"""
Screenshot capture and analysis utilities for CRO Analyzer.

This module contains functions for capturing website screenshots using Playwright
and analyzing them with Claude AI for CRO issues.
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
from utils.image_processor import resize_screenshot_if_needed
from utils.anthropic_client import call_anthropic_api_with_retry


async def capture_screenshot_and_analyze(
    url: str, include_screenshots: bool = False, deep_info: bool = False
) -> Union[AnalysisResponse, DeepAnalysisResponse]:
    """
    Captures a screenshot of the website and analyzes it for CRO issues using Claude.

    Args:
        url: The website URL to analyze
        include_screenshots: If True, includes base64-encoded screenshots in the response. Default is False.
        deep_info: If True, provides comprehensive analysis with top 5 issues and scoring. Default is False (2-3 key points).

    Returns:
        AnalysisResponse or DeepAnalysisResponse depending on deep_info parameter
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

            # Capture full page screenshot
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)

            # Get page title and basic info
            page_title = await page.title()

            # Get the appropriate prompt based on deep_info flag
            cro_prompt = get_cro_prompt(deep_info=deep_info)

            # Analyze with Claude (with automatic retry logic)
            message = call_anthropic_api_with_retry(
                screenshot_base64=screenshot_base64,
                cro_prompt=cro_prompt,
                url=str(url),
                page_title=page_title,
                deep_info=deep_info,
            )

            # Parse Claude's response
            response_text = message.content[0].text.strip()

            # Log raw response for debugging
            # print(f"Raw Claude response (first 500 chars): {response_text[:500]}")

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = (
                    response_text.replace("```json", "").replace("```", "").strip()
                )
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            # Extract JSON from response if it's wrapped in text
            if not response_text.startswith("{"):
                # Try to find JSON in the response
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    response_text = response_text[start_idx : end_idx + 1]
                    print(f"Extracted JSON from response: {response_text[:200]}")

            # Use multi-layer JSON repair function
            try:
                analysis_data = repair_and_parse_json(
                    response_text, deep_info=deep_info
                )
            except ValueError as e:
                # Error already logged by repair function
                raise ValueError(str(e))

            # Parse based on response format
            issues = []

            if deep_info:
                # Deep info format: extract from "top_5_issues" array
                if "top_5_issues" in analysis_data:
                    for issue in analysis_data["top_5_issues"][:5]:
                        issues.append(
                            CROIssue(
                                title=issue.get("issue_title", ""),
                                description=issue.get("whats_wrong", ""),
                                why_it_matters=issue.get("why_it_matters", ""),
                                recommendation="\n".join(
                                    issue.get("implementation_ideas", [])
                                ),
                                screenshot_base64=(
                                    screenshot_base64 if include_screenshots else None
                                ),
                            )
                        )

                if not issues:
                    raise ValueError("No issues found in Claude's response")

                # Extract all deep info fields
                return DeepAnalysisResponse(
                    url=str(url),
                    analyzed_at=datetime.utcnow().isoformat(),
                    issues=issues,
                    total_issues_identified=analysis_data.get(
                        "total_issues_identified", len(issues)
                    ),
                    executive_summary=ExecutiveSummary(
                        overview=analysis_data.get("executive_summary", {}).get(
                            "overview", ""
                        ),
                        how_to_act=analysis_data.get("executive_summary", {}).get(
                            "how_to_act", ""
                        ),
                    ),
                    cro_analysis_score=ScoreDetails(
                        score=analysis_data.get("cro_analysis_score", {}).get(
                            "score", 0
                        ),
                        calculation=analysis_data.get("cro_analysis_score", {}).get(
                            "calculation", ""
                        ),
                        rating=analysis_data.get("cro_analysis_score", {}).get(
                            "rating", ""
                        ),
                    ),
                    site_performance_score=ScoreDetails(
                        score=analysis_data.get("site_performance_score", {}).get(
                            "score", 0
                        ),
                        calculation=analysis_data.get("site_performance_score", {}).get(
                            "calculation", ""
                        ),
                        rating=analysis_data.get("site_performance_score", {}).get(
                            "rating", ""
                        ),
                    ),
                    conversion_rate_increase_potential=ConversionPotential(
                        percentage=analysis_data.get(
                            "conversion_rate_increase_potential", {}
                        ).get("percentage", ""),
                        confidence=analysis_data.get(
                            "conversion_rate_increase_potential", {}
                        ).get("confidence", ""),
                        rationale=analysis_data.get(
                            "conversion_rate_increase_potential", {}
                        ).get("rationale", ""),
                    ),
                )
            else:
                # Standard format: key-value pairs like "Key point 1": {...}
                # Extract all key points from the response
                key_points = []

                # Log what keys we actually received for debugging
                print(f"DEBUG: Keys received from Claude: {list(analysis_data.keys())}")

                # Flexible matching for various key formats
                # Accept: "Key point N", "key point N", "Keypoint N", "Issue N", "Finding N", "Point N"
                accepted_prefixes = [
                    "key point",
                    "keypoint",
                    "issue",
                    "finding",
                    "point",
                ]

                for key, value in analysis_data.items():
                    if isinstance(value, dict):
                        # Check if key matches any accepted pattern (case-insensitive)
                        key_lower = key.lower().strip()
                        if any(
                            key_lower.startswith(prefix) for prefix in accepted_prefixes
                        ):
                            key_points.append(value)
                            print(f"DEBUG: Matched key '{key}' as issue")

                # Convert to CROIssue objects
                for i, point in enumerate(key_points[:3], 1):
                    issues.append(
                        CROIssue(
                            title=f"Key Point {i}",
                            description=point.get("Issue", "")
                            or point.get("issue", "")
                            or point.get("description", ""),
                            recommendation=point.get("Recommendation", "")
                            or point.get("recommendation", "")
                            or point.get("solution", ""),
                            screenshot_base64=(
                                screenshot_base64 if include_screenshots else None
                            ),
                        )
                    )

                if not issues:
                    print(
                        f"WARNING: No issues found. Response structure: {analysis_data}"
                    )
                    raise ValueError(
                        f"No issues found in Claude's response. Keys received: {list(analysis_data.keys())}"
                    )

                return AnalysisResponse(
                    url=str(url),
                    analyzed_at=datetime.utcnow().isoformat(),
                    issues=issues,
                )

        finally:
            await browser.close()
