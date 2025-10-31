"""
Celery background tasks for CRO Analyzer
Handles screenshot capture and analysis in background workers
"""

import asyncio
import base64
from datetime import datetime
from typing import Union
import os
import logging

from celery import Task
from celery_app import celery_app
from playwright.async_api import async_playwright
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from analysis_prompt import get_cro_prompt
from redis_client import get_redis_client
from browser_pool import get_browser_pool
from main import (
    resize_screenshot_if_needed,
    repair_and_parse_json,
    CROIssue,
    AnalysisResponse,
    DeepAnalysisResponse,
    ExecutiveSummary,
    ScoreDetails,
    ConversionPotential,
)

logger = logging.getLogger(__name__)

# Initialize Anthropic client (synchronous for Celery compatibility)
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class CallbackTask(Task):
    """
    Custom Celery task class with callbacks and cleanup.
    """

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        logger.info(f"✅ Task {task_id} completed successfully")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        logger.error(f"❌ Task {task_id} failed: {str(exc)}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried"""
        logger.warning(f"🔄 Task {task_id} retrying: {str(exc)}")


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


async def _capture_and_analyze_async(
    url: str, include_screenshots: bool = False, deep_info: bool = False
) -> dict:
    """
    Async function to capture screenshot and analyze with Claude.
    This is the core logic extracted from main.py for reuse in Celery tasks.
    """
    # Get browser from pool (or create temporary one)
    try:
        pool = await get_browser_pool(pool_size=5)
        browser, context, page = await pool.acquire()
        use_pool = True
    except Exception as e:
        logger.warning(f"⚠️  Browser pool unavailable, using standalone browser: {str(e)}")
        # Fallback to standalone browser
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        use_pool = False

    try:
        # Navigate to the URL
        logger.info(f"📡 Navigating to {url}")
        await page.goto(str(url), wait_until="load", timeout=90000)

        # Wait for dynamic content
        await page.wait_for_timeout(2000)

        # Capture full page screenshot
        logger.info(f"📸 Capturing screenshot of {url}")
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)

        # Get page title
        page_title = await page.title()
        logger.info(f"📄 Page title: {page_title}")

        # Get the appropriate prompt
        cro_prompt = get_cro_prompt(deep_info=deep_info)

        # Analyze with Claude (with retry logic)
        logger.info(f"🤖 Analyzing {url} with Claude AI...")
        message = call_anthropic_api_with_retry(
            screenshot_base64=screenshot_base64,
            cro_prompt=cro_prompt,
            url=str(url),
            page_title=page_title,
            deep_info=deep_info,
        )

        # Parse Claude's response
        response_text = message.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()

        # Extract JSON from response if wrapped in text
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                response_text = response_text[start_idx : end_idx + 1]

        # Parse JSON with multi-layer repair
        analysis_data = repair_and_parse_json(response_text, deep_info=deep_info)

        # Build response based on format
        issues = []

        if deep_info:
            # Deep info format
            if "top_5_issues" in analysis_data:
                for issue in analysis_data["top_5_issues"][:5]:
                    issues.append({
                        "title": issue.get("issue_title", ""),
                        "description": (
                            issue.get("whats_wrong", "")
                            + "\n\nWhy it matters: "
                            + issue.get("why_it_matters", "")
                        ),
                        "recommendation": "\n".join(issue.get("implementation_ideas", [])),
                        "screenshot_base64": screenshot_base64 if include_screenshots else None,
                    })

            result = {
                "url": str(url),
                "analyzed_at": datetime.utcnow().isoformat(),
                "issues": issues,
                "total_issues_identified": analysis_data.get("total_issues_identified", len(issues)),
                "executive_summary": {
                    "overview": analysis_data.get("executive_summary", {}).get("overview", ""),
                    "how_to_act": analysis_data.get("executive_summary", {}).get("how_to_act", ""),
                },
                "cro_analysis_score": {
                    "score": analysis_data.get("cro_analysis_score", {}).get("score", 0),
                    "calculation": analysis_data.get("cro_analysis_score", {}).get("calculation", ""),
                    "rating": analysis_data.get("cro_analysis_score", {}).get("rating", ""),
                },
                "site_performance_score": {
                    "score": analysis_data.get("site_performance_score", {}).get("score", 0),
                    "calculation": analysis_data.get("site_performance_score", {}).get("calculation", ""),
                    "rating": analysis_data.get("site_performance_score", {}).get("rating", ""),
                },
                "conversion_rate_increase_potential": {
                    "percentage": analysis_data.get("conversion_rate_increase_potential", {}).get("percentage", ""),
                    "confidence": analysis_data.get("conversion_rate_increase_potential", {}).get("confidence", ""),
                    "rationale": analysis_data.get("conversion_rate_increase_potential", {}).get("rationale", ""),
                },
                "deep_info": True,
            }
        else:
            # Standard format (2-3 key points)
            for key, value in analysis_data.items():
                if key.startswith("Key point"):
                    issues.append({
                        "title": key,
                        "description": value.get("Issue", ""),
                        "recommendation": value.get("Recommendation", ""),
                        "screenshot_base64": screenshot_base64 if include_screenshots else None,
                    })

            result = {
                "url": str(url),
                "analyzed_at": datetime.utcnow().isoformat(),
                "issues": issues[:3],  # Limit to 3 issues
                "deep_info": False,
            }

        logger.info(f"✅ Analysis complete for {url}: {len(issues)} issues found")
        return result

    finally:
        # Cleanup
        if use_pool:
            await pool.release(browser, context, page)
        else:
            await page.close()
            await context.close()
            await browser.close()


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="tasks.analyze_website",
    max_retries=3,
    default_retry_delay=60,
)
def analyze_website(
    self, url: str, include_screenshots: bool = False, deep_info: bool = False
) -> dict:
    """
    Celery task to analyze a website for CRO issues.

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response
        deep_info: Use deep analysis mode (5 issues + scores)

    Returns:
        Dictionary with analysis results
    """
    task_id = self.request.id
    logger.info(f"🚀 Starting analysis task {task_id} for {url}")

    try:
        # Check cache first
        redis_client = get_redis_client()
        cached_result = redis_client.get_cached_analysis(url)

        if cached_result:
            logger.info(f"💾 Cache hit for {url}, returning cached result")
            return cached_result

        # Run async analysis in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _capture_and_analyze_async(url, include_screenshots, deep_info)
            )
        finally:
            loop.close()

        # Cache the result (24 hours)
        redis_client.cache_analysis(url, result, ttl=86400)

        return result

    except anthropic.APIError as e:
        logger.error(f"❌ Anthropic API error for {url}: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

    except Exception as e:
        logger.error(f"❌ Task failed for {url}: {str(e)}")
        raise


@celery_app.task(name="tasks.cleanup_old_results")
def cleanup_old_results():
    """
    Periodic task to cleanup old cached results.
    This is an example task that can be enabled in celery_app.py beat schedule.
    """
    try:
        redis_client = get_redis_client()
        deleted_count = redis_client.clear_cache("cache:analysis:*")
        logger.info(f"🧹 Cleaned up {deleted_count} old cached results")
        return {"deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"❌ Cleanup task failed: {str(e)}")
        raise


@celery_app.task(name="tasks.get_pool_health")
def get_pool_health() -> dict:
    """
    Task to check browser pool health (for monitoring).
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            pool = loop.run_until_complete(get_browser_pool())
            health = loop.run_until_complete(pool.health_check())
            return health
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"❌ Pool health check failed: {str(e)}")
        return {"status": "error", "error": str(e)}
