"""
Section Detector for CRO Analyzer

Intelligently detects webpage sections for targeted screenshot capture and analysis.
Uses viewport position, DOM structure, and visual cues to identify:
- Navigation
- Hero/Above-the-fold
- Product Page elements
- Forms
- Footer
- etc.
"""

from typing import List, Dict, Optional
from playwright.async_api import Page, ElementHandle
import asyncio


class Section:
    """Represents a detected section of a webpage."""

    def __init__(
        self,
        name: str,
        selector: str,
        y_position: float,
        height: float,
        description: str = ""
    ):
        self.name = name
        self.selector = selector
        self.y_position = y_position
        self.height = height
        self.description = description

    def __repr__(self):
        return f"<Section '{self.name}' at y={self.y_position}px height={self.height}px>"

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'selector': self.selector,
            'y_position': self.y_position,
            'height': self.height,
            'description': self.description
        }


class SectionDetector:
    """
    Detects webpage sections using heuristics and DOM analysis.

    Detection strategy:
    1. Above-the-fold (Hero): First viewport height (0-800px typically)
    2. Navigation: Top sticky/fixed elements, <nav>, <header>
    3. Product Page: Product images, pricing, add-to-cart
    4. Forms: <form> elements, input fields
    5. Footer: Bottom <footer> elements
    6. Content sections: H1, H2 headings that divide content
    """

    def __init__(self, page: Page):
        self.page = page

    async def detect_sections(self) -> List[Section]:
        """
        Detect all major sections on the current page.

        Returns:
            List of Section objects ordered by position on page
        """
        sections = []

        # Get viewport dimensions
        viewport_height = await self.page.evaluate("window.innerHeight")

        # Detect navigation
        nav_section = await self._detect_navigation()
        if nav_section:
            sections.append(nav_section)

        # Detect hero/above-the-fold
        hero_section = Section(
            name="Hero",
            selector="viewport_top",
            y_position=0,
            height=viewport_height,
            description="Above-the-fold hero section"
        )
        sections.append(hero_section)

        # Detect product page elements (if present)
        product_sections = await self._detect_product_page()
        sections.extend(product_sections)

        # Detect forms
        form_sections = await self._detect_forms()
        sections.extend(form_sections)

        # Detect content sections by headings
        heading_sections = await self._detect_heading_sections()
        sections.extend(heading_sections)

        # Detect footer
        footer_section = await self._detect_footer()
        if footer_section:
            sections.append(footer_section)

        # Sort by y_position
        sections.sort(key=lambda s: s.y_position)

        print(f"✓ Detected {len(sections)} sections on page")
        for section in sections:
            print(f"  - {section.name} at {section.y_position}px")

        return sections

    async def _detect_navigation(self) -> Optional[Section]:
        """Detect navigation section."""
        # Try multiple selectors for navigation
        nav_selectors = [
            'nav',
            'header',
            '[role="navigation"]',
            '.navigation',
            '.navbar',
            '.header',
            '#navigation',
            '#navbar'
        ]

        for selector in nav_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    box = await element.bounding_box()
                    if box:
                        return Section(
                            name="Navigation",
                            selector=selector,
                            y_position=box['y'],
                            height=box['height'],
                            description="Main navigation menu"
                        )
            except:
                continue

        return None

    async def _detect_product_page(self) -> List[Section]:
        """Detect product page specific elements."""
        sections = []

        # Check if this is a product page
        is_product_page = await self.page.evaluate("""
            () => {
                const indicators = [
                    document.querySelector('[itemprop="product"]'),
                    document.querySelector('.product'),
                    document.querySelector('[data-product]'),
                    document.querySelector('button[type="submit"][name="add"]'),
                    document.querySelector('.add-to-cart'),
                    document.querySelector('.product-price')
                ];
                return indicators.some(el => el !== null);
            }
        """)

        if not is_product_page:
            return sections

        # Product image gallery
        gallery_selectors = [
            '.product-images',
            '.product-gallery',
            '[class*="product"][class*="image"]',
            '.gallery',
            '[data-product-images]'
        ]

        for selector in gallery_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    box = await element.bounding_box()
                    if box:
                        sections.append(Section(
                            name="Product Gallery",
                            selector=selector,
                            y_position=box['y'],
                            height=box['height'],
                            description="Product image gallery"
                        ))
                        break
            except:
                continue

        # Product details/pricing
        details_selectors = [
            '.product-details',
            '.product-info',
            '[class*="product"][class*="detail"]',
            '.product-price'
        ]

        for selector in details_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    box = await element.bounding_box()
                    if box:
                        sections.append(Section(
                            name="Product Details",
                            selector=selector,
                            y_position=box['y'],
                            height=box['height'],
                            description="Product details and pricing"
                        ))
                        break
            except:
                continue

        return sections

    async def _detect_forms(self) -> List[Section]:
        """Detect form sections."""
        sections = []

        # Find all forms
        forms = await self.page.query_selector_all('form')

        for i, form in enumerate(forms):
            try:
                box = await form.bounding_box()
                if box and box['height'] > 50:  # Filter out tiny forms
                    # Try to determine form purpose
                    form_name = await self._identify_form_purpose(form)

                    sections.append(Section(
                        name=form_name,
                        selector=f'form:nth-of-type({i+1})',
                        y_position=box['y'],
                        height=box['height'],
                        description=f"Form for {form_name.lower()}"
                    ))
            except:
                continue

        return sections

    async def _identify_form_purpose(self, form: ElementHandle) -> str:
        """Try to identify the purpose of a form."""
        # Get form attributes and nearby text
        form_info = await form.evaluate("""
            (el) => {
                return {
                    id: el.id,
                    class: el.className,
                    action: el.action,
                    innerHTML: el.innerHTML.toLowerCase().substring(0, 500)
                };
            }
        """)

        # Check for keywords
        content = (form_info.get('id', '') + ' ' +
                   form_info.get('class', '') + ' ' +
                   form_info.get('innerHTML', '')).lower()

        if any(word in content for word in ['search', 'query']):
            return "Search Form"
        elif any(word in content for word in ['contact', 'email', 'message']):
            return "Contact Form"
        elif any(word in content for word in ['newsletter', 'subscribe', 'signup']):
            return "Newsletter Form"
        elif any(word in content for word in ['login', 'signin', 'sign in']):
            return "Login Form"
        elif any(word in content for word in ['register', 'signup', 'sign up', 'create account']):
            return "Registration Form"
        elif any(word in content for word in ['checkout', 'payment', 'billing']):
            return "Checkout Form"
        else:
            return "Form"

    async def _detect_heading_sections(self) -> List[Section]:
        """Detect major content sections by H1/H2 headings."""
        sections = []

        # Get all H1 and H2 elements
        headings = await self.page.query_selector_all('h1, h2')

        for heading in headings:
            try:
                box = await heading.bounding_box()
                text = await heading.inner_text()

                if box and text and len(text.strip()) > 0:
                    # Clean up heading text for section name
                    section_name = text.strip()[:50]  # Limit length

                    # Skip if this is likely a subheading or small section
                    if box['y'] < 100:  # Skip headings in navigation area
                        continue

                    sections.append(Section(
                        name=section_name,
                        selector=f'text={text[:30]}',  # Use text selector
                        y_position=box['y'],
                        height=box['height'] + 200,  # Include some content below
                        description=f"Content section: {section_name}"
                    ))
            except:
                continue

        return sections

    async def _detect_footer(self) -> Optional[Section]:
        """Detect footer section."""
        footer_selectors = [
            'footer',
            '[role="contentinfo"]',
            '.footer',
            '#footer',
            '[class*="footer"]'
        ]

        for selector in footer_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    box = await element.bounding_box()
                    if box:
                        return Section(
                            name="Footer",
                            selector=selector,
                            y_position=box['y'],
                            height=box['height'],
                            description="Page footer"
                        )
            except:
                continue

        return None

    async def get_section_screenshot(
        self,
        section: Section,
        full_width: bool = True
    ) -> bytes:
        """
        Capture a screenshot of a specific section.

        Args:
            section: Section object to screenshot
            full_width: If True, capture full width (default), else viewport width

        Returns:
            Screenshot as bytes
        """
        if section.selector == "viewport_top":
            # Screenshot the first viewport
            return await self.page.screenshot(clip={
                'x': 0,
                'y': 0,
                'width': await self.page.evaluate("window.innerWidth"),
                'height': section.height
            })
        else:
            # Screenshot specific element
            try:
                element = await self.page.query_selector(section.selector)
                if element:
                    return await element.screenshot()
            except:
                pass

            # Fallback: clip by position
            return await self.page.screenshot(clip={
                'x': 0,
                'y': section.y_position,
                'width': await self.page.evaluate("window.innerWidth"),
                'height': min(section.height, 2000)  # Cap at 2000px
            })


# Usage example
if __name__ == "__main__":
    from playwright.async_api import async_playwright

    async def test_section_detection():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

            # Navigate to test page
            await page.goto('https://www.shopify.com', wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Detect sections
            detector = SectionDetector(page)
            sections = await detector.detect_sections()

            print(f"\n📍 Detected Sections:")
            for section in sections:
                print(section)

            # Take screenshot of first section
            if sections:
                screenshot = await detector.get_section_screenshot(sections[0])
                with open('test_section.png', 'wb') as f:
                    f.write(screenshot)
                print(f"\n✓ Saved screenshot of {sections[0].name}")

            await browser.close()

    asyncio.run(test_section_detection())
