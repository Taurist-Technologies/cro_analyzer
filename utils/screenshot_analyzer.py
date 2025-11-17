"""
Screenshot capture and analysis utilities for CRO Analyzer.

This module provides the sync endpoint implementation using section-based analysis.
For async processing, use the Celery task in tasks.py instead.
"""

from typing import Union
from playwright.async_api import async_playwright
from datetime import datetime
from models import (
    AnalysisResponse,
    DeepAnalysisResponse,
    CROIssue,
    ExecutiveSummary,
    ScoreDetails,
    ConversionPotential,
)
from analysis_prompt import get_cro_prompt
from utils.json_parser import repair_and_parse_json
from utils.section_analyzer import SectionAnalyzer
from utils.vector_db import VectorDBClient
from utils.anthropic_client import call_anthropic_api_with_retry
import os


async def capture_screenshot_and_analyze(
    url: str, include_screenshots: bool = False
) -> Union[AnalysisResponse, DeepAnalysisResponse]:
    """
    Analyzes a website for CRO issues using section-based analysis.

    This is the sync endpoint implementation. For async processing with task queue,
    use the Celery task in tasks.py instead.

    Args:
        url: The website URL to analyze
        include_screenshots: If True, includes base64-encoded screenshots in the response

    Returns:
        DeepAnalysisResponse with section-based analysis containing:
        - 5 Quick Wins (prioritized CRO issues)
        - 5 Scorecards (UX, Content, Performance, Conversion, Mobile)
        - Executive summary
        - Conversion rate increase potential
    """
    async with async_playwright() as p:
        # Launch browser with error handling
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            print(f"ERROR: Browser launch failed: {str(e)}")
            raise RuntimeError(f"Failed to launch browser: {str(e)}")

        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Navigate to the URL (increased timeout from 60s to 90s for slow pages)
            await page.goto(str(url), wait_until="load", timeout=90000)

            # Wait a bit for any dynamic content
            await page.wait_for_timeout(2000)

            # Initialize VectorDB client (REQUIRED for historical pattern grounding)
            vector_db = None
            try:
                vector_db = VectorDBClient()
                print("✓ VectorDB connected - historical patterns enabled")
            except Exception as e:
                error_msg = f"❌ VectorDB connection required but unavailable: {e}\nCannot proceed without historical audit data for grounding analysis."
                print(error_msg)
                raise RuntimeError(error_msg)

            # Initialize section analyzer with page and VectorDB
            section_analyzer = SectionAnalyzer(page, vector_db=vector_db)

            # Capture viewport screenshots (desktop and mobile)
            viewport_screenshots = await section_analyzer.capture_viewport_screenshots()

            # Analyze page sections (captures screenshots, queries historical patterns)
            section_data = await section_analyzer.analyze_page_sections(
                include_screenshots=True,
                include_mobile=True
            )

            # Format section context for Claude prompt
            section_context = section_analyzer.format_for_claude_prompt(section_data)

            # VALIDATION: Ensure sufficient historical patterns were retrieved
            total_patterns = sum(
                len(section.get("historical_patterns", []))
                for section in section_context["sections"]
            )

            if total_patterns == 0:
                error_msg = (
                    f"❌ No historical patterns found (>75% similarity) for any sections.\n"
                    f"Cannot proceed without historical audit data to ground the analysis.\n"
                    f"Sections analyzed: {', '.join([s['name'] for s in section_context['sections']])}"
                )
                print(error_msg)
                raise RuntimeError(error_msg)

            print(f"✓ Historical pattern validation passed: {total_patterns} patterns found across {len(section_context['sections'])} sections")

            # Get CRO prompt with section context
            cro_prompt = get_cro_prompt(section_context=section_context)

            # Extract section screenshots from section_context
            section_screenshots = [
                section["screenshot_base64"]
                for section in section_context["sections"]
                if section.get("screenshot_base64")
            ]

            # Call Claude API with section screenshots
            message = call_anthropic_api_with_retry(
                section_screenshots=section_screenshots,
                mobile_screenshot=section_context.get("mobile_screenshot"),
                cro_prompt=cro_prompt,
                url=str(url),
                page_title=section_data["page_info"]["title"]
            )

            # Parse Claude's response
            response_text = message.content[0].text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            # Extract JSON from response if it's wrapped in text
            if not response_text.startswith("{"):
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    response_text = response_text[start_idx : end_idx + 1]

            # Use multi-layer JSON repair function (always returns enhanced mode structure)
            analysis_data = repair_and_parse_json(response_text)

            # Build response with section-based enhanced mode format
            issues = []

            # Extract quick_wins (always present in enhanced mode)
            if "quick_wins" in analysis_data:
                for quick_win in analysis_data["quick_wins"][:5]:  # Exactly 5
                    issues.append(
                        CROIssue(
                            title=f"{quick_win.get('section', '')} - {quick_win.get('issue_title', '')}",
                            description=quick_win.get("whats_wrong", ""),
                            why_it_matters=quick_win.get("why_it_matters", ""),
                            recommendation="\n".join(quick_win.get("recommendations", [])),
                            screenshot_base64=None  # Screenshots not included in sync mode by default
                        )
                    )

            if not issues:
                raise ValueError("No quick wins found in Claude's response")

            # Return enhanced mode response with scorecards and viewport screenshots
            return DeepAnalysisResponse(
                url=str(url),
                analyzed_at=datetime.utcnow().isoformat(),
                issues=issues,
                total_issues_identified=len(issues),
                executive_summary=ExecutiveSummary(
                    overview=analysis_data.get("executive_summary", {}).get("overview", ""),
                    how_to_act=analysis_data.get("executive_summary", {}).get("how_to_act", "")
                ),
                cro_analysis_score=ScoreDetails(
                    score=analysis_data.get("scorecards", {}).get("ux_design", {}).get("score", 0),
                    calculation=f"UX & Design Score based on visual hierarchy, layout, and design quality",
                    rating=analysis_data.get("scorecards", {}).get("ux_design", {}).get("color", "yellow")
                ),
                site_performance_score=ScoreDetails(
                    score=analysis_data.get("scorecards", {}).get("site_performance", {}).get("score", 0),
                    calculation=f"Performance Score based on load speed and technical issues",
                    rating=analysis_data.get("scorecards", {}).get("site_performance", {}).get("color", "yellow")
                ),
                conversion_rate_increase_potential=ConversionPotential(
                    percentage=analysis_data.get("conversion_rate_increase_potential", {}).get("percentage", "Unknown"),
                    confidence=analysis_data.get("conversion_rate_increase_potential", {}).get("confidence", "Medium"),
                    rationale=analysis_data.get("conversion_rate_increase_potential", {}).get("rationale", "")
                ),
                desktop_viewport_screenshot=viewport_screenshots.get("desktop"),
                mobile_viewport_screenshot=viewport_screenshots.get("mobile")
            )

        finally:
            await browser.close()
