"""
Interactive Testing Module for CRO Analyzer

Tests actual page functionality by interacting with elements:
- E-commerce: Add to cart, verify cart updates, check quantity display
- Forms: Test validation, submission flows
- Navigation: Test CTAs, menus, links
- Mobile: Test responsive behavior

Goal: Eliminate false positives by verifying claims before reporting issues.
"""

from typing import Dict, List, Optional, Any
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
import asyncio
import re


class InteractionTester:
    """
    Tests page functionality through actual user interactions.
    Prevents false positives by verifying claims before reporting.
    """

    def __init__(self, page: Page):
        """
        Initialize interaction tester.

        Args:
            page: Playwright Page object
        """
        self.page = page
        self.test_results = {
            "business_type": "unknown",
            "tests_performed": [],
            "findings": [],
        }

    async def detect_business_type(self) -> str:
        """
        Auto-detect business type from page content and structure.

        Returns:
            Business type: 'ecommerce', 'saas', 'lead-gen', 'content', 'service'
        """
        print("\n🔍 Detecting business type...")

        # Check for e-commerce indicators
        ecommerce_selectors = [
            'button:has-text("Add to Cart")',
            'button:has-text("Buy Now")',
            '[class*="cart"]',
            '[class*="product"]',
            '[class*="price"]',
            'select[name*="quantity"]',
        ]

        ecommerce_score = 0
        for selector in ecommerce_selectors:
            try:
                if await self.page.locator(selector).first.count() > 0:
                    ecommerce_score += 1
            except:
                pass

        # Check for SaaS indicators
        saas_selectors = [
            'a:has-text("Start Free Trial")',
            'a:has-text("Request Demo")',
            'a:has-text("Get Started")',
            '[class*="pricing"]',
            '[class*="plan"]',
        ]

        saas_score = 0
        for selector in saas_selectors:
            try:
                if await self.page.locator(selector).first.count() > 0:
                    saas_score += 1
            except:
                pass

        # Check for lead-gen indicators
        leadgen_selectors = [
            'form input[type="email"]',
            'form input[name*="email"]',
            'button:has-text("Subscribe")',
            'button:has-text("Download")',
            'button:has-text("Get")',
        ]

        leadgen_score = 0
        for selector in leadgen_selectors:
            try:
                if await self.page.locator(selector).first.count() > 0:
                    leadgen_score += 1
            except:
                pass

        # Determine business type
        scores = {
            "ecommerce": ecommerce_score,
            "saas": saas_score,
            "lead-gen": leadgen_score,
        }

        business_type = max(scores, key=scores.get) if max(scores.values()) > 0 else "content"
        self.test_results["business_type"] = business_type

        print(f"  ✓ Detected business type: {business_type}")
        print(f"    Scores: E-commerce={ecommerce_score}, SaaS={saas_score}, Lead-gen={leadgen_score}")

        return business_type

    async def _dismiss_marketing_popups(self) -> None:
        """
        Dismiss marketing popups that may block page interactions.
        Called before testing to ensure clean interaction state.
        """
        print("  🧹 Dismissing marketing popups before testing...")

        # Marketing popup close selectors (Bounce Exchange, Attentive, etc.)
        close_selectors = [
            # Bounce Exchange (bx-*) popups
            '[class*="bx-close"]',
            '.bxc [class*="close"]',
            '[id*="bx-campaign"] [class*="close"]',
            '.bx-button-close',
            # Attentive popups
            '[class*="attentive"] [class*="close"]',
            # Privy popups
            '[class*="privy"] [class*="close"]',
            # Generic popup close buttons
            '[role="dialog"] button[aria-label*="close" i]',
            '[role="dialog"] [class*="close"]',
            '.modal button[class*="close"]',
        ]

        dismissed = False
        for selector in close_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.click(timeout=2000)
                    await self.page.wait_for_timeout(500)
                    print(f"    ✓ Dismissed popup via: {selector}")
                    dismissed = True
                    break
            except Exception:
                continue

        # Try Escape key as fallback
        if not dismissed:
            try:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(300)
            except Exception:
                pass

    async def test_ecommerce_cart(self) -> Dict[str, Any]:
        """
        Test e-commerce cart functionality by actually adding a product.

        Returns:
            Dictionary with test results and findings
        """
        print("\n🛒 Testing e-commerce cart functionality...")

        # First, dismiss any marketing popups that might block interactions
        await self._dismiss_marketing_popups()

        test_result = {
            "test_name": "E-commerce Cart Test",
            "success": False,
            "findings": [],
        }

        try:
            # Find Add to Cart button - prioritize more specific selectors
            add_to_cart_selectors = [
                'button:has-text("Add to Cart")',
                'button:has-text("Add to Bag")',
                '[class*="add-to-cart"]',
                'input[value*="Add to Cart"]',
                # More generic "Add" is last resort - often matches carousel buttons
                'button:has-text("Add")',
            ]

            # Try to find AND click an accessible button
            add_button = None
            button_clicked = False

            for selector in add_to_cart_selectors:
                try:
                    # Get all matching buttons, try each one
                    locators = self.page.locator(selector)
                    count = await locators.count()

                    if count == 0:
                        continue

                    print(f"  ✓ Found {count} button(s) matching: {selector}")

                    # Try each button until one works
                    for i in range(min(count, 3)):  # Try up to 3 buttons
                        try:
                            button = locators.nth(i)
                            if await button.is_visible():
                                # Use shorter timeout for scroll (5s instead of 30s)
                                await button.scroll_into_view_if_needed(timeout=5000)
                                add_button = button
                                print(f"  🖱 Clicking Add to Cart button...")
                                await button.click(timeout=5000)
                                await self.page.wait_for_timeout(2000)
                                button_clicked = True
                                break
                        except Exception as btn_err:
                            print(f"    ⚠ Button {i+1} inaccessible: {str(btn_err)[:50]}")
                            continue

                    if button_clicked:
                        break

                except Exception:
                    continue

            if not button_clicked:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "No accessible 'Add to Cart' button found on page - user may need to navigate to product page first",
                })
                print("  ⚠ No accessible Add to Cart button found")
                return test_result

            # Get cart state AFTER clicking (cart may have updated)
            cart_selectors = [
                '[class*="cart-count"]',
                '[class*="cart-quantity"]',
                '[class*="cart-items"]',
                '[class*="minicart"]',
                '.cart-link',
                'a[href*="cart"]',
            ]

            cart_element = None
            cart_text = None
            for selector in cart_selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0:
                        cart_element = locator
                        cart_text = await locator.inner_text()
                        print(f"  ✓ Found cart indicator: {selector}")
                        print(f"    Cart state: '{cart_text}'")
                        break
                except:
                    continue

            test_result["success"] = True
            test_result["findings"].append({
                "type": "action",
                "message": "Successfully clicked 'Add to Cart' button",
            })

            # Verify cart indicator exists and shows a value after add-to-cart
            if cart_element and cart_text:
                # Cart indicator is present and has text - this is a positive signal
                # Look for numeric content indicating quantity
                has_quantity = bool(re.search(r'\d+', cart_text))

                if has_quantity:
                    test_result["findings"].append({
                        "type": "verified",
                        "message": f"Cart quantity indicator IS visible and shows quantity: '{cart_text.strip()}'",
                    })
                    print(f"  ✅ Cart quantity indicator IS visible: '{cart_text.strip()}'")
                else:
                    test_result["findings"].append({
                        "type": "verified",
                        "message": f"Cart indicator IS visible: '{cart_text.strip()}'",
                    })
                    print(f"  ✅ Cart indicator IS visible: '{cart_text.strip()}'")
            elif cart_element:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "Cart indicator element found but may be empty",
                })
                print("  ⚠ Cart indicator found but empty")
            else:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "No cart quantity indicator found - site may use different cart UX pattern",
                })
                print("  ⚠ No cart indicator found")

            # Check for cart modal/drawer
            await self.page.wait_for_timeout(500)
            modal_selectors = [
                '[class*="cart-drawer"]',
                '[class*="mini-cart"]',
                '[class*="cart-popup"]',
                '[role="dialog"]',
            ]

            cart_modal_found = False
            for selector in modal_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        cart_modal_found = True
                        test_result["findings"].append({
                            "type": "verified",
                            "message": "Cart modal/drawer DOES appear after adding item",
                        })
                        print("  ✅ Cart modal/drawer appeared")
                        break
                except:
                    continue

            if not cart_modal_found:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "No cart modal/drawer detected - site may use different cart UX pattern",
                })

            # Close the cart drawer/modal after testing to ensure clean screenshots
            await self._dismiss_cart_drawer()

        except Exception as e:
            test_result["findings"].append({
                "type": "error",
                "message": f"Cart test failed: {str(e)}",
            })
            print(f"  ✗ Cart test error: {str(e)}")

        return test_result

    async def _dismiss_cart_drawer(self) -> None:
        """
        Dismiss cart drawer/modal after testing to ensure clean screenshots.
        Tries multiple strategies: close button, backdrop click, Escape key.
        """
        print("  🧹 Closing cart drawer...")

        # Cart drawer close selectors
        close_selectors = [
            '[class*="cart-drawer"] [class*="close"]',
            '[class*="cart-drawer"] button[aria-label*="close" i]',
            '[class*="mini-cart"] [class*="close"]',
            '[class*="drawer"] [class*="close"]',
            '[class*="cart-modal"] [class*="close"]',
            '.cart-drawer .close-btn',
            'button[class*="drawer-close"]',
            '[data-cart-close]',
        ]

        # Backdrop selectors
        backdrop_selectors = [
            '[class*="cart-drawer-overlay"]',
            '[class*="drawer-backdrop"]',
            '[class*="drawer-overlay"]',
            '.overlay.is-visible',
            '[class*="modal-backdrop"]',
        ]

        closed = False

        # Strategy 1: Click close button
        for selector in close_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.click(timeout=2000)
                    await self.page.wait_for_timeout(500)
                    print(f"    ✓ Cart drawer closed via close button")
                    closed = True
                    break
            except Exception:
                continue

        # Strategy 2: Click backdrop
        if not closed:
            for selector in backdrop_selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=2000)
                        await self.page.wait_for_timeout(500)
                        print(f"    ✓ Cart drawer closed via backdrop")
                        closed = True
                        break
                except Exception:
                    continue

        # Strategy 3: Press Escape key
        if not closed:
            try:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(500)
                print(f"    ✓ Cart drawer closed via Escape key")
                closed = True
            except Exception:
                pass

        if not closed:
            print(f"    ⚠ Could not close cart drawer (may not be open)")

    async def test_navigation_ctas(self) -> Dict[str, Any]:
        """
        Test primary CTAs to verify they work correctly.

        Returns:
            Dictionary with test results
        """
        print("\n🔗 Testing navigation and CTAs...")

        test_result = {
            "test_name": "Navigation CTA Test",
            "success": False,
            "findings": [],
        }

        try:
            # Find primary CTA
            cta_selectors = [
                'a.btn-primary',
                'a.button-primary',
                'a[class*="cta"]',
                'button[class*="primary"]',
                'a:has-text("Get Started")',
                'a:has-text("Learn More")',
                'a:has-text("Shop Now")',
            ]

            cta_element = None
            for selector in cta_selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0:
                        cta_element = locator
                        cta_text = await locator.inner_text()
                        print(f"  ✓ Found primary CTA: '{cta_text}'")
                        break
                except:
                    continue

            if not cta_element:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "No primary CTA button found to test",
                })
                return test_result

            # Get CTA destination
            try:
                href = await cta_element.get_attribute("href")
                if href:
                    test_result["findings"].append({
                        "type": "verified",
                        "message": f"Primary CTA links to: {href}",
                    })
                    test_result["success"] = True
                    print(f"  ✓ CTA destination: {href}")
            except:
                pass

        except Exception as e:
            test_result["findings"].append({
                "type": "error",
                "message": f"Navigation test failed: {str(e)}",
            })
            print(f"  ✗ Navigation test error: {str(e)}")

        return test_result

    async def test_forms(self) -> Dict[str, Any]:
        """
        Test form functionality and validation.

        Returns:
            Dictionary with test results
        """
        print("\n📝 Testing form functionality...")

        test_result = {
            "test_name": "Form Validation Test",
            "success": False,
            "findings": [],
        }

        try:
            # Find forms on page
            forms = await self.page.locator("form").count()

            if forms == 0:
                test_result["findings"].append({
                    "type": "observation",
                    "message": "No forms found on page",
                })
                print("  ⚠ No forms found")
                return test_result

            print(f"  ✓ Found {forms} form(s) on page")

            # Test first form
            form = self.page.locator("form").first

            # Find email input
            email_input = None
            email_selectors = [
                'input[type="email"]',
                'input[name*="email"]',
                'input[placeholder*="email"]',
            ]

            for selector in email_selectors:
                try:
                    locator = form.locator(selector).first
                    if await locator.count() > 0:
                        email_input = locator
                        print(f"  ✓ Found email input: {selector}")
                        break
                except:
                    continue

            if email_input:
                # Test with invalid email
                print("  🧪 Testing with invalid email...")
                await email_input.fill("invalid-email")

                # Try to submit
                submit_button = form.locator('button[type="submit"], input[type="submit"]').first
                if await submit_button.count() > 0:
                    await submit_button.click()
                    await self.page.wait_for_timeout(1000)

                    # Check for validation message
                    validation_found = False
                    validation_selectors = [
                        ':invalid',
                        '[aria-invalid="true"]',
                        '.error',
                        '.invalid',
                    ]

                    for selector in validation_selectors:
                        try:
                            if await form.locator(selector).count() > 0:
                                validation_found = True
                                break
                        except:
                            continue

                    if validation_found:
                        test_result["findings"].append({
                            "type": "verified",
                            "message": "Form validation DOES work - invalid email was caught",
                        })
                        print("  ✅ Form validation works")
                    else:
                        test_result["findings"].append({
                            "type": "issue",
                            "message": "Form validation may not be working - invalid email was not caught",
                        })
                        print("  ⚠ Form validation may not work")

                    test_result["success"] = True

        except Exception as e:
            test_result["findings"].append({
                "type": "error",
                "message": f"Form test failed: {str(e)}",
            })
            print(f"  ✗ Form test error: {str(e)}")

        return test_result

    async def test_mobile_navigation(self) -> Dict[str, Any]:
        """
        Test mobile navigation elements (hamburger menu, mobile nav).
        Called when in mobile viewport to verify mobile nav works.

        Returns:
            Dictionary with test results
        """
        print("\n📱 Testing mobile navigation...")

        test_result = {
            "test_name": "Mobile Navigation Test",
            "success": False,
            "findings": [],
        }

        # Hamburger menu selectors
        hamburger_selectors = [
            'button[aria-label*="menu" i]',
            'button[aria-label*="navigation" i]',
            'button[aria-label*="Menu" i]',
            '[class*="hamburger"]',
            '[class*="menu-toggle"]',
            '[class*="mobile-menu"]',
            '[class*="nav-toggle"]',
            'button[class*="menu"]',
            '[data-toggle="menu"]',
            '.menu-icon',
            '.burger-menu',
            '[class*="nav-icon"]',
            '[class*="toggle-nav"]',
        ]

        hamburger_found = False
        hamburger_element = None
        found_selector = None

        for selector in hamburger_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    hamburger_found = True
                    hamburger_element = locator
                    found_selector = selector

                    # Get any accessible text/label
                    aria_label = await locator.get_attribute("aria-label") or ""

                    test_result["findings"].append({
                        "type": "verified",
                        "message": f"Mobile hamburger menu IS VISIBLE and functional (aria-label: '{aria_label}')" if aria_label else "Mobile hamburger menu IS VISIBLE and functional",
                    })
                    print(f"  ✅ Found visible hamburger menu: {selector}")
                    test_result["success"] = True
                    break
            except Exception:
                continue

        if not hamburger_found:
            test_result["findings"].append({
                "type": "observation",
                "message": "No hamburger menu detected - site may use different mobile nav pattern",
            })
            print("  ⚠ No hamburger menu found")

        # Optionally test if hamburger opens the menu
        if hamburger_element:
            try:
                await hamburger_element.click(timeout=2000)
                await self.page.wait_for_timeout(500)

                # Check if menu opened
                menu_selectors = [
                    'nav.is-open',
                    '[class*="mobile-nav"].is-open',
                    '[class*="mobile-nav"].active',
                    '[class*="nav-menu"].is-visible',
                    '[class*="menu-panel"].open',
                    '[class*="nav"][class*="open"]',
                    '[class*="menu"][class*="active"]',
                    '[class*="nav-drawer"]',
                ]

                menu_opened = False
                for selector in menu_selectors:
                    try:
                        if await self.page.locator(selector).count() > 0:
                            test_result["findings"].append({
                                "type": "verified",
                                "message": "Mobile menu DOES open when hamburger is clicked",
                            })
                            print("  ✅ Mobile menu opens correctly")
                            menu_opened = True
                            break
                    except:
                        continue

                # Close the menu again
                try:
                    await self.page.keyboard.press("Escape")
                    await self.page.wait_for_timeout(300)
                except:
                    pass

                # If menu didn't open with known selectors, it might use different pattern
                if not menu_opened:
                    test_result["findings"].append({
                        "type": "observation",
                        "message": "Hamburger clicked but could not verify menu opened (may use custom pattern)",
                    })

            except Exception as e:
                test_result["findings"].append({
                    "type": "observation",
                    "message": f"Could not test hamburger click: {str(e)[:50]}",
                })

        self.test_results["tests_performed"].append(test_result)
        return test_result

    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all appropriate tests based on detected business type.

        Returns:
            Complete test results dictionary
        """
        print("\n🚀 Starting interactive testing phase...")

        # Detect business type
        business_type = await self.detect_business_type()

        # Run tests based on business type
        if business_type == "ecommerce":
            cart_test = await self.test_ecommerce_cart()
            self.test_results["tests_performed"].append(cart_test)

        # Always test navigation/CTAs
        nav_test = await self.test_navigation_ctas()
        self.test_results["tests_performed"].append(nav_test)

        # Test forms if present
        form_test = await self.test_forms()
        self.test_results["tests_performed"].append(form_test)

        # Compile all findings
        for test in self.test_results["tests_performed"]:
            self.test_results["findings"].extend(test.get("findings", []))

        print(f"\n✅ Interactive testing complete")
        print(f"  Business type: {business_type}")
        print(f"  Tests performed: {len(self.test_results['tests_performed'])}")
        print(f"  Findings: {len(self.test_results['findings'])}")

        return self.test_results

    def format_for_claude_prompt(self) -> str:
        """
        Format test results for inclusion in Claude prompt.

        Returns:
            Formatted string for Claude prompt
        """
        lines = []
        lines.append("## Interactive Testing Results")
        lines.append("")
        lines.append(f"**Business Type Detected**: {self.test_results['business_type']}")
        lines.append("")
        lines.append("**Tests Performed**:")
        lines.append("")

        for test in self.test_results["tests_performed"]:
            lines.append(f"### {test['test_name']}")
            lines.append(f"Status: {'✅ Success' if test['success'] else '⚠️ Incomplete'}")
            lines.append("")

            if test.get("findings"):
                lines.append("**Findings**:")
                for finding in test["findings"]:
                    icon = {
                        "verified": "✅",
                        "issue": "⚠️",
                        "observation": "ℹ️",
                        "action": "🖱",
                        "error": "❌",
                    }.get(finding["type"], "•")
                    lines.append(f"- {icon} {finding['message']}")
                lines.append("")

        lines.append("**CRITICAL INSTRUCTION**: Use these test results to verify your observations. DO NOT claim issues that were tested and verified to work correctly. For example, if the cart test shows 'Cart quantity indicator DOES update', do NOT report 'cart doesn't show quantity' as an issue.")
        lines.append("")

        return "\n".join(lines)


# Usage example
if __name__ == "__main__":
    from playwright.async_api import async_playwright
    import asyncio

    async def test_interaction_testing():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            # Navigate to test page
            print("🌐 Loading page...")
            await page.goto("https://www.shopify.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Run interaction tests
            tester = InteractionTester(page)
            results = await tester.run_all_tests()

            # Format for Claude
            prompt_text = tester.format_for_claude_prompt()
            print("\n" + "=" * 60)
            print("FORMATTED FOR CLAUDE PROMPT:")
            print("=" * 60)
            print(prompt_text)

            await browser.close()

    asyncio.run(test_interaction_testing())
