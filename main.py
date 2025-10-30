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
import json
import re
import json5
import demjson3
from pathlib import Path
from analysis_prompt import get_cro_prompt
import traceback
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

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


# Retry wrapper for Anthropic API calls
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (anthropic.APIConnectionError, anthropic.RateLimitError)
    ),
    reraise=True,
)
def call_anthropic_api_with_retry(
    screenshot_base64: str, cro_prompt: str, url: str, page_title: str, deep_info: bool
):
    """
    Calls Anthropic API with automatic retry logic for transient failures.

    Retries up to 3 times for:
    - APIConnectionError (network issues)
    - RateLimitError (rate limit exceeded)

    Does NOT retry for:
    - AuthenticationError (bad API key)
    - InvalidRequestError (malformed request)
    - Other permanent errors

    Args:
        screenshot_base64: Base64-encoded screenshot
        cro_prompt: The CRO analysis prompt
        url: Website URL being analyzed
        page_title: Page title
        deep_info: Whether to use deep analysis mode

    Returns:
        Anthropic message response
    """
    return anthropic_client.messages.create(
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


# JSON Repair and Parsing Function
def repair_and_parse_json(response_text: str, deep_info: bool = False) -> dict:
    """
    Multi-layered JSON parsing with auto-repair capabilities.

    Attempts to parse JSON through multiple strategies:
    1. Standard json.loads()
    2. Clean common issues (trailing commas, comments)
    3. json5 parser (tolerates comments and trailing commas)
    4. demjson3 parser (auto-repairs many errors)
    5. Regex extraction fallback for critical fields

    Args:
        response_text: Raw text response from Claude
        deep_info: Whether this is a deep analysis (affects error handling)

    Returns:
        Parsed dictionary from JSON

    Raises:
        ValueError: If all parsing attempts fail
    """
    original_text = response_text
    errors = []

    # Layer 1: Try standard JSON parser first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        errors.append(f"Standard JSON: {str(e)}")

    # Layer 2: Clean common Claude JSON mistakes
    try:
        cleaned = response_text

        # Remove trailing commas before closing braces/brackets
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

        # Remove single-line comments (// ...)
        cleaned = re.sub(r"//.*?\n", "\n", cleaned)

        # Remove multi-line comments (/* ... */)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

        # Fix common quote escaping issues
        cleaned = cleaned.replace('\\"', '"').replace("'", '"')

        # Try parsing cleaned version
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"Cleaned JSON: {str(e)}")

    # Layer 3: Try json5 (tolerates trailing commas and comments)
    try:
        return json5.loads(response_text)
    except Exception as e:
        errors.append(f"JSON5: {str(e)}")

    # Layer 4: Try demjson3 (auto-repairs many JSON errors)
    try:
        return demjson3.decode(response_text)
    except Exception as e:
        errors.append(f"DemJSON: {str(e)}")

    # Layer 5: Regex extraction fallback with graceful degradation
    try:
        print("WARNING: All JSON parsers failed. Attempting regex extraction...")

        if deep_info:
            # Extract deep info structure
            extracted = {
                "total_issues_identified": 0,
                "top_5_issues": [],
                "executive_summary": {
                    "overview": "Analysis unavailable",
                    "how_to_act": "",
                },
                "cro_analysis_score": {
                    "score": 0,
                    "calculation": "",
                    "rating": "Unknown",
                },
                "site_performance_score": {
                    "score": 0,
                    "calculation": "",
                    "rating": "Unknown",
                },
                "conversion_rate_increase_potential": {
                    "percentage": "Unknown",
                    "confidence": "Low",
                    "rationale": "",
                },
            }
        else:
            # Extract standard format (Key point 1, 2, 3)
            extracted = {}

            # Try to find key points using regex
            key_point_pattern = r'"(Key point \d+)":\s*\{[^}]*"Issue":\s*"([^"]+)"[^}]*"Recommendation":\s*"([^"]+)"'
            matches = re.findall(key_point_pattern, response_text, re.DOTALL)

            for key, issue, recommendation in matches[:3]:
                extracted[key] = {"Issue": issue, "Recommendation": recommendation}

        # Graceful degradation: Return partial data if we got anything useful
        if extracted:
            if deep_info:
                # Check if we have at least some structure
                if extracted.get("top_5_issues") or extracted.get("executive_summary"):
                    print(f"WARNING: Partial deep info extraction successful via regex")
                    return extracted
            else:
                # Check if we have at least one key point
                if any(key.startswith("Key point") for key in extracted.keys()):
                    print(
                        f"WARNING: Partial extraction successful. Found {len(extracted)} key points via regex"
                    )
                    return extracted

    except Exception as e:
        errors.append(f"Regex extraction: {str(e)}")

    # All layers failed - save for debugging and raise error
    error_log_path = Path("failed_json_responses")
    error_log_path.mkdir(exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = error_log_path / f"failed_{timestamp}.json"

    with open(log_file, "w") as f:
        f.write(f"=== ORIGINAL RESPONSE ===\n{original_text}\n\n")
        f.write(f"=== ERRORS ===\n")
        for error in errors:
            f.write(f"{error}\n")

    print(f"JSON parsing failed. Response saved to {log_file}")

    # Return detailed error
    raise ValueError(
        f"Failed to parse JSON after all attempts. "
        f"Errors: {'; '.join(errors[:2])}. "
        f"Response saved to {log_file} for debugging."
    )


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
    except asyncio.TimeoutError as e:
        print(f"ERROR: Page navigation timeout for {request.url}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=504,
            detail="Page load timeout exceeded 60 seconds. The target website may be slow or unresponsive.",
        )
    except anthropic.APIError as e:
        print(f"ERROR: Anthropic API failure for {request.url}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=502, detail=f"AI analysis service failed: {str(e)}"
        )
    except ValueError as e:
        error_msg = str(e)
        print(
            f"ERROR: JSON parsing or validation failed for {request.url}: {error_msg}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=422, detail=f"Analysis parsing failed: {error_msg}"
        )
    except RuntimeError as e:
        error_msg = str(e)
        print(f"ERROR: Runtime error for {request.url}: {error_msg}")
        traceback.print_exc()
        if "browser" in error_msg.lower():
            raise HTTPException(
                status_code=503, detail=f"Browser service unavailable: {error_msg}"
            )
        raise HTTPException(status_code=500, detail=f"Service error: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: Unexpected failure for {request.url}: {error_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {error_msg}")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/status")
async def status_check():
    """
    Enhanced health check that verifies Playwright browser availability.

    Returns:
        - status: "healthy" if all systems operational, "degraded" if browser unavailable
        - playwright: Status of Playwright browser engine
        - anthropic_api: Status of Anthropic API key configuration
    """
    status_info = {
        "status": "healthy",
        "playwright": "unknown",
        "anthropic_api": "configured" if os.getenv("ANTHROPIC_API_KEY") else "missing",
    }

    # Test Playwright browser availability
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        status_info["playwright"] = "available"
    except Exception as e:
        status_info["playwright"] = f"unavailable: {str(e)}"
        status_info["status"] = "degraded"

    return status_info


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=60)
