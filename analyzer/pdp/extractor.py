"""
Deterministic PDP fact extraction.

Instead of asking the vision model to guess what exists on the page, this
module pulls machine-readable ground truth in one DOM pass per viewport:

- schema.org Product JSON-LD (price, availability, ratings — free, no vision)
- buy box facts (ATC button text/position/fold/sticky, price proximity)
- gallery, reviews, shipping/returns, variants, trust signals
- real performance numbers (nav timing, LCP, CLS, transfer size)

These facts are fed to Claude as verified ground truth, which is what kills
the false-positive problem the old selector-list + prompt-warning stack was
patching around.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# Injected via context.add_init_script BEFORE navigation so buffered
# performance observers catch LCP/CLS from the first paint.
METRICS_INIT_JS = """
(() => {
  window.__cro_metrics = { lcp: null, cls: 0 };
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) window.__cro_metrics.lcp = last.startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__cro_metrics.cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
})();
"""


# Single-pass DOM extraction. Returns a plain JSON object; anything that
# can't be determined is null/false rather than guessed.
PDP_FACTS_JS = r"""
() => {
  const vh = window.innerHeight;
  const vw = window.innerWidth;

  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };

  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x), y: Math.round(r.y + window.scrollY),
      width: Math.round(r.width), height: Math.round(r.height),
      viewportY: Math.round(r.y),
    };
  };

  const aboveFold = (el) => {
    const r = el.getBoundingClientRect();
    return r.top >= 0 && r.top < vh;
  };

  const isStickyOrFixed = (el) => {
    let node = el;
    for (let i = 0; node && i < 8; i++) {
      const pos = window.getComputedStyle(node).position;
      if (pos === 'fixed' || pos === 'sticky') return true;
      node = node.parentElement;
    }
    return false;
  };

  const textOf = (el) => (el ? (el.innerText || el.value || '').trim().slice(0, 120) : null);

  // ---- Add to cart button ----
  const atcSelectors = [
    'form[action*="/cart/add"] button[type="submit"]',
    'form[action*="/cart/add"] input[type="submit"]',
    'button[name="add"]', 'button[id*="AddToCart" i]', 'button[class*="add-to-cart" i]',
    'button[class*="addtocart" i]', 'button[data-testid*="add-to-cart" i]',
    '[data-action*="add-to-cart" i]', 'button[class*="add_to_cart" i]',
    '#add-to-cart', '.add-to-cart', '.product-form__submit', '.single_add_to_cart_button',
  ];
  let atcEl = null;
  for (const sel of atcSelectors) {
    try {
      const candidates = [...document.querySelectorAll(sel)].filter(visible);
      if (candidates.length) { atcEl = candidates[0]; break; }
    } catch (e) {}
  }
  if (!atcEl) {
    // text-based fallback: any visible button whose text is an ATC phrase
    const phrases = /^(add to (cart|bag|basket)|buy (it )?now|add to trolley|purchase|pre[- ]?order|shop now)/i;
    for (const b of document.querySelectorAll('button, input[type="submit"], a[role="button"], a.button, a.btn')) {
      const t = (b.innerText || b.value || '').trim();
      if (t && phrases.test(t) && visible(b)) { atcEl = b; break; }
    }
  }

  const atc = atcEl ? {
    found: true,
    text: textOf(atcEl),
    rect: rectOf(atcEl),
    above_fold: aboveFold(atcEl),
    sticky: isStickyOrFixed(atcEl),
    disabled: atcEl.disabled === true || atcEl.getAttribute('aria-disabled') === 'true',
    background_color: window.getComputedStyle(atcEl).backgroundColor,
    text_color: window.getComputedStyle(atcEl).color,
    font_size: window.getComputedStyle(atcEl).fontSize,
  } : { found: false };

  // ---- Price ----
  const priceSelectors = [
    '[itemprop="price"]', '.price', '.product-price', '[class*="product__price" i]',
    '[class*="price-item" i]', '[data-testid*="price" i]', '[class*="ProductPrice" i]',
  ];
  let priceEl = null;
  const priceRe = /(\$|€|£|¥|kr|USD|EUR|GBP|CAD|AUD)\s?\d|\d+([.,]\d{2})?\s?(\$|€|£|USD|EUR)/;
  for (const sel of priceSelectors) {
    try {
      const candidates = [...document.querySelectorAll(sel)].filter((el) => visible(el) && priceRe.test(el.innerText || ''));
      if (candidates.length) { priceEl = candidates[0]; break; }
    } catch (e) {}
  }

  let priceNearAtc = null;
  if (priceEl && atcEl) {
    const pr = priceEl.getBoundingClientRect();
    const ar = atcEl.getBoundingClientRect();
    priceNearAtc = Math.abs((pr.top + pr.height / 2) - (ar.top + ar.height / 2)) < vh * 0.6;
  }

  const compareAt = [...document.querySelectorAll('s, del, strike, [class*="compare-at" i], [class*="compare_at" i], [class*="price--compare" i], [class*="was-price" i], [class*="old-price" i]')]
    .some((el) => visible(el) && priceRe.test(el.innerText || ''));

  const bodyText = document.body.innerText || '';
  const installmentProviders = ['klarna', 'afterpay', 'affirm', 'sezzle', 'zip pay', 'shop pay', 'clearpay', 'paypal pay in']
    .filter((p) => bodyText.toLowerCase().includes(p));

  const price = {
    found: !!priceEl,
    text: textOf(priceEl),
    above_fold: priceEl ? aboveFold(priceEl) : null,
    near_atc: priceNearAtc,
    has_compare_at_price: compareAt,
    installment_options: installmentProviders,
  };

  // ---- Gallery ----
  const gallerySelectors = [
    '.product__media', '.product-gallery', '.product-images', '[class*="ProductGallery" i]',
    '[class*="product-media" i]', '[data-testid*="gallery" i]', '.woocommerce-product-gallery',
  ];
  let galleryEl = null;
  for (const sel of gallerySelectors) {
    try { const el = document.querySelector(sel); if (el && visible(el)) { galleryEl = el; break; } } catch (e) {}
  }
  const galleryImgs = galleryEl ? [...galleryEl.querySelectorAll('img')] : [];
  const gallery = {
    found: !!galleryEl,
    image_count: galleryImgs.length,
    images_missing_alt: galleryImgs.filter((i) => !(i.alt || '').trim()).length,
    has_video: !!document.querySelector('video, [class*="product" i] iframe[src*="youtube"], [class*="product" i] iframe[src*="vimeo"], model-viewer'),
    main_image_above_fold: galleryEl ? aboveFold(galleryEl) : null,
  };

  // ---- Reviews / social proof ----
  const reviewWidgetSelectors = [
    '[class*="yotpo" i]', '[class*="stamped" i]', '[class*="loox" i]', '[class*="judgeme" i]',
    '[class*="jdgm" i]', '[class*="okendo" i]', '[class*="trustpilot" i]', '[class*="reviews-io" i]',
    '[class*="review" i]', '[id*="review" i]', '[class*="rating" i]', '[itemprop="aggregateRating"]',
  ];
  let reviewEl = null;
  for (const sel of reviewWidgetSelectors) {
    try {
      const candidates = [...document.querySelectorAll(sel)].filter(visible);
      if (candidates.length) { reviewEl = candidates[0]; break; }
    } catch (e) {}
  }
  const reviews = {
    widget_found: !!reviewEl,
    above_fold: reviewEl ? aboveFold(reviewEl) : null,
    star_rating_visible: !!document.querySelector('[class*="star" i] svg, .stars, [class*="star-rating" i], [aria-label*="stars" i], [aria-label*="rating" i]'),
  };

  // ---- Shipping / returns / risk reversal (near the buy box) ----
  let buyBoxText = '';
  if (atcEl) {
    let container = atcEl;
    for (let i = 0; container.parentElement && i < 5; i++) container = container.parentElement;
    buyBoxText = (container.innerText || '').toLowerCase();
  }
  const scanZone = buyBoxText || bodyText.toLowerCase().slice(0, 6000);
  const shipping = {
    shipping_mention_near_buybox: /(free shipping|free delivery|ships (in|within|by)|delivery (in|within|by)|arrives|dispatch)/i.test(scanZone),
    returns_mention_near_buybox: /(free returns?|\d+[- ]day returns?|return policy|money[- ]back|easy returns?)/i.test(scanZone),
    guarantee_mention: /(guarantee|warranty)/i.test(bodyText.toLowerCase()),
    stock_urgency_mention: /(only \d+ left|low stock|selling fast|in stock|out of stock|sold out)/i.test(scanZone),
  };

  // ---- Variants ----
  const variantSelects = [...document.querySelectorAll('form select, [class*="variant" i] select, [class*="product" i] select')].filter(visible);
  const swatches = [...document.querySelectorAll('[class*="swatch" i], [class*="variant" i] input[type="radio"], [class*="option" i] input[type="radio"]')].filter(visible);
  const variants = {
    select_count: variantSelects.length,
    swatch_count: swatches.length,
    has_size_guide: /size (guide|chart)/i.test(bodyText),
    uses_dropdowns: variantSelects.length > 0 && swatches.length === 0,
  };

  // ---- Trust ----
  const trust = {
    payment_icons: [...document.querySelectorAll('[class*="payment" i] img, [class*="payment" i] svg, img[src*="visa" i], img[src*="mastercard" i], img[src*="paypal" i], img[alt*="visa" i]')].filter(visible).length,
    security_badges: [...document.querySelectorAll('img[src*="secure" i], img[alt*="secure" i], [class*="trust-badge" i], [class*="trustbadge" i]')].filter(visible).length,
  };

  const quantity_selector_found = !!document.querySelector('input[name*="quantity" i], select[name*="quantity" i], [class*="quantity" i] input, [class*="qty" i] input');

  // ---- Meta ----
  const og = (prop) => { const m = document.querySelector(`meta[property="${prop}"]`); return m ? m.content : null; };
  const meta = {
    title: document.title,
    h1: textOf(document.querySelector('h1')),
    og_type: og('og:type'),
    og_price: og('product:price:amount') || og('og:price:amount'),
    canonical: (document.querySelector('link[rel="canonical"]') || {}).href || null,
    has_cart_add_form: !!document.querySelector('form[action*="/cart/add"], form[action*="add-to-cart"], form.cart'),
  };

  return {
    viewport: { width: vw, height: vh },
    document_height: Math.round(document.body.scrollHeight),
    atc, price, gallery, reviews, shipping, variants, trust,
    quantity_selector_found, meta,
  };
}
"""

PERF_METRICS_JS = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const resources = performance.getEntriesByType('resource');
  const totalBytes = resources.reduce((sum, r) => sum + (r.transferSize || 0), 0) + (nav ? (nav.transferSize || 0) : 0);
  const m = window.__cro_metrics || {};
  return {
    lcp_ms: m.lcp != null ? Math.round(m.lcp) : null,
    cls: m.cls != null ? Math.round(m.cls * 1000) / 1000 : null,
    dom_content_loaded_ms: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
    load_event_ms: nav && nav.loadEventEnd > 0 ? Math.round(nav.loadEventEnd) : null,
    ttfb_ms: nav ? Math.round(nav.responseStart) : null,
    transfer_size_bytes: Math.round(totalBytes),
    request_count: resources.length + 1,
  };
}
"""


async def extract_dom_facts(page: Page) -> Dict[str, Any]:
    """Run the single-pass DOM extraction on the current page state."""
    try:
        return await page.evaluate(PDP_FACTS_JS)
    except Exception as e:
        logger.warning(f"DOM fact extraction failed: {e}")
        return {"error": str(e)}


async def extract_performance_metrics(page: Page) -> Dict[str, Any]:
    """Read real performance numbers (requires METRICS_INIT_JS injected pre-nav)."""
    try:
        return await page.evaluate(PERF_METRICS_JS)
    except Exception as e:
        logger.warning(f"Performance metric extraction failed: {e}")
        return {}


async def extract_jsonld_products(page: Page) -> List[Dict[str, Any]]:
    """Parse schema.org Product objects out of the page's JSON-LD blocks."""
    try:
        raw_blocks = await page.evaluate(
            """() => [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent)"""
        )
    except Exception as e:
        logger.warning(f"JSON-LD read failed: {e}")
        return []

    products = []
    for raw in raw_blocks or []:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        products.extend(_find_products(data))
    return [_summarize_product(p) for p in products]


def _find_products(node: Any) -> List[Dict[str, Any]]:
    """Recursively locate Product nodes (handles arrays and @graph)."""
    found = []
    if isinstance(node, list):
        for item in node:
            found.extend(_find_products(item))
    elif isinstance(node, dict):
        node_type = node.get("@type", "")
        types = node_type if isinstance(node_type, list) else [node_type]
        if any(t in ("Product", "ProductGroup") for t in types):
            found.append(node)
        for key in ("@graph", "mainEntity", "hasVariant"):
            if key in node:
                found.extend(_find_products(node[key]))
    return found


def _summarize_product(p: Dict[str, Any]) -> Dict[str, Any]:
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    rating = p.get("aggregateRating") or {}
    images = p.get("image")
    if isinstance(images, str):
        images = [images]

    brand = p.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    return {
        "name": p.get("name"),
        "brand": brand,
        "price": offers.get("price") or offers.get("lowPrice"),
        "currency": offers.get("priceCurrency"),
        "availability": _short_availability(offers.get("availability")),
        "rating_value": rating.get("ratingValue"),
        "review_count": rating.get("reviewCount") or rating.get("ratingCount"),
        "image_count": len(images) if isinstance(images, list) else 0,
        "description_present": bool(p.get("description")),
    }


def _short_availability(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return str(value).rsplit("/", 1)[-1]  # "https://schema.org/InStock" -> "InStock"


def detect_pdp(dom_facts: Dict[str, Any], jsonld_products: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Decide whether the page is a product detail page.

    Signals (any strong one qualifies):
    - JSON-LD Product schema present
    - og:type == product
    - add-to-cart form/button + visible price
    """
    signals = []
    meta = dom_facts.get("meta", {}) or {}

    if jsonld_products:
        signals.append("schema.org Product JSON-LD present")
    if (meta.get("og_type") or "").lower() in ("product", "og:product", "product.item"):
        signals.append("og:type is product")
    if meta.get("has_cart_add_form"):
        signals.append("add-to-cart form present")
    if dom_facts.get("atc", {}).get("found") and dom_facts.get("price", {}).get("found"):
        signals.append("add-to-cart button and price both visible")

    return bool(signals), signals
