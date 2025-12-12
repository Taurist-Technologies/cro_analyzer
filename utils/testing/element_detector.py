"""
Element Detection Module for CRO Analyzer

Detects common CRO elements on the page BEFORE Claude analysis
to prevent false positive "missing element" recommendations.

Elements detected:
- Hamburger menus (mobile navigation)
- Star ratings and reviews
- Social proof elements
- Trust badges and security indicators
- Call-to-action buttons
- Navigation menus
- Search functionality
- Shopping cart elements
"""

from typing import Dict, List, Optional, Any
from playwright.async_api import Page
import logging

logger = logging.getLogger(__name__)


class ElementDetector:
    """
    Detects common CRO elements on a page before Claude analysis.
    Prevents false positives by identifying what elements actually exist.
    """

    # Comprehensive selectors for each element type
    SELECTORS = {
        "hamburger_menu": [
            "[aria-label*='menu' i]",
            "[aria-label*='navigation' i]",
            ".hamburger",
            ".burger",
            ".burger-menu",
            ".mobile-nav-toggle",
            ".mobile-menu-toggle",
            ".nav-toggle",
            ".menu-toggle",
            "button[class*='menu' i]",
            "button[class*='hamburger' i]",
            "button[class*='burger' i]",
            "[data-toggle='collapse']",
            ".navbar-toggler",
            ".nav-hamburger",
            "[class*='mobile-nav']",
            "[class*='mobile-menu']",
            # SVG hamburger icons (3 horizontal lines)
            "svg[class*='menu' i]",
            "[class*='hamburger'] svg",
            # Toggle button patterns (aria-expanded, aria-controls)
            "button[aria-expanded]",
            "header button:has(span.sr-only)",
            "[aria-controls*='nav' i]",
            "[aria-controls*='menu' i]",
            "[aria-controls*='drawer' i]",
            "[aria-controls*='sidebar' i]",
            "button:has(svg line)",
            "[data-action*='toggle' i]",
            "[data-action*='menu' i]",
        ],
        "star_ratings": [
            ".stars",
            ".star-rating",
            ".rating",
            ".ratings",
            "[class*='star-rating' i]",
            "[class*='star_rating' i]",
            "[class*='starrating' i]",
            "[class*='review-stars' i]",
            "[class*='reviews-stars' i]",
            "[aria-label*='rating' i]",
            "[aria-label*='stars' i]",
            "[class*='yotpo']",  # Yotpo reviews
            "[class*='stamped']",  # Stamped reviews
            "[class*='loox']",  # Loox reviews
            "[class*='judge']",  # Judge.me reviews
            "[class*='trustpilot']",
            "[class*='bazaarvoice']",
            "[class*='powerreviews']",
            "[data-rating]",
            "svg[class*='star' i]",
            "[role='img'][aria-label*='star' i]",
        ],
        "social_proof": [
            ".testimonial",
            ".testimonials",
            ".review",
            ".reviews",
            ".customer-review",
            ".customer-reviews",
            "[class*='testimonial' i]",
            "[class*='social-proof' i]",
            "[class*='socialproof' i]",
            "[class*='trust-pilot' i]",
            "[class*='trustpilot' i]",
            "[class*='yotpo']",
            "[class*='stamped']",
            "[class*='loox']",
            "[class*='judge']",
            "[class*='customer-photo' i]",
            "[class*='ugc' i]",  # User generated content
            "[class*='as-seen' i]",  # As seen in...
            "[class*='featured-in' i]",
            "[class*='press-logo' i]",
            "[class*='media-logo' i]",
            "[class*='client-logo' i]",
            "[class*='partner-logo' i]",
            "[class*='brand-logo' i]",
        ],
        "trust_badges": [
            ".trust",
            ".trust-badge",
            ".trust-badges",
            ".badge",
            ".badges",
            ".secure",
            ".security",
            ".ssl",
            ".payment-icons",
            ".payment-badges",
            "[class*='trust' i]",
            "[class*='secure' i]",
            "[class*='security' i]",
            "[class*='ssl' i]",
            "[class*='guarantee' i]",
            "[class*='certified' i]",
            "[class*='verified' i]",
            "[alt*='secure' i]",
            "[alt*='trust' i]",
            "[alt*='ssl' i]",
            "[alt*='safe' i]",
            "[alt*='guarantee' i]",
            "[alt*='certified' i]",
            "[alt*='verified' i]",
            "[alt*='mcafee' i]",
            "[alt*='norton' i]",
            "[alt*='bbb' i]",
            "[class*='money-back' i]",
            "[class*='free-shipping' i]",
            "[class*='returns' i]",
        ],
        "cta_buttons": [
            "button[class*='primary' i]",
            "button[class*='cta' i]",
            "a[class*='cta' i]",
            ".cta",
            ".cta-button",
            "[class*='add-to-cart' i]",
            "[class*='addtocart' i]",
            "[class*='buy-now' i]",
            "[class*='buynow' i]",
            "[class*='shop-now' i]",
            "[class*='shopnow' i]",
            "[class*='get-started' i]",
            "[class*='getstarted' i]",
            "[class*='sign-up' i]",
            "[class*='signup' i]",
            "[class*='subscribe' i]",
            "[class*='learn-more' i]",
            "button:has-text('Add to Cart')",
            "button:has-text('Buy Now')",
            "button:has-text('Shop Now')",
            "button:has-text('Get Started')",
            "a:has-text('Shop Now')",
            "a:has-text('Get Started')",
        ],
        "navigation": [
            "nav",
            ".nav",
            ".navigation",
            ".main-nav",
            ".main-menu",
            ".primary-nav",
            ".site-nav",
            "[role='navigation']",
            "header nav",
            ".navbar",
            ".menu",
            "[class*='main-nav' i]",
            "[class*='primary-nav' i]",
            "[class*='site-nav' i]",
        ],
        "search": [
            # Input-based search fields
            "input[type='search']",
            "[class*='search' i] input",
            ".search",
            ".search-form",
            ".search-box",
            ".search-input",
            "[aria-label*='search' i]",
            "[placeholder*='search' i]",
            "[name*='search' i]",
            "[name='q']",
            "[name='s']",
            ".site-search",
            "[class*='searchbar' i]",
            "[class*='search-bar' i]",
            # Search buttons/links (click to open search modal)
            "a[href*='search' i]",
            "button:has-text('Search')",
            "a:has-text('Search')",
            "[class*='search-icon' i]",
            "[class*='search-toggle' i]",
            "[class*='search-btn' i]",
            "[class*='search-button' i]",
            "[data-action*='search' i]",
            "svg[aria-label*='search' i]",
            "[role='search']",
            # Common search icon patterns
            "button[aria-label*='search' i]",
            "a[aria-label*='search' i]",
            "[class*='icon-search' i]",
            "[class*='search_icon' i]",
        ],
        "cart": [
            ".cart",
            ".cart-icon",
            ".cart-link",
            ".shopping-cart",
            ".basket",
            ".bag",
            ".bag-icon",
            "[class*='cart' i]",
            "[class*='basket' i]",
            "[class*='shopping-bag' i]",
            "[aria-label*='cart' i]",
            "[aria-label*='basket' i]",
            "[aria-label*='bag' i]",
            "[href*='cart']",
            "[href*='basket']",
            "[href*='bag']",
            ".minicart",
            ".mini-cart",
        ],
        "forms": [
            "form",
            ".form",
            "[class*='form' i]",
            "input[type='email']",
            "input[type='tel']",
            "input[name*='email' i]",
            "input[name*='phone' i]",
            "[class*='newsletter' i]",
            "[class*='signup-form' i]",
            "[class*='contact-form' i]",
            "[class*='lead-form' i]",
        ],
        "product_grid": [
            ".products",
            ".product-grid",
            ".product-list",
            "[class*='product-grid' i]",
            "[class*='product-list' i]",
            "[class*='products-grid' i]",
            "[class*='collection-grid' i]",
            ".collection-products",
        ],
        "footer_links": [
            "footer a",
            "footer nav",
            ".footer-nav",
            ".footer-links",
            ".footer-menu",
            "[class*='footer-nav' i]",
            "[class*='footer-links' i]",
        ],
    }

    def __init__(self, page: Page):
        """
        Initialize element detector.

        Args:
            page: Playwright Page object
        """
        self.page = page

    async def detect_all(self, viewport: str = "desktop") -> Dict[str, Any]:
        """
        Detect all common CRO elements on the page.

        Args:
            viewport: "desktop" or "mobile" - used for logging

        Returns:
            Dictionary with detection results for each element type
        """
        logger.info(f"🔍 Starting element detection for {viewport} viewport")

        results = {
            "viewport": viewport,
            "detected_elements": {},
            "summary": {
                "total_elements_found": 0,
                "element_types_found": [],
            }
        }

        for element_type, selectors in self.SELECTORS.items():
            detection = await self._detect_element(element_type, selectors)
            results["detected_elements"][element_type] = detection

            if detection["found"]:
                results["summary"]["total_elements_found"] += detection["count"]
                results["summary"]["element_types_found"].append(element_type)

        logger.info(
            f"✅ Element detection complete: {len(results['summary']['element_types_found'])} "
            f"element types found, {results['summary']['total_elements_found']} total elements"
        )

        return results

    async def _detect_element(self, element_type: str, selectors: List[str]) -> Dict[str, Any]:
        """
        Detect a specific element type using multiple selectors.

        Args:
            element_type: Name of the element type
            selectors: List of CSS selectors to try

        Returns:
            Detection result with found status, count, and matched selector
        """
        total_count = 0
        visible_count = 0
        matched_selectors = []
        sample_texts = []

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()

                if count > 0:
                    total_count += count
                    matched_selectors.append(selector)

                    # Check visibility and get sample text
                    for i in range(min(count, 3)):  # Check up to 3 elements
                        try:
                            element = locator.nth(i)
                            if await element.is_visible():
                                visible_count += 1
                                # Try to get text content for context
                                text = await element.text_content()
                                if text and text.strip() and len(text.strip()) < 100:
                                    sample_texts.append(text.strip()[:50])
                        except:
                            pass

            except Exception as e:
                # Some selectors may not be valid, skip them
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue

        return {
            "found": total_count > 0,
            "count": total_count,
            "visible_count": visible_count,
            "matched_selectors": matched_selectors[:3],  # Limit to 3 for brevity
            "sample_texts": list(set(sample_texts))[:3],  # Unique samples, limit to 3
        }

    async def detect_hamburger_menu(self) -> Dict[str, Any]:
        """Specifically detect hamburger menu with extra validation."""
        base_result = await self._detect_element("hamburger_menu", self.SELECTORS["hamburger_menu"])

        # Additional checks for hamburger menu
        if base_result["found"]:
            # Try to verify it's a working menu toggle
            try:
                for selector in base_result["matched_selectors"]:
                    element = self.page.locator(selector).first
                    if await element.is_visible():
                        # Check if it has click handler indicators
                        onclick = await element.get_attribute("onclick")
                        data_toggle = await element.get_attribute("data-toggle")
                        aria_expanded = await element.get_attribute("aria-expanded")
                        aria_controls = await element.get_attribute("aria-controls")

                        base_result["has_click_handler"] = onclick is not None
                        base_result["has_toggle_attribute"] = data_toggle is not None
                        base_result["has_aria_expanded"] = aria_expanded is not None
                        base_result["has_aria_controls"] = aria_controls is not None
                        break
            except:
                pass

        return base_result

    def format_for_prompt(self, detection_results: Dict[str, Any]) -> str:
        """
        Format detection results for inclusion in Claude prompt.

        Args:
            detection_results: Results from detect_all()

        Returns:
            Formatted string for prompt injection
        """
        lines = []
        viewport = detection_results.get("viewport", "unknown")

        lines.append(f"### Viewport: {viewport.upper()}")
        lines.append("")

        for element_type, data in detection_results["detected_elements"].items():
            status = "FOUND" if data["found"] else "NOT FOUND"
            formatted_name = element_type.replace("_", " ").title()

            if data["found"]:
                count_info = f"({data['count']} elements, {data['visible_count']} visible)"
                lines.append(f"- **{formatted_name}**: {status} {count_info}")

                # Add sample text context if available
                if data.get("sample_texts"):
                    samples = ", ".join([f'"{t}"' for t in data["sample_texts"][:2]])
                    lines.append(f"  - Sample content: {samples}")
            else:
                lines.append(f"- **{formatted_name}**: {status}")

        return "\n".join(lines)


async def detect_elements_both_viewports(page: Page) -> Dict[str, Any]:
    """
    Helper function to detect elements at both desktop and mobile viewports.

    Args:
        page: Playwright Page object

    Returns:
        Combined detection results for both viewports
    """
    detector = ElementDetector(page)

    # Get current viewport
    original_viewport = page.viewport_size

    # Detect at current viewport (assumed desktop)
    desktop_results = await detector.detect_all(viewport="desktop")

    # Switch to mobile viewport and detect
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.wait_for_timeout(500)  # Wait for responsive CSS to apply

    mobile_results = await detector.detect_all(viewport="mobile")

    # Restore original viewport
    if original_viewport:
        await page.set_viewport_size(original_viewport)

    return {
        "desktop": desktop_results,
        "mobile": mobile_results,
    }


def format_detection_for_prompt(detection_results: Dict[str, Any]) -> str:
    """
    Format complete detection results for Claude prompt.

    Args:
        detection_results: Results from detect_elements_both_viewports()

    Returns:
        Formatted string for prompt injection
    """
    detector = ElementDetector(None)  # Just need the format method

    lines = [
        "## VERIFIED ELEMENTS - DO NOT RECOMMEND ADDING THESE",
        "",
        "The following elements have been programmatically verified to exist on this page.",
        "**CRITICAL**: If an element is listed as FOUND, do NOT recommend adding it.",
        "Only recommend IMPROVEMENTS to existing elements, never claim they are missing.",
        "",
    ]

    if "desktop" in detection_results:
        # Create a temporary detector instance for formatting
        temp_detector = ElementDetector(None)
        temp_detector.page = None  # Not needed for formatting
        lines.append(temp_detector.format_for_prompt(detection_results["desktop"]))
        lines.append("")

    if "mobile" in detection_results:
        temp_detector = ElementDetector(None)
        temp_detector.page = None
        lines.append(temp_detector.format_for_prompt(detection_results["mobile"]))

    return "\n".join(lines)
