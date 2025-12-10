"""
Section Analyzer for CRO Analyzer

Orchestrates section-based analysis:
1. Detects page sections
2. Captures screenshots for each section
3. Queries ChromaDB for historical patterns
4. Prepares structured context for Claude API
"""

from typing import List, Dict, Tuple, Optional
from playwright.async_api import Page
import base64
from utils.section_detector import SectionDetector, Section
from utils.vector_db import VectorDBClient
from utils.image_processor import resize_screenshot_if_needed


class SectionAnalyzer:
    """
    Orchestrates section-by-section webpage analysis.

    Workflow:
    1. Detect sections on page (Navigation, Hero, Product, Forms, etc.)
    2. Capture screenshot for each section
    3. Query ChromaDB for similar historical issues per section
    4. Compile structured context for Claude API
    """

    def __init__(self, page: Page, vector_db: Optional[VectorDBClient] = None):
        """
        Initialize section analyzer.

        Args:
            page: Playwright Page object
            vector_db: Optional VectorDBClient for historical pattern matching
        """
        self.page = page
        self.detector = SectionDetector(page)
        self.vector_db = vector_db

    async def analyze_page_sections(
        self, include_screenshots: bool = True, include_mobile: bool = True
    ) -> Dict:
        """
        Analyze page section by section.

        Args:
            include_screenshots: Include base64 screenshots in output
            include_mobile: Also capture mobile viewport screenshots

        Returns:
            Dictionary containing:
            - sections: List of detected sections with metadata
            - screenshots: Section screenshots (base64 if include_screenshots=True)
            - historical_patterns: Similar issues from ChromaDB per section
            - page_info: URL, title, viewport
        """
        print("\n📸 Starting section-based analysis...")

        # Get page info
        url = self.page.url
        title = await self.page.title()
        viewport = self.page.viewport_size

        # Detect sections
        sections = await self.detector.detect_sections()

        # Capture desktop screenshots
        print(f"\n📷 Capturing {len(sections)} section screenshots (desktop)...")
        section_data = await self._capture_section_screenshots(
            sections, include_screenshots
        )

        # Capture mobile screenshots if requested
        mobile_data = None
        if include_mobile:
            mobile_data = await self._capture_mobile_screenshots(
                sections, include_screenshots
            )

        # Query historical patterns if vector DB is available
        historical_patterns = {}
        if self.vector_db:
            print(f"\n🔍 Querying historical patterns from ChromaDB...")
            historical_patterns = await self._query_historical_patterns(sections)

        # Compile results
        result = {
            "page_info": {"url": url, "title": title, "viewport": viewport},
            "sections": section_data,
            "mobile_sections": mobile_data,
            "historical_patterns": historical_patterns,
            "total_sections": len(sections),
        }

        print(f"✓ Section analysis complete")
        print(f"  Desktop sections: {len(section_data)}")
        if mobile_data:
            print(f"  Mobile sections: {len(mobile_data)}")
        if historical_patterns:
            total_patterns = sum(
                len(patterns) for patterns in historical_patterns.values()
            )
            print(f"  Historical patterns found: {total_patterns}")

        return result

    async def _capture_section_screenshots(
        self, sections: List[Section], include_base64: bool = True
    ) -> List[Dict]:
        """
        Capture screenshots for each section.

        Args:
            sections: List of Section objects
            include_base64: If True, include base64 encoded screenshots

        Returns:
            List of section dictionaries with screenshot data
        """
        section_data = []

        for i, section in enumerate(sections, 1):
            print(f"  [{i}/{len(sections)}] {section.name}...", end="")

            try:
                # Capture screenshot
                screenshot_bytes = await self.detector.get_section_screenshot(section)

                # Resize if needed
                screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)

                # Prepare section data
                data = {
                    "name": section.name,
                    "description": section.description,
                    "position": section.y_position,
                    "height": section.height,
                    "screenshot_size": (
                        len(screenshot_base64) if screenshot_base64 else 0
                    ),
                }

                if include_base64:
                    data["screenshot_base64"] = screenshot_base64

                section_data.append(data)
                print(f" ✓")

            except Exception as e:
                print(f" ✗ Error: {str(e)}")
                section_data.append(
                    {
                        "name": section.name,
                        "description": section.description,
                        "error": str(e),
                    }
                )

        return section_data

    async def _capture_mobile_screenshots(
        self, sections: List[Section], include_base64: bool = True
    ) -> Optional[List[Dict]]:
        """
        Capture mobile viewport screenshots.

        Args:
            sections: List of Section objects
            include_base64: If True, include base64 encoded screenshots

        Returns:
            List of mobile section screenshots, or None if failed
        """
        original_viewport = None
        try:
            # Save current viewport
            original_viewport = self.page.viewport_size

            # Set mobile viewport (iPhone 12 Pro)
            await self.page.set_viewport_size({"width": 390, "height": 844})
            await self.page.wait_for_timeout(1000)  # Wait for reflow

            print(f"\n📱 Capturing mobile screenshots...")

            # Test mobile navigation elements while in mobile viewport
            mobile_nav_result = None
            try:
                from utils.interaction_tester import InteractionTester
                mobile_tester = InteractionTester(self.page)
                mobile_nav_result = await mobile_tester.test_mobile_navigation()
            except Exception as e:
                print(f"  ⚠ Mobile nav test skipped: {str(e)}")

            # Capture full-page mobile screenshot
            mobile_screenshot_bytes = await self.page.screenshot(full_page=True)
            mobile_screenshot_base64 = resize_screenshot_if_needed(
                mobile_screenshot_bytes
            )

            mobile_data = [
                {
                    "name": "Mobile Full Page",
                    "description": "Full mobile viewport screenshot",
                    "screenshot_size": (
                        len(mobile_screenshot_base64) if mobile_screenshot_base64 else 0
                    ),
                }
            ]

            if include_base64:
                mobile_data[0]["screenshot_base64"] = mobile_screenshot_base64

            # Include mobile nav test results if available
            if mobile_nav_result:
                mobile_data[0]["mobile_nav_test"] = mobile_nav_result

            # Restore original viewport
            await self.page.set_viewport_size(original_viewport)
            await self.page.wait_for_timeout(500)

            print(f"  ✓ Mobile screenshot captured")

            return mobile_data

        except Exception as e:
            print(f"  ✗ Mobile screenshot failed: {str(e)}")
            # Restore viewport on error
            try:
                if original_viewport:
                    await self.page.set_viewport_size(original_viewport)
            except:
                pass
            return None

    async def capture_viewport_screenshots(self) -> Dict[str, Optional[str]]:
        """
        Capture viewport-only screenshots (visible area, not full page).

        Returns:
            Dictionary with 'desktop' and 'mobile' viewport screenshots (base64)
        """
        viewports = {}

        try:
            # Save original viewport
            original_viewport = self.page.viewport_size

            # Capture desktop viewport (1920x1080)
            print(f"\n🖥️  Capturing desktop viewport screenshot...")
            await self.page.set_viewport_size({"width": 1920, "height": 1080})
            await self.page.wait_for_timeout(500)

            desktop_bytes = await self.page.screenshot(full_page=False)
            viewports["desktop"] = resize_screenshot_if_needed(desktop_bytes)
            print(f"  ✓ Desktop viewport captured")

            # Capture mobile viewport (390x844 - iPhone 12 Pro)
            print(f"📱 Capturing mobile viewport screenshot...")
            await self.page.set_viewport_size({"width": 390, "height": 844})
            await self.page.wait_for_timeout(1000)

            mobile_bytes = await self.page.screenshot(full_page=False)
            viewports["mobile"] = resize_screenshot_if_needed(mobile_bytes)
            print(f"  ✓ Mobile viewport captured")

            # Restore original viewport
            await self.page.set_viewport_size(original_viewport)
            await self.page.wait_for_timeout(500)

        except Exception as e:
            print(f"  ✗ Viewport screenshot failed: {str(e)}")
            viewports["desktop"] = None
            viewports["mobile"] = None
            # Try to restore viewport
            try:
                await self.page.set_viewport_size(original_viewport)
            except:
                pass

        return viewports

    async def _query_historical_patterns(
        self, sections: List[Section]
    ) -> Dict[str, List[Dict]]:
        """
        Query ChromaDB for similar historical issues for each section.

        Args:
            sections: List of detected sections

        Returns:
            Dictionary mapping section names to similar historical issues
        """
        patterns = {}

        for section in sections:
            # Query for similar issues in this section
            query_text = f"{section.name} section issues and optimization opportunities"

            try:
                similar_issues = self.vector_db.query_similar_issues(
                    query_text=query_text,
                    section=section.name,
                    n_results=8,  # Top 8 similar issues for better context
                )

                if similar_issues:
                    patterns[section.name] = [
                        {
                            "title": issue["metadata"]["issue_title"],
                            "description": issue["metadata"]["issue_description"],
                            "why_it_matters": issue["metadata"]["why_it_matters"],
                            "recommendations": issue["metadata"]["recommendations"],
                            "similarity": issue["similarity"],
                            "client": issue["metadata"]["client_name"],
                        }
                        for issue in similar_issues
                        if issue["similarity"]
                        > 0.60  # Only include similar patterns (>60% similarity)
                    ]

            except Exception as e:
                print(f"  ⚠ Error querying patterns for {section.name}: {str(e)}")
                continue

        return patterns

    def format_for_claude_prompt(self, analysis_data: Dict) -> Dict:
        """
        Format section analysis data for Claude API prompt.

        Args:
            analysis_data: Output from analyze_page_sections()

        Returns:
            Formatted dictionary ready for Claude API with structured sections
        """
        # Prepare section context
        sections_context = []

        for section in analysis_data["sections"]:
            # Skip sections that failed to capture screenshots
            if "error" in section:
                print(f"  ⚠ Skipping section '{section['name']}' due to screenshot error: {section['error']}")
                continue

            section_context = {
                "name": section["name"],
                "description": section["description"],
                "position": section["position"],
                "screenshot_base64": section.get("screenshot_base64"),
            }

            # Add historical patterns if available
            section_name = section["name"]
            if section_name in analysis_data.get("historical_patterns", {}):
                patterns = analysis_data["historical_patterns"][section_name]
                section_context["historical_patterns"] = [
                    {
                        "issue": p["title"],
                        "why_it_matters": p["why_it_matters"],
                        "recommendations": p["recommendations"],
                        "similar_to": p["client"],
                    }
                    for p in patterns
                ]

            sections_context.append(section_context)

        # Add mobile screenshot if available
        mobile_screenshot = None
        mobile_nav_test = None
        if analysis_data.get("mobile_sections"):
            mobile_screenshot = analysis_data["mobile_sections"][0].get(
                "screenshot_base64"
            )
            # Include mobile navigation test results if available
            mobile_nav_test = analysis_data["mobile_sections"][0].get(
                "mobile_nav_test"
            )

        return {
            "url": analysis_data["page_info"]["url"],
            "title": analysis_data["page_info"]["title"],
            "sections": sections_context,
            "mobile_screenshot": mobile_screenshot,
            "mobile_nav_test": mobile_nav_test,
            "total_sections": analysis_data["total_sections"],
        }


# Usage example
if __name__ == "__main__":
    from playwright.async_api import async_playwright
    import asyncio

    async def test_section_analysis():
        # Initialize vector DB (optional)
        try:
            vector_db = VectorDBClient()
        except:
            print("⚠ Vector DB not available, continuing without historical patterns")
            vector_db = None

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            # Navigate to test page
            print("🌐 Loading page...")
            await page.goto("https://www.shopify.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Analyze sections
            analyzer = SectionAnalyzer(page, vector_db=vector_db)
            analysis = await analyzer.analyze_page_sections(
                include_screenshots=False,  # Set False to avoid large output
                include_mobile=True,
            )

            print(f"\n📊 Analysis Results:")
            print(f"  URL: {analysis['page_info']['url']}")
            print(f"  Title: {analysis['page_info']['title']}")
            print(f"  Sections detected: {analysis['total_sections']}")

            print(f"\n📋 Sections:")
            for section in analysis["sections"]:
                print(f"  - {section['name']} at {section['position']}px")

            # Format for Claude
            claude_context = analyzer.format_for_claude_prompt(analysis)
            print(f"\n✓ Formatted context for Claude API")
            print(f"  Sections with context: {len(claude_context['sections'])}")
            print(
                f"  Mobile screenshot included: {claude_context['mobile_screenshot'] is not None}"
            )

            await browser.close()

    asyncio.run(test_section_analysis())
