"""
PDP capture: parallel desktop + mobile navigation, screenshots, and fact
extraction.

Fixed shot list (max 5 images sent to Claude):
  1. desktop above-the-fold      3. mobile above-the-fold
  2. desktop full page           4. mobile full page
  5. desktop buy-box close-up (when an ATC button is located)

Desktop and mobile run in separate browser contexts concurrently — no
viewport-swapping on a single page, which the old pipeline spent ~5s on.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from playwright.async_api import Browser, Page

from config import settings
from analyzer.pdp.extractor import (
    METRICS_INIT_JS,
    extract_dom_facts,
    extract_jsonld_products,
    extract_performance_metrics,
)
from utils.images.processor import resize_screenshot_if_needed
from utils.net import validate_public_url, UnsafeURLError
from utils.testing.overlays import OverlayDismisser

logger = logging.getLogger(__name__)

DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class NotPubliclyReachableError(Exception):
    """Navigation landed on a non-public address (redirect-based SSRF)."""


async def capture_pdp(
    browser: Browser,
    url: str,
    progress: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Run the full capture for both viewports.

    Returns:
        {
          "desktop": {facts, metrics, jsonld_products, screenshots{above_fold, full_page, buy_box}, atc_test, final_url},
          "mobile":  {facts, metrics, screenshots{above_fold, full_page}, final_url},
          "page_title": str,
          "timings": {...},
        }
    """
    start = time.time()
    if progress:
        progress(15, "Loading your product page on desktop and mobile...")

    desktop_task = asyncio.create_task(
        _capture_viewport(browser, url, DESKTOP_VIEWPORT, DESKTOP_UA, is_mobile=False)
    )
    mobile_task = asyncio.create_task(
        _capture_viewport(browser, url, MOBILE_VIEWPORT, MOBILE_UA, is_mobile=True)
    )
    desktop, mobile = await asyncio.gather(desktop_task, mobile_task)

    if progress:
        progress(45, "Reading structured product data and testing add-to-cart...")

    return {
        "desktop": desktop,
        "mobile": mobile,
        "page_title": desktop.get("page_title") or mobile.get("page_title") or "",
        "timings": {"capture_seconds": round(time.time() - start, 2)},
    }


async def _capture_viewport(
    browser: Browser,
    url: str,
    viewport: Dict[str, int],
    user_agent: str,
    is_mobile: bool,
) -> Dict[str, Any]:
    context = await browser.new_context(
        viewport=viewport,
        user_agent=user_agent,
        is_mobile=is_mobile,
        has_touch=is_mobile,
        device_scale_factor=2 if is_mobile else 1,
    )
    await context.add_init_script(METRICS_INIT_JS)
    page = await context.new_page()
    label = "mobile" if is_mobile else "desktop"

    try:
        await _navigate(page, url)
        _recheck_final_url(page.url)

        page_title = await page.title()

        # Clear popups/cookie banners before anything is measured or shot
        try:
            dismisser = OverlayDismisser(page)
            overlay_results = await asyncio.wait_for(dismisser.dismiss_all_overlays(), timeout=12)
        except Exception as e:
            logger.warning(f"[{label}] overlay dismissal skipped: {e}")
            overlay_results = {}

        # Trigger lazy-loaded content, then return to top for the fold shot
        await _scroll_through(page)

        above_fold_bytes = await page.screenshot(full_page=False)
        full_page_bytes = await page.screenshot(full_page=True)

        facts = await extract_dom_facts(page)
        metrics = await extract_performance_metrics(page)

        result: Dict[str, Any] = {
            "facts": facts,
            "metrics": metrics,
            "page_title": page_title,
            "final_url": page.url,
            "overlays_dismissed": len(overlay_results.get("overlays_dismissed", [])) if isinstance(overlay_results, dict) else 0,
            "screenshots": {
                "above_fold": resize_screenshot_if_needed(above_fold_bytes),
                "full_page": resize_screenshot_if_needed(full_page_bytes),
            },
        }

        if not is_mobile:
            result["jsonld_products"] = await extract_jsonld_products(page)
            buy_box_shot = await _capture_buy_box(page)
            if buy_box_shot:
                result["screenshots"]["buy_box"] = buy_box_shot
            # Interaction test LAST — it may open a cart drawer
            result["atc_test"] = await _test_add_to_cart(page)

        return result

    finally:
        try:
            await context.close()
        except Exception as e:
            logger.warning(f"[{label}] context close failed: {e}")


async def _navigate(page: Page, url: str) -> None:
    """Navigate with a chat-friendly time budget: DOM ready fast, then a
    bounded settle wait instead of blocking on the full load event."""
    await page.goto(url, wait_until="domcontentloaded", timeout=settings.NAV_TIMEOUT_MS)
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass  # busy pages never go idle; analyze what we have
    await page.wait_for_timeout(1500)


def _recheck_final_url(final_url: str) -> None:
    """Redirects can escape the submission-time SSRF check — re-validate."""
    try:
        validate_public_url(final_url)
    except UnsafeURLError as e:
        raise NotPubliclyReachableError(str(e)) from e


async def _scroll_through(page: Page) -> None:
    """Scroll to the bottom in steps to fire lazy loaders, then back to top."""
    try:
        await page.evaluate(
            """async () => {
                const step = window.innerHeight;
                const max = Math.min(document.body.scrollHeight, step * 12);
                for (let y = 0; y < max; y += step) {
                    window.scrollTo(0, y);
                    await new Promise(r => setTimeout(r, 120));
                }
                window.scrollTo(0, 0);
            }"""
        )
        await page.wait_for_timeout(600)
    except Exception as e:
        logger.warning(f"Scroll pass failed: {e}")


async def _capture_buy_box(page: Page) -> Optional[str]:
    """Close-up of the purchase area: the region around the ATC button."""
    try:
        box = await page.evaluate(
            """() => {
                const phrases = /^(add to (cart|bag|basket)|buy (it )?now|purchase|pre[- ]?order)/i;
                let el = document.querySelector('form[action*="/cart/add"]')
                      || document.querySelector('button[name="add"]')
                      || [...document.querySelectorAll('button')].find(b => phrases.test((b.innerText || '').trim()));
                if (!el) return null;
                // widen to a meaningful container (price + variants + CTA)
                for (let i = 0; el.parentElement && i < 4; i++) {
                    const r = el.parentElement.getBoundingClientRect();
                    if (r.height > window.innerHeight * 0.9) break;
                    el = el.parentElement;
                }
                const r = el.getBoundingClientRect();
                if (r.width < 50 || r.height < 50) return null;
                return { x: Math.max(0, r.x), y: Math.max(0, r.y + window.scrollY),
                         width: Math.min(r.width, window.innerWidth), height: Math.min(r.height, 1600) };
            }"""
        )
        if not box:
            return None
        shot = await page.screenshot(clip=box)
        return resize_screenshot_if_needed(shot)
    except Exception as e:
        logger.warning(f"Buy-box crop failed: {e}")
        return None


async def _test_add_to_cart(page: Page) -> Dict[str, Any]:
    """
    The one interaction test worth keeping: click ATC, verify the cart
    responds. Time-boxed and fully fenced — a failure here never fails the
    analysis, it just becomes a data point.
    """
    result = {"attempted": False, "cart_responded": False, "detail": ""}
    try:
        state_js = """() => ({
            url: location.href,
            cartCount: (document.querySelector('[class*="cart-count" i], [class*="cart_count" i], [data-cart-count], .cart-count-bubble') || {}).innerText || null,
            drawerOpen: !!document.querySelector('[class*="cart-drawer" i][class*="open" i], [class*="cart" i][class*="active" i], cart-drawer[open], #CartDrawer.active'),
        })"""
        before = await page.evaluate(state_js)

        clicked = await page.evaluate(
            """() => {
                const phrases = /^(add to (cart|bag|basket)|buy (it )?now)/i;
                const btn = document.querySelector('form[action*="/cart/add"] button[type="submit"], button[name="add"]')
                    || [...document.querySelectorAll('button')].find(b => phrases.test((b.innerText || '').trim()));
                if (!btn || btn.disabled) return false;
                btn.click();
                return true;
            }"""
        )
        if not clicked:
            result["detail"] = "No enabled add-to-cart button found to test"
            return result

        result["attempted"] = True
        await page.wait_for_timeout(2500)
        after = await page.evaluate(state_js)

        if (
            after.get("drawerOpen")
            or (after.get("cartCount") and after.get("cartCount") != before.get("cartCount"))
            or ("/cart" in (after.get("url") or "") and "/cart" not in (before.get("url") or ""))
        ):
            result["cart_responded"] = True
            result["detail"] = "Cart responded to add-to-cart click (drawer opened, count changed, or navigated to cart)"
        else:
            result["detail"] = "No visible cart response detected within 2.5s of clicking add-to-cart (may require a variant selection first)"
    except Exception as e:
        result["detail"] = f"Add-to-cart test errored: {e}"
    return result
