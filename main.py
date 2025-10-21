import asyncio
import base64
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright
import anthropic
import os
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
import io

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


class AnalysisResponse(BaseModel):
    url: str
    analyzed_at: str
    issues: List[CROIssue]


# Initialize Anthropic client
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def resize_screenshot_if_needed(
    screenshot_bytes: bytes, max_dimension: int = 7500
) -> str:
    """
    Resize screenshot if any dimension exceeds max_dimension to comply with Claude's 8000px limit.
    Returns base64 encoded string of the (possibly resized) image.
    """
    # Open image from bytes
    image = Image.open(io.BytesIO(screenshot_bytes))
    width, height = image.size

    # Check if resizing is needed
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

        # Convert back to bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        screenshot_bytes = buffer.getvalue()

    # Return base64 encoded string
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def capture_screenshot_and_analyze(
    url: str, include_screenshots: bool = False
) -> AnalysisResponse:
    """
    Captures a screenshot of the website and analyzes it for CRO issues using Claude.

    Args:
        url: The website URL to analyze
        include_screenshots: If True, includes base64-encoded screenshots in the response. Default is False.
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

            # Analyze with Claude
            message = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"""You are a Conversion Rate Optimization (CRO) expert analyzing this website screenshot.

Website URL: {url}
Page Title: {page_title}

Analyze this website and identify exactly 2-3 quick CRO issues that should be addressed immediately. Focus on:
- Above-the-fold content and value proposition clarity
- Call-to-action (CTA) visibility and effectiveness
- Trust signals and social proof
- Mobile responsiveness concerns visible in the layout
- Form design and friction points
- Navigation and user flow issues

For each issue, provide:
1. A clear, concise title
2. A brief description of the problem
3. A specific, actionable recommendation to fix it

Format your response as JSON with this exact structure:
{{
  "issues": [
    {{
      "title": "Issue title here",
      "description": "What's wrong and why it matters",
      "recommendation": "Specific action to take"
    }}
  ]
}}

Return ONLY the JSON, no additional text.""",
                            },
                        ],
                    }
                ],
            )

            # Parse Claude's response
            response_text = message.content[0].text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = (
                    response_text.replace("```json", "").replace("```", "").strip()
                )
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()

            import json

            analysis_data = json.loads(response_text)

            # Create CROIssue objects with optional screenshots
            issues = [
                CROIssue(
                    title=issue["title"],
                    description=issue["description"],
                    recommendation=issue["recommendation"],
                    screenshot_base64=(
                        screenshot_base64 if include_screenshots else None
                    ),
                )
                for issue in analysis_data["issues"][:3]  # Limit to 3 issues
            ]

            return AnalysisResponse(
                url=str(url), analyzed_at=datetime.utcnow().isoformat(), issues=issues
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


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_website(request: AnalysisRequest):
    """
    Analyzes a website for CRO issues and returns 2-3 actionable recommendations.

    By default, screenshots are NOT included in the response for faster performance.
    Set include_screenshots=true in the request body to include base64-encoded screenshots.
    """
    try:
        result = await capture_screenshot_and_analyze(
            str(request.url), request.include_screenshots
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
