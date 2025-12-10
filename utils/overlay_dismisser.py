"""
Overlay Dismisser Module for CRO Analyzer

Detects and dismisses overlays (cart drawers, cookie banners, popups, modals, chat widgets)
before screenshot capture to prevent false positives in CRO analysis.

Goal: Ensure clean screenshots by dismissing all UI overlays that obscure page content.
"""

from typing import Dict, List, Any, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


class OverlayDismisser:
    """
    Detects and dismisses overlays before screenshot capture.
    Prevents false positives by ensuring page content is visible.
    """

    def __init__(self, page: Page):
        """
        Initialize overlay dismisser.

        Args:
            page: Playwright Page object
        """
        self.page = page
        self.results = {
            "overlays_detected": [],
            "overlays_dismissed": [],
            "dismissal_failed": [],
            "revealed_elements": [],
        }

    # Detection selectors for different overlay types
    OVERLAY_PATTERNS = {
        "cart_drawer": {
            "detection": [
                '[class*="cart-drawer"]',
                '[class*="cart-slide"]',
                '[class*="mini-cart"][class*="open"]',
                '[class*="minicart"][class*="active"]',
                '[class*="drawer"][class*="cart"]',
                '[class*="side-cart"]',
                '[class*="cart-modal"]',
                '.cart-drawer.is-open',
                '.drawer.is-open',
                '[data-cart-drawer]',
                '[id*="cart-drawer"]',
                '[id*="slide-cart"]',
            ],
            "close_selectors": [
                '[class*="cart-drawer"] [class*="close"]',
                '[class*="cart-drawer"] button[aria-label*="close" i]',
                '[class*="mini-cart"] [class*="close"]',
                '[class*="drawer"] [class*="close"]',
                '[class*="cart-drawer"] .close-btn',
                'button[class*="drawer-close"]',
            ],
            "backdrop_selectors": [
                '[class*="cart-drawer-overlay"]',
                '[class*="drawer-backdrop"]',
                '[class*="drawer-overlay"]',
                '.overlay.is-visible',
            ],
        },
        "cookie_banner": {
            "detection": [
                '[class*="cookie"]',
                '[class*="consent"]',
                '[class*="gdpr"]',
                '[class*="privacy-banner"]',
                '[id*="cookie"]',
                '[id*="consent"]',
                '[id*="gdpr"]',
                '[data-cookie-banner]',
                '[aria-label*="cookie" i]',
            ],
            "accept_selectors": [
                'button:has-text("Accept")',
                'button:has-text("Accept All")',
                'button:has-text("Accept Cookies")',
                'button:has-text("I Accept")',
                'button:has-text("Got It")',
                'button:has-text("OK")',
                'button:has-text("Allow")',
                'button:has-text("Agree")',
                '[class*="cookie"] button[class*="accept"]',
                '[class*="consent"] button[class*="accept"]',
                '[class*="cookie"] button[class*="primary"]',
            ],
            "close_selectors": [
                '[class*="cookie"] [class*="close"]',
                '[class*="consent"] [class*="close"]',
                '[class*="gdpr"] [class*="close"]',
            ],
        },
        "newsletter_popup": {
            "detection": [
                '[class*="newsletter"][class*="popup"]',
                '[class*="newsletter"][class*="modal"]',
                '[class*="email-popup"]',
                '[class*="subscribe-popup"]',
                '[class*="signup-modal"]',
                '.klaviyo-popup',
                '.klaviyo-form-modal',
                '[id*="newsletter-popup"]',
                '[id*="email-modal"]',
                '[data-popup-type="newsletter"]',
            ],
            "close_selectors": [
                '[class*="newsletter"] [class*="close"]',
                '[class*="newsletter"] button[aria-label*="close" i]',
                '[class*="popup"] [class*="close"]',
                '.klaviyo-close-form',
                '[class*="modal-close"]',
                'button[class*="popup-close"]',
            ],
        },
        "marketing_popup": {
            "detection": [
                # Bounce Exchange (bx-*) popups
                '[class*="bxc"][class*="bx-active"]',
                '[class*="bx-type-overlay"]',
                '[id*="bx-campaign"]',
                '.bxc.bx-impress',
                # Attentive popups
                '[class*="attentive"]',
                '#attentive_overlay',
                # Privy popups
                '[class*="privy"]',
                '#privy-popup',
                # OptinMonster
                '[class*="optinmonster"]',
                '#om-popup',
                # Generic marketing popups
                '[class*="popup-overlay"][class*="visible"]',
                '[class*="promo-popup"]',
                '[class*="exit-intent"]',
            ],
            "close_selectors": [
                # Bounce Exchange close buttons
                '[class*="bx-close"]',
                '.bxc [class*="close"]',
                '[id*="bx-campaign"] [class*="close"]',
                '.bx-button-close',
                # Generic close buttons
                '[class*="attentive"] [class*="close"]',
                '[class*="privy"] [class*="close"]',
                '[class*="optinmonster"] [class*="close"]',
                '[class*="popup"] button[aria-label*="close" i]',
                '[class*="popup"] .close-icon',
            ],
            "backdrop_selectors": [
                '.bx-slab',
                '[class*="popup-backdrop"]',
                '[class*="popup-overlay"]',
            ],
        },
        "chat_widget": {
            "detection": [
                '[class*="intercom"]',
                '[class*="drift"]',
                '[class*="zendesk"]',
                '[class*="freshchat"]',
                '[class*="crisp"]',
                '[class*="tawk"]',
                '[class*="hubspot-messages"]',
                '[class*="chat-widget"]',
                '[id*="intercom"]',
                '[id*="drift"]',
                '[id*="zendesk-chat"]',
                'iframe[title*="chat" i]',
            ],
            "minimize_selectors": [
                '[class*="intercom"] [class*="close"]',
                '[class*="drift"] [class*="close"]',
                '[class*="chat-widget"] [class*="minimize"]',
            ],
        },
        "generic_modal": {
            "detection": [
                '[role="dialog"]:not([aria-hidden="true"])',
                '.modal.show',
                '.modal.is-open',
                '.modal.active',
                '[class*="modal"][class*="open"]',
                '[class*="modal"][class*="visible"]',
                '[class*="lightbox"][class*="open"]',
                '[class*="popup"][class*="active"]',
                '[data-modal-open="true"]',
            ],
            "close_selectors": [
                '[role="dialog"] button[aria-label*="close" i]',
                '[role="dialog"] [class*="close"]',
                '.modal button[class*="close"]',
                '.modal [class*="close-btn"]',
                '.modal-close',
                'button[data-dismiss="modal"]',
            ],
            "backdrop_selectors": [
                '.modal-backdrop',
                '.modal-overlay',
                '[class*="overlay"][class*="modal"]',
            ],
        },
    }

    # Elements to verify are visible after dismissal
    VERIFY_ELEMENTS = {
        "cart_badge": [
            '[class*="cart-count"]',
            '[class*="cart-quantity"]',
            '[class*="cart-items"]',
            '[class*="cart-badge"]',
            '.cart-count',
            '[data-cart-count]',
        ],
        "navigation": [
            'nav',
            '[role="navigation"]',
            'header nav',
        ],
        "hero_cta": [
            'a.btn-primary',
            'a.button-primary',
            '[class*="hero"] a[class*="btn"]',
            '[class*="hero"] button',
        ],
        "header": [
            'header',
            '[role="banner"]',
        ],
        # Mobile-specific elements for hamburger menu verification
        "mobile_nav_toggle": [
            # Hamburger menu icons with aria-labels
            'button[aria-label*="menu" i]',
            'button[aria-label*="navigation" i]',
            'button[aria-label*="Menu" i]',
            # Class-based hamburger patterns
            '[class*="hamburger"]',
            '[class*="menu-toggle"]',
            '[class*="mobile-menu"]',
            '[class*="nav-toggle"]',
            'button[class*="menu"]',
            '[data-toggle="menu"]',
            '.menu-icon',
            '.burger-menu',
            # Mobile-specific nav containers
            '[class*="mobile-nav"]',
            '[class*="mobile-header"]',
            # Common icon patterns
            '[class*="nav-icon"]',
            '[class*="toggle-nav"]',
        ],
        "mobile_search": [
            '[class*="search-icon"]',
            'button[aria-label*="search" i]',
            '[class*="mobile"] [class*="search"]',
            '[class*="header"] [class*="search"]',
        ],
        "mobile_cart_icon": [
            '[class*="header"] [class*="cart"]',
            'a[href*="cart"]',
            '[aria-label*="cart" i]',
            '[class*="cart-icon"]',
        ],
    }

    async def dismiss_all_overlays(self) -> Dict[str, Any]:
        """
        Detect and dismiss all overlay types.

        Returns:
            Dictionary with dismissal results and revealed elements
        """
        print("\n🧹 Dismissing overlays for clean screenshots...")

        # Try each overlay type
        for overlay_type, patterns in self.OVERLAY_PATTERNS.items():
            await self._handle_overlay_type(overlay_type, patterns)

        # Wait for animations to complete
        await self.page.wait_for_timeout(500)

        # Try pressing Escape as final cleanup
        try:
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
        except Exception:
            pass

        # Verify what elements are now visible
        await self._verify_revealed_elements()

        # Summary
        print(f"  ✓ Detected: {len(self.results['overlays_detected'])} overlays")
        print(f"  ✓ Dismissed: {len(self.results['overlays_dismissed'])} overlays")
        print(f"  ✓ Revealed: {len(self.results['revealed_elements'])} key elements")

        if self.results["dismissal_failed"]:
            print(f"  ⚠ Failed to dismiss: {len(self.results['dismissal_failed'])} overlays")

        return self.results

    async def _handle_overlay_type(
        self, overlay_type: str, patterns: Dict[str, List[str]]
    ) -> bool:
        """
        Handle a specific overlay type.

        Args:
            overlay_type: Type of overlay (cart_drawer, cookie_banner, etc.)
            patterns: Detection and dismissal patterns

        Returns:
            True if overlay was found and dismissed
        """
        # Check if overlay is present
        overlay_found = False
        for selector in patterns.get("detection", []):
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0:
                    # Check if visible
                    if await locator.is_visible():
                        overlay_found = True
                        self.results["overlays_detected"].append({
                            "type": overlay_type,
                            "selector": selector,
                        })
                        print(f"  🔍 Detected {overlay_type}: {selector}")
                        break
            except Exception:
                continue

        if not overlay_found:
            return False

        # Try to dismiss
        dismissed = False

        # Strategy 1: Click accept button (for cookie banners)
        if "accept_selectors" in patterns:
            for selector in patterns["accept_selectors"]:
                if await self._try_click(selector, f"{overlay_type} accept"):
                    dismissed = True
                    break

        # Strategy 2: Click close button
        if not dismissed and "close_selectors" in patterns:
            for selector in patterns["close_selectors"]:
                if await self._try_click(selector, f"{overlay_type} close"):
                    dismissed = True
                    break

        # Strategy 3: Click backdrop
        if not dismissed and "backdrop_selectors" in patterns:
            for selector in patterns["backdrop_selectors"]:
                if await self._try_click(selector, f"{overlay_type} backdrop"):
                    dismissed = True
                    break

        # Strategy 4: Click minimize (for chat widgets)
        if not dismissed and "minimize_selectors" in patterns:
            for selector in patterns["minimize_selectors"]:
                if await self._try_click(selector, f"{overlay_type} minimize"):
                    dismissed = True
                    break

        # Strategy 5: Press Escape
        if not dismissed:
            try:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(300)
                # Check if still visible
                for selector in patterns.get("detection", []):
                    try:
                        locator = self.page.locator(selector).first
                        if await locator.count() > 0 and not await locator.is_visible():
                            dismissed = True
                            print(f"  ✓ Dismissed {overlay_type} via Escape key")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # Strategy 6: Hide via JavaScript (for stubborn chat widgets)
        if not dismissed and overlay_type == "chat_widget":
            dismissed = await self._hide_via_js(patterns.get("detection", []))

        if dismissed:
            self.results["overlays_dismissed"].append({
                "type": overlay_type,
            })
        else:
            self.results["dismissal_failed"].append({
                "type": overlay_type,
            })

        return dismissed

    async def _try_click(self, selector: str, description: str) -> bool:
        """
        Try to click an element.

        Args:
            selector: CSS selector to click
            description: Description for logging

        Returns:
            True if click succeeded
        """
        try:
            locator = self.page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible():
                await locator.click(timeout=2000)
                await self.page.wait_for_timeout(500)
                print(f"  ✓ Dismissed via {description}")
                return True
        except Exception:
            pass
        return False

    async def _hide_via_js(self, detection_selectors: List[str]) -> bool:
        """
        Hide element via JavaScript as last resort.

        Args:
            detection_selectors: Selectors to try hiding

        Returns:
            True if successfully hidden
        """
        for selector in detection_selectors:
            try:
                await self.page.evaluate(f"""
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                    }}
                """)
                print(f"  ✓ Hidden via JavaScript: {selector}")
                return True
            except Exception:
                continue
        return False

    async def _verify_revealed_elements(self) -> None:
        """
        Verify which key elements are visible after dismissal.
        """
        print("\n  🔎 Verifying revealed elements...")

        for element_name, selectors in self.VERIFY_ELEMENTS.items():
            for selector in selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0:
                        is_visible = await locator.is_visible()
                        if is_visible:
                            # Get text content if available
                            text = ""
                            try:
                                text = await locator.inner_text()
                                text = text.strip()[:50]  # Limit length
                            except Exception:
                                pass

                            self.results["revealed_elements"].append({
                                "element": element_name,
                                "selector": selector,
                                "visible": True,
                                "text": text if text else None,
                            })
                            print(f"    ✓ {element_name}: VISIBLE" + (f" ({text})" if text else ""))
                            break
                except Exception:
                    continue

    def format_for_claude_prompt(self) -> str:
        """
        Format dismissal results for inclusion in Claude prompt.

        Returns:
            Formatted string for Claude prompt
        """
        lines = []
        lines.append("## Overlay Dismissal Results")
        lines.append("")

        if self.results["overlays_detected"]:
            lines.append("**Overlays Detected and Handled**:")
            for overlay in self.results["overlays_detected"]:
                status = "DISMISSED" if overlay["type"] in [d["type"] for d in self.results["overlays_dismissed"]] else "FAILED"
                lines.append(f"- {overlay['type']}: {status}")
            lines.append("")

        if self.results["revealed_elements"]:
            lines.append("**Verified Visible Elements** (DO NOT report these as missing):")
            for element in self.results["revealed_elements"]:
                text_info = f" - shows '{element['text']}'" if element.get("text") else ""
                lines.append(f"- {element['element']}: VISIBLE{text_info}")
            lines.append("")

        lines.append("**CRITICAL INSTRUCTION**: Elements listed above as VISIBLE have been verified after all overlays were dismissed. DO NOT report these elements as 'missing', 'hidden', or 'not visible'. Trust this verification data.")
        lines.append("")

        return "\n".join(lines)


# Convenience function for tasks.py
async def dismiss_overlays_before_screenshot(page: Page) -> Dict[str, Any]:
    """
    Convenience function to dismiss overlays before taking screenshots.

    Args:
        page: Playwright Page object

    Returns:
        Overlay dismissal results
    """
    dismisser = OverlayDismisser(page)
    return await dismisser.dismiss_all_overlays()
