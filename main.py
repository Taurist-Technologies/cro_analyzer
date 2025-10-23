import asyncio
import base64
from typing import List, Optional, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright
import anthropic
import os
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
import io
from analysis_prompt import get_cro_prompt

load_dotenv()

app = FastAPI(title="CRO Analyzer Service")


# Models
class CROIssue(BaseModel):
    title: str
    description: str
    recommendation: str
    screenshot_base64: Optional[str] = None


class AnalysisRequest(BaseModel):
    url: HttpUrl
    include_screenshots: bool = False
    deep_info: bool = False


class AnalysisResponse(BaseModel):
    url: str
    analyzed_at: str
    issues: List[CROIssue]


# Deep info models
class ExecutiveSummary(BaseModel):
    overview: str
    how_to_act: str


class ScoreDetails(BaseModel):
    score: int
    calculation: str
    rating: str


class ConversionPotential(BaseModel):
    percentage: str
    confidence: str
    rationale: str


class DeepAnalysisResponse(AnalysisResponse):
    total_issues_identified: int
    executive_summary: ExecutiveSummary
    cro_analysis_score: ScoreDetails
    site_performance_score: ScoreDetails
    conversion_rate_increase_potential: ConversionPotential


# Initialize Anthropic client
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def resize_screenshot_if_needed(
    screenshot_bytes: bytes, max_dimension: int = 7500, max_file_size: int = 5_242_880
) -> str:
    """
    Resize and compress screenshot to comply with Claude's limits:
    - 8000px maximum dimension
    - 5 MB maximum file size

    Uses JPEG compression with quality reduction until under max_file_size.
    Returns base64 encoded string of the processed image.

    Args:
        screenshot_bytes: Original screenshot bytes
        max_dimension: Maximum width/height in pixels (default 7500)
        max_file_size: Maximum file size in bytes (default 5MB = 5,242,880 bytes)
    """
    # Open image from bytes
    image = Image.open(io.BytesIO(screenshot_bytes))
    width, height = image.size

    # Step 1: Resize dimensions if needed
    if width > max_dimension or height > max_dimension:
        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))

        # Resize image
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Convert RGBA to RGB if necessary (JPEG doesn't support transparency)
    if image.mode == "RGBA":
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        image = rgb_image
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Step 2: Compress to stay under file size limit
    quality = 95
    buffer = io.BytesIO()

    while quality > 20:  # Don't go below 20% quality
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        file_size = buffer.tell()

        if file_size <= max_file_size:
            break

        # If still too large, reduce quality
        quality -= 10

    # Step 3: If still too large after max compression, reduce dimensions further
    if buffer.tell() > max_file_size:
        scale_factor = 0.8
        while buffer.tell() > max_file_size and scale_factor > 0.3:
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=75, optimize=True)

            if buffer.tell() <= max_file_size:
                break

            scale_factor -= 0.1

    screenshot_bytes = buffer.getvalue()

    # Return base64 encoded string
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def capture_screenshot_and_analyze(
    url: str, include_screenshots: bool = False, deep_info: bool = False
) -> Union[AnalysisResponse, DeepAnalysisResponse]:
    """
    Captures a screenshot of the website and analyzes it for CRO issues using Claude.

    Args:
        url: The website URL to analyze
        include_screenshots: If True, includes base64-encoded screenshots in the response. Default is False.
        deep_info: If True, provides comprehensive analysis with top 5 issues and scoring. Default is False (2-3 key points).
    """
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Navigate to the URL
            await page.goto(str(url), wait_until="load", timeout=60000)

            # Wait a bit for any dynamic content
            await page.wait_for_timeout(2000)

            # Capture full page screenshot
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)

            # Get page title and basic info
            page_title = await page.title()

            # Get the appropriate prompt based on deep_info flag
            cro_prompt = get_cro_prompt(deep_info=deep_info)

            # Analyze with Claude
            message = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000 if deep_info else 2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": screenshot_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"""{cro_prompt}

Website URL: {url}
Page Title: {page_title}

Please analyze this website screenshot and provide your findings in the JSON format specified above.""",
                            },
                        ],
                    }
                ],
            )

            # Parse Claude's response
            response_text = message.content[0].text.strip()

            # Log raw response for debugging
            print(f"Raw Claude response (first 500 chars): {response_text[:500]}")

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = (
                    response_text.replace("```json", "").replace("```", "").strip()
                )
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            import json

            # Extract JSON from response if it's wrapped in text
            if not response_text.startswith("{"):
                # Try to find JSON in the response
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    response_text = response_text[start_idx : end_idx + 1]
                    print(f"Extracted JSON from response: {response_text[:200]}")

            try:
                analysis_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                # Log the raw response for debugging
                print(f"Failed to parse JSON. Full response: {response_text}")
                raise ValueError(f"Invalid JSON response from Claude: {str(e)}")

            # Parse based on response format
            issues = []

            if deep_info:
                # Deep info format: extract from "top_5_issues" array
                if "top_5_issues" in analysis_data:
                    for issue in analysis_data["top_5_issues"][:5]:
                        issues.append(
                            CROIssue(
                                title=issue.get("issue_title", ""),
                                description=issue.get("whats_wrong", "")
                                + "\n\nWhy it matters: "
                                + issue.get("why_it_matters", ""),
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
                for key, value in analysis_data.items():
                    if key.startswith("Key point") and isinstance(value, dict):
                        key_points.append(value)

                # Convert to CROIssue objects
                for i, point in enumerate(key_points[:3], 1):
                    issues.append(
                        CROIssue(
                            title=f"Key Point {i}",
                            description=point.get("Issue", ""),
                            recommendation=point.get("Recommendation", ""),
                            screenshot_base64=(
                                screenshot_base64 if include_screenshots else None
                            ),
                        )
                    )

                if not issues:
                    raise ValueError("No issues found in Claude's response")

                return AnalysisResponse(
                    url=str(url),
                    analyzed_at=datetime.utcnow().isoformat(),
                    issues=issues,
                )

        finally:
            await browser.close()


@app.get("/")
async def root():
    return {
        "service": "CRO Analyzer",
        "status": "running",
        "endpoints": {"analyze": "/analyze (POST)"},
    }


@app.post("/analyze", response_model=Union[AnalysisResponse, DeepAnalysisResponse])
async def analyze_website(request: AnalysisRequest):
    """
    Analyzes a website for CRO issues and returns actionable recommendations.

    By default, returns 2-3 key points. Set deep_info=true for comprehensive analysis with:
    - Total issues identified
    - Top 5 issues with detailed breakdown
    - Executive summary with strategic guidance
    - CRO analysis score (0-100)
    - Site performance score (0-100)
    - Conversion rate increase potential estimate

    Screenshots are NOT included in the response by default. Set include_screenshots=true to include them.
    """
    try:
        result = await capture_screenshot_and_analyze(
            str(request.url), request.include_screenshots, request.deep_info
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=60)
