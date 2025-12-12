"""
Recommendation Validator Module for CRO Analyzer

Validates Claude's CRO recommendations against the actual page using Playwright.
Identifies false positives where Claude claims elements are missing but they exist.

This is Layer 2 of the validation pipeline:
1. Pre-analysis detection (ElementDetector) - prevents false positives
2. POST-ANALYSIS VALIDATION (this module) - catches remaining false positives
3. AI post-validation (AIValidator) - handles uncertain/subjective cases
"""

from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import Page
import logging
import re

logger = logging.getLogger(__name__)


class RecommendationValidator:
    """
    Validates Claude's CRO recommendations against the actual page.

    Identifies false positives by:
    1. Detecting "missing element" claims in recommendations
    2. Searching the page for those elements
    3. Marking recommendations as false positives if elements exist
    """

    # Keywords that indicate a "missing element" claim
    MISSING_KEYWORDS = [
        "add ",
        "adding ",
        "include ",
        "including ",
        "missing",
        "no ",
        "doesn't have",
        "does not have",
        "doesn't include",
        "does not include",
        "lack",
        "lacking",
        "without ",
        "needs ",
        "need to add",
        "should have",
        "should include",
        "consider adding",
        "recommend adding",
        "implement ",
        "implementing ",
        "create ",
        "creating ",
    ]

    # Keywords that indicate a subjective "quality/clarity" claim
    # These claims need AI validation since Playwright cannot verify them
    QUALITY_CLAIM_KEYWORDS = [
        "doesn't clearly",
        "does not clearly",
        "not clear",
        "unclear",
        "generic",
        "lacks clarity",
        "could be clearer",
        "could be more specific",
        "doesn't communicate",
        "does not communicate",
        "vague",
        "doesn't explain",
        "does not explain",
        "doesn't articulate",
        "does not articulate",
        "weak value",
        "unclear value",
        "minimal copy",
        "minimal text",
        "doesn't convey",
        "does not convey",
        "fails to communicate",
        "fails to explain",
        "doesn't tell",
        "does not tell",
    ]

    # Element type keywords mapped to CSS selectors for validation
    VALIDATION_RULES = {
        "hamburger": [
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
        "mobile menu": [
            ".hamburger",
            ".burger",
            ".mobile-nav",
            ".mobile-menu",
            "[class*='mobile-nav' i]",
            "[class*='mobile-menu' i]",
            ".navbar-toggler",
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
        "menu": [
            "nav",
            ".nav",
            ".navigation",
            ".main-nav",
            ".main-menu",
            "[role='navigation']",
            "header nav",
            ".navbar",
            ".menu",
        ],
        "navigation": [
            "nav",
            ".navigation",
            "[role='navigation']",
            ".main-nav",
            ".primary-nav",
            ".site-nav",
            "header nav",
        ],
        "star": [
            ".stars",
            ".star-rating",
            ".rating",
            "[class*='star-rating' i]",
            "[class*='star_rating' i]",
            "[aria-label*='rating' i]",
            "[aria-label*='stars' i]",
            "[class*='yotpo']",
            "[class*='stamped']",
            "[class*='loox']",
            "[class*='judge']",
            "[data-rating]",
            "svg[class*='star' i]",
        ],
        "rating": [
            ".rating",
            ".ratings",
            ".stars",
            ".review-score",
            "[class*='rating' i]",
            "[class*='star' i]",
            "[data-rating]",
        ],
        "review": [
            ".review",
            ".reviews",
            ".customer-review",
            "[class*='review' i]",
            "[class*='yotpo']",
            "[class*='stamped']",
            "[class*='loox']",
            "[class*='judge']",
            "[class*='trustpilot']",
        ],
        "social proof": [
            ".testimonial",
            ".testimonials",
            ".review",
            ".reviews",
            "[class*='testimonial' i]",
            "[class*='social-proof' i]",
            "[class*='proof' i]",
            "[class*='yotpo']",
            "[class*='stamped']",
            ".customer-review",
        ],
        "testimonial": [
            ".testimonial",
            ".testimonials",
            "[class*='testimonial' i]",
            ".customer-quote",
            ".customer-story",
        ],
        "trust": [
            ".trust",
            ".trust-badge",
            ".trust-badges",
            ".badge",
            ".badges",
            "[class*='trust' i]",
            "[class*='secure' i]",
            "[class*='guarantee' i]",
            "[alt*='trust' i]",
            "[alt*='secure' i]",
            "[alt*='guarantee' i]",
        ],
        "badge": [
            ".badge",
            ".badges",
            ".trust-badge",
            "[class*='badge' i]",
            "[alt*='badge' i]",
        ],
        "security": [
            ".secure",
            ".security",
            ".ssl",
            "[class*='secure' i]",
            "[class*='security' i]",
            "[class*='ssl' i]",
            "[alt*='secure' i]",
            "[alt*='ssl' i]",
            "[alt*='mcafee' i]",
            "[alt*='norton' i]",
        ],
        "cta": [
            "button[class*='primary' i]",
            "button[class*='cta' i]",
            "a[class*='cta' i]",
            ".cta",
            ".cta-button",
            "[class*='add-to-cart' i]",
            "[class*='buy-now' i]",
            "[class*='shop-now' i]",
            "[class*='get-started' i]",
        ],
        "call to action": [
            ".cta",
            ".cta-button",
            "button[class*='primary' i]",
            "[class*='cta' i]",
            "[class*='action' i]",
        ],
        "button": [
            "button",
            ".btn",
            ".button",
            "[role='button']",
            "a.btn",
            "[class*='btn' i]",
        ],
        "cart": [
            ".cart",
            ".cart-icon",
            ".shopping-cart",
            ".basket",
            ".bag",
            "[class*='cart' i]",
            "[class*='basket' i]",
            "[aria-label*='cart' i]",
            "[href*='cart']",
        ],
        "search": [
            "input[type='search']",
            ".search",
            ".search-form",
            ".search-box",
            "[aria-label*='search' i]",
            "[placeholder*='search' i]",
            "[name='q']",
            "[name='s']",
        ],
        "form": [
            "form",
            ".form",
            "[class*='form' i]",
            "input[type='email']",
            "input[type='tel']",
        ],
        "newsletter": [
            "[class*='newsletter' i]",
            "[class*='subscribe' i]",
            "[class*='signup' i]",
            "input[name*='email' i]",
            ".email-signup",
        ],
        "footer": [
            "footer",
            ".footer",
            "[role='contentinfo']",
            "#footer",
        ],
        "header": [
            "header",
            ".header",
            "[role='banner']",
            "#header",
        ],
        "logo": [
            ".logo",
            "[class*='logo' i]",
            "[alt*='logo' i]",
            "header img",
            ".brand",
        ],
        "price": [
            ".price",
            "[class*='price' i]",
            "[class*='cost' i]",
            "[class*='amount' i]",
            "[data-price]",
        ],
        "product": [
            ".product",
            "[class*='product' i]",
            ".item",
            "[class*='item' i]",
        ],
        "image": [
            "img",
            "picture",
            "[class*='image' i]",
            "[class*='img' i]",
            "[class*='photo' i]",
        ],
        "video": [
            "video",
            "iframe[src*='youtube']",
            "iframe[src*='vimeo']",
            "[class*='video' i]",
        ],
        "shipping": [
            "[class*='shipping' i]",
            "[class*='delivery' i]",
            "[alt*='shipping' i]",
            "[alt*='delivery' i]",
        ],
        "return": [
            "[class*='return' i]",
            "[class*='refund' i]",
            "[alt*='return' i]",
        ],
        "guarantee": [
            "[class*='guarantee' i]",
            "[class*='warranty' i]",
            "[alt*='guarantee' i]",
        ],
    }

    def __init__(self, page: Page):
        """
        Initialize the recommendation validator.

        Args:
            page: Playwright Page object
        """
        self.page = page

    async def validate_recommendations(
        self,
        issues: List[Dict[str, Any]],
        viewport: str = "desktop"
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate a list of CRO recommendations against the actual page.

        Args:
            issues: List of issue dictionaries from Claude's analysis
            viewport: "desktop" or "mobile" for logging purposes

        Returns:
            Tuple of (validated_issues, filtered_issues)
            - validated_issues: Issues that passed validation (kept)
            - filtered_issues: Issues identified as false positives (removed)
        """
        logger.info(f"🔍 Validating {len(issues)} recommendations for {viewport} viewport")

        validated = []
        filtered = []

        for issue in issues:
            validation_result = await self._validate_issue(issue)
            issue["validation"] = validation_result

            if validation_result.get("should_filter", False):
                filtered.append(issue)
                logger.info(
                    f"❌ Filtered false positive: '{issue.get('title', 'Unknown')}' - "
                    f"{validation_result.get('reason', 'No reason')}"
                )
            else:
                validated.append(issue)
                logger.debug(
                    f"✅ Kept recommendation: '{issue.get('title', 'Unknown')}' - "
                    f"{validation_result.get('status', 'Unknown status')}"
                )

        logger.info(
            f"📊 Validation complete: {len(validated)} kept, {len(filtered)} filtered"
        )

        return validated, filtered

    async def _validate_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single CRO issue/recommendation.

        Args:
            issue: Issue dictionary with title, description, recommendations

        Returns:
            Validation result dictionary
        """
        # Combine all text fields for analysis
        title = issue.get("title", "")
        description = issue.get("description", "")
        recommendations = issue.get("recommendations", [])
        if isinstance(recommendations, list):
            recommendations_text = " ".join(recommendations)
        else:
            recommendations_text = str(recommendations)

        full_text = f"{title} {description} {recommendations_text}".lower()

        # FIRST: Check for subjective quality/clarity claims that need AI validation
        # These claims like "doesn't clearly communicate" cannot be verified by Playwright
        is_quality_claim = self._is_quality_claim(full_text)

        if is_quality_claim:
            # Find which quality keyword matched for logging
            matched_quality_keyword = next(
                (kw for kw in self.QUALITY_CLAIM_KEYWORDS if kw in full_text),
                "unknown"
            )
            return {
                "status": "uncertain",
                "reason": f"Subjective quality/clarity claim detected ('{matched_quality_keyword}') - needs AI verification",
                "claim_type": "quality",
                "matched_keyword": matched_quality_keyword,
                "should_filter": False,
                "needs_ai_validation": True,  # Route to Layer 3 AI validation
            }

        # SECOND: Check if this is a "missing element" claim
        is_missing_claim = self._is_missing_element_claim(full_text)

        if not is_missing_claim:
            return {
                "status": "not_applicable",
                "reason": "Not a missing element or quality claim",
                "should_filter": False,
                "needs_ai_validation": False,
            }

        # Identify which element type is being claimed as missing
        element_type, matched_keyword = self._identify_element_type(full_text)

        if not element_type:
            return {
                "status": "uncertain",
                "reason": "Missing claim detected but element type unclear",
                "should_filter": False,
                "needs_ai_validation": True,  # Pass to AI validator
            }

        # Search for the element on the page
        element_found, selector_matched, count = await self._search_for_element(element_type)

        if element_found:
            return {
                "status": "false_positive",
                "reason": f"Element '{element_type}' exists ({count} found with '{selector_matched}')",
                "element_type": element_type,
                "matched_keyword": matched_keyword,
                "selector_matched": selector_matched,
                "element_count": count,
                "should_filter": True,
                "needs_ai_validation": False,
            }

        return {
            "status": "verified",
            "reason": f"Element '{element_type}' genuinely appears missing",
            "element_type": element_type,
            "matched_keyword": matched_keyword,
            "should_filter": False,
            "needs_ai_validation": False,
        }

    def _is_missing_element_claim(self, text: str) -> bool:
        """
        Check if the text contains a claim about missing elements.

        Args:
            text: Combined text from issue fields (lowercase)

        Returns:
            True if this appears to be a "missing element" recommendation
        """
        return any(keyword in text for keyword in self.MISSING_KEYWORDS)

    def _is_quality_claim(self, text: str) -> bool:
        """
        Check if the text contains a subjective quality/clarity claim.

        These claims cannot be verified by Playwright and need AI validation.
        Examples: "doesn't clearly communicate", "generic", "vague"

        Args:
            text: Combined text from issue fields (lowercase)

        Returns:
            True if this appears to be a subjective quality/clarity claim
        """
        return any(keyword in text for keyword in self.QUALITY_CLAIM_KEYWORDS)

    def _identify_element_type(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Identify which element type is being claimed as missing.

        Args:
            text: Combined text from issue fields (lowercase)

        Returns:
            Tuple of (element_type, matched_keyword) or (None, None)
        """
        for element_type in self.VALIDATION_RULES.keys():
            if element_type in text:
                return element_type, element_type

        return None, None

    async def _search_for_element(
        self,
        element_type: str
    ) -> Tuple[bool, Optional[str], int]:
        """
        Search the page for a specific element type.

        Args:
            element_type: The type of element to search for

        Returns:
            Tuple of (found, matched_selector, count)
        """
        selectors = self.VALIDATION_RULES.get(element_type, [])

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()

                if count > 0:
                    # Verify at least one is visible
                    for i in range(min(count, 5)):  # Check up to 5 elements
                        try:
                            element = locator.nth(i)
                            if await element.is_visible():
                                return True, selector, count
                        except:
                            continue

                    # Elements exist but none visible - still count as found
                    # (could be mobile-only or hidden by responsive CSS)
                    return True, selector, count

            except Exception as e:
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue

        return False, None, 0


async def validate_issues_both_viewports(
    page: Page,
    issues: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Validate issues at both desktop and mobile viewports.

    Args:
        page: Playwright Page object
        issues: List of issue dictionaries from Claude's analysis

    Returns:
        Tuple of (validated_issues, filtered_issues, validation_stats)
    """
    validator = RecommendationValidator(page)

    # Get current viewport
    original_viewport = page.viewport_size

    # Validate at desktop viewport (assume current is desktop)
    validated_desktop, filtered_desktop = await validator.validate_recommendations(
        issues, viewport="desktop"
    )

    # If we filtered anything, also check mobile viewport
    # Some elements might only be visible on mobile (hamburger menus)
    if filtered_desktop:
        # Switch to mobile viewport
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(500)  # Wait for responsive CSS

        # Re-validate filtered issues at mobile viewport
        revalidated = []
        still_filtered = []

        for issue in filtered_desktop:
            validation = await validator._validate_issue(issue)

            if validation.get("status") == "false_positive":
                # Still a false positive at mobile - keep filtered
                still_filtered.append(issue)
            else:
                # Element found at mobile viewport - restore the issue
                issue["validation"] = {
                    "status": "restored_mobile",
                    "reason": "Element found at mobile viewport",
                    "original_filter_reason": issue.get("validation", {}).get("reason"),
                    "should_filter": False,
                }
                revalidated.append(issue)
                logger.info(
                    f"↩️ Restored issue (mobile): '{issue.get('title', 'Unknown')}'"
                )

        # Restore original viewport
        if original_viewport:
            await page.set_viewport_size(original_viewport)

        # Combine results
        validated_issues = validated_desktop + revalidated
        filtered_issues = still_filtered
    else:
        validated_issues = validated_desktop
        filtered_issues = filtered_desktop

    # Build stats
    stats = {
        "total_issues": len(issues),
        "validated_count": len(validated_issues),
        "filtered_count": len(filtered_issues),
        "filter_rate": len(filtered_issues) / len(issues) if issues else 0,
        "needs_ai_validation": [
            i for i in validated_issues
            if i.get("validation", {}).get("needs_ai_validation", False)
        ],
    }

    return validated_issues, filtered_issues, stats
