#!/usr/bin/env python3
"""
System Validation Script for CRO Analyzer

Tests the complete section-based analysis pipeline:
1. ChromaDB vector database setup and querying
2. Section detection and screenshot capture
3. Historical pattern matching
4. Claude API integration with multiple screenshots
5. Response parsing and validation

Usage:
    python3 scripts/validate_system.py --mode [quick|full]

    quick: Basic health checks only (< 30 seconds)
    full: End-to-end test with real website analysis (2-3 minutes)
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))


class SystemValidator:
    """Validates all components of the enhanced CRO analyzer system."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results: Dict[str, bool] = {}
        self.errors: List[str] = []

    def log(self, message: str, level: str = "INFO"):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "WARNING": "⚠️ ",
                "TEST": "🧪"
            }.get(level, "")
            print(f"{prefix} {message}")

    def test_chromadb_setup(self) -> bool:
        """Test ChromaDB initialization and basic operations."""
        self.log("Testing ChromaDB setup...", "TEST")

        try:
            from utils.vector_db import VectorDBClient

            # Initialize client
            db = VectorDBClient()
            self.log("ChromaDB client initialized successfully", "SUCCESS")

            # Test collection access
            collection = db.collection
            count = collection.count()
            self.log(f"ChromaDB collection has {count} documents", "INFO")

            if count == 0:
                self.log("Warning: ChromaDB collection is empty. Run scripts/ingest_audits.py first.", "WARNING")
                return True  # Not a failure, just a warning

            # Test query functionality
            test_results = db.query_similar_issues(
                query_text="hero section call to action button visibility",
                section="Hero",
                n_results=3
            )

            if test_results:
                self.log(f"Successfully queried {len(test_results)} similar issues from ChromaDB", "SUCCESS")
                if self.verbose:
                    for i, result in enumerate(test_results, 1):
                        self.log(f"  {i}. {result['metadata']['issue_title']} (similarity: {result['similarity']:.2%})", "INFO")
                return True
            else:
                self.log("Warning: No similar issues found in query test", "WARNING")
                return True  # Not a hard failure

        except ImportError as e:
            self.errors.append(f"ChromaDB import failed: {str(e)}")
            self.log(f"ChromaDB import failed: {str(e)}", "ERROR")
            return False
        except Exception as e:
            self.errors.append(f"ChromaDB test failed: {str(e)}")
            self.log(f"ChromaDB test failed: {str(e)}", "ERROR")
            return False

    def test_section_detection(self) -> bool:
        """Test section detector with a sample webpage."""
        self.log("Testing section detection...", "TEST")

        try:
            from playwright.async_api import async_playwright
            from utils.section_detector import SectionDetector

            async def _test():
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

                    # Navigate to a simple test page
                    await page.goto('https://example.com', wait_until='domcontentloaded')
                    await page.wait_for_timeout(2000)

                    # Detect sections
                    detector = SectionDetector(page)
                    sections = await detector.detect_sections()

                    await browser.close()
                    return sections

            sections = asyncio.run(_test())

            if sections and len(sections) > 0:
                self.log(f"Successfully detected {len(sections)} sections", "SUCCESS")
                if self.verbose:
                    for section in sections:
                        self.log(f"  - {section.name} at {section.y_position}px", "INFO")
                return True
            else:
                self.errors.append("Section detection returned no sections")
                self.log("Section detection returned no sections", "ERROR")
                return False

        except ImportError as e:
            self.errors.append(f"Section detector import failed: {str(e)}")
            self.log(f"Section detector import failed: {str(e)}", "ERROR")
            return False
        except Exception as e:
            self.errors.append(f"Section detection test failed: {str(e)}")
            self.log(f"Section detection test failed: {str(e)}", "ERROR")
            return False

    def test_section_analyzer(self) -> bool:
        """Test section analyzer with screenshot capture and ChromaDB integration."""
        self.log("Testing section analyzer with ChromaDB integration...", "TEST")

        try:
            from playwright.async_api import async_playwright
            from utils.section_analyzer import SectionAnalyzer
            from utils.vector_db import VectorDBClient

            async def _test():
                # Initialize vector DB (optional)
                try:
                    vector_db = VectorDBClient()
                    self.log("Vector DB initialized for section analyzer", "INFO")
                except:
                    vector_db = None
                    self.log("Vector DB unavailable, continuing without historical patterns", "WARNING")

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

                    # Navigate to test page
                    await page.goto('https://example.com', wait_until='domcontentloaded')
                    await page.wait_for_timeout(2000)

                    # Analyze sections
                    analyzer = SectionAnalyzer(page, vector_db=vector_db)
                    analysis = await analyzer.analyze_page_sections(
                        include_screenshots=False,  # Don't include base64 for test
                        include_mobile=True
                    )

                    await browser.close()
                    return analysis

            analysis = asyncio.run(_test())

            if analysis and analysis.get('total_sections', 0) > 0:
                self.log(f"Section analyzer detected {analysis['total_sections']} sections", "SUCCESS")

                # Check for historical patterns
                if analysis.get('historical_patterns'):
                    pattern_count = sum(len(patterns) for patterns in analysis['historical_patterns'].values())
                    self.log(f"Found {pattern_count} historical patterns from ChromaDB", "SUCCESS")
                else:
                    self.log("No historical patterns found (ChromaDB may be empty)", "WARNING")

                # Check for mobile screenshot
                if analysis.get('mobile_sections'):
                    self.log("Mobile screenshot captured successfully", "SUCCESS")

                return True
            else:
                self.errors.append("Section analyzer returned no sections")
                self.log("Section analyzer returned no sections", "ERROR")
                return False

        except Exception as e:
            self.errors.append(f"Section analyzer test failed: {str(e)}")
            self.log(f"Section analyzer test failed: {str(e)}", "ERROR")
            return False

    def test_anthropic_client(self) -> bool:
        """Test Anthropic API client with section-based analysis support."""
        self.log("Testing Anthropic API client...", "TEST")

        try:
            from utils.anthropic_client import get_anthropic_client
            import anthropic

            # Check API key
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                self.errors.append("ANTHROPIC_API_KEY not set in environment")
                self.log("ANTHROPIC_API_KEY not set in environment", "ERROR")
                return False

            # Initialize client
            client = get_anthropic_client()
            self.log("Anthropic client initialized successfully", "SUCCESS")

            # Test basic API call (small request to minimize cost)
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=50,
                    messages=[{"role": "user", "content": "Say 'test successful' in JSON format with a key 'status'"}]
                )

                if response and response.content:
                    self.log("Anthropic API connection successful", "SUCCESS")
                    return True
                else:
                    self.errors.append("Anthropic API returned empty response")
                    self.log("Anthropic API returned empty response", "ERROR")
                    return False

            except anthropic.AuthenticationError:
                self.errors.append("Invalid ANTHROPIC_API_KEY")
                self.log("Invalid ANTHROPIC_API_KEY", "ERROR")
                return False
            except anthropic.RateLimitError:
                self.log("Rate limit hit (API is working, just throttled)", "WARNING")
                return True  # API is working, just rate limited
            except Exception as e:
                self.errors.append(f"Anthropic API call failed: {str(e)}")
                self.log(f"Anthropic API call failed: {str(e)}", "ERROR")
                return False

        except ImportError as e:
            self.errors.append(f"Anthropic client import failed: {str(e)}")
            self.log(f"Anthropic client import failed: {str(e)}", "ERROR")
            return False
        except Exception as e:
            self.errors.append(f"Anthropic client test failed: {str(e)}")
            self.log(f"Anthropic client test failed: {str(e)}", "ERROR")
            return False

    def test_section_based_end_to_end(self) -> bool:
        """Test complete section-based analysis pipeline with real website analysis."""
        self.log("Testing section-based analysis end-to-end (this will take 1-2 minutes)...", "TEST")

        try:
            from utils.screenshot_analyzer import capture_screenshot_and_analyze

            async def _test():
                # Use a simple, fast-loading page for testing
                test_url = "https://example.com"

                self.log(f"Analyzing {test_url} with section-based analysis...", "INFO")

                result = await capture_screenshot_and_analyze(
                    url=test_url,
                    include_screenshots=False  # Don't bloat response
                )

                return result

            result = asyncio.run(_test())

            if result:
                self.log("Section-based analysis completed successfully", "SUCCESS")

                # Validate response structure
                if hasattr(result, 'issues') and len(result.issues) > 0:
                    self.log(f"Analysis returned {len(result.issues)} issues", "SUCCESS")

                    # Check for section-based analysis specific fields
                    first_issue = result.issues[0]
                    if hasattr(first_issue, 'why_it_matters') and first_issue.why_it_matters:
                        self.log("Section analysis 'why_it_matters' field present", "SUCCESS")

                    return True
                else:
                    self.log("Warning: Analysis returned no issues", "WARNING")
                    return True  # Not a hard failure
            else:
                self.errors.append("Section-based analysis returned no result")
                self.log("Section-based analysis returned no result", "ERROR")
                return False

        except Exception as e:
            self.errors.append(f"Section-based end-to-end test failed: {str(e)}")
            self.log(f"Section-based end-to-end test failed: {str(e)}", "ERROR")
            import traceback
            if self.verbose:
                traceback.print_exc()
            return False

    def run_quick_tests(self) -> bool:
        """Run quick health checks (< 30 seconds)."""
        self.log("\n" + "="*60, "INFO")
        self.log("QUICK VALIDATION MODE", "INFO")
        self.log("="*60 + "\n", "INFO")

        tests = [
            ("ChromaDB Setup", self.test_chromadb_setup),
            ("Anthropic API Client", self.test_anthropic_client),
            ("Section Detection", self.test_section_detection),
        ]

        for test_name, test_func in tests:
            self.log(f"\n--- {test_name} ---", "INFO")
            result = test_func()
            self.results[test_name] = result

        return all(self.results.values())

    def run_full_tests(self) -> bool:
        """Run comprehensive tests including end-to-end (2-3 minutes)."""
        self.log("\n" + "="*60, "INFO")
        self.log("FULL VALIDATION MODE", "INFO")
        self.log("="*60 + "\n", "INFO")

        tests = [
            ("ChromaDB Setup", self.test_chromadb_setup),
            ("Anthropic API Client", self.test_anthropic_client),
            ("Section Detection", self.test_section_detection),
            ("Section Analyzer", self.test_section_analyzer),
            ("Section-Based End-to-End", self.test_section_based_end_to_end),
        ]

        for test_name, test_func in tests:
            self.log(f"\n--- {test_name} ---", "INFO")
            result = test_func()
            self.results[test_name] = result

        return all(self.results.values())

    def print_summary(self):
        """Print test summary and results."""
        self.log("\n" + "="*60, "INFO")
        self.log("VALIDATION SUMMARY", "INFO")
        self.log("="*60 + "\n", "INFO")

        passed = sum(1 for r in self.results.values() if r)
        total = len(self.results)

        for test_name, result in self.results.items():
            status = "PASS" if result else "FAIL"
            level = "SUCCESS" if result else "ERROR"
            self.log(f"{test_name}: {status}", level)

        self.log(f"\nTotal: {passed}/{total} tests passed", "INFO")

        if self.errors:
            self.log("\nErrors encountered:", "ERROR")
            for error in self.errors:
                self.log(f"  - {error}", "ERROR")

        if passed == total:
            self.log("\n🎉 All tests passed! System is ready for section-based analysis.", "SUCCESS")
            return True
        else:
            self.log(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.", "ERROR")
            return False


def main():
    """Main entry point for validation script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate CRO Analyzer enhanced mode system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/validate_system.py --mode quick
  python3 scripts/validate_system.py --mode full --quiet
        """
    )

    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="quick",
        help="Validation mode: quick (< 30s) or full (2-3 min with real analysis)"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output, only show summary"
    )

    args = parser.parse_args()

    # Create validator
    validator = SystemValidator(verbose=not args.quiet)

    # Run tests
    if args.mode == "quick":
        success = validator.run_quick_tests()
    else:
        success = validator.run_full_tests()

    # Print summary
    validator.print_summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
