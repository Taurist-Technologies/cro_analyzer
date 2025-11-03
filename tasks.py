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
import time

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


class AnalysisTimeoutError(Exception):
    """Raised when analysis exceeds 60 seconds"""
    pass


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


async def _run_with_timeout(
    url: str, include_screenshots: bool, deep_info: bool, task, timeout_seconds: int = 60
):
    """
    Wrapper to run analysis with timeout and cleanup on failure.

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response
        deep_info: Use deep analysis mode
        task: Celery task instance for progress updates
        timeout_seconds: Timeout in seconds (default: 60)

    Returns:
        dict: Analysis result

    Raises:
        AnalysisTimeoutError: If analysis exceeds timeout_seconds
    """
    try:
        result = await asyncio.wait_for(
            _capture_and_analyze_async(url, include_screenshots, deep_info, task=task),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Analysis timeout after {timeout_seconds}s for {url}")

        # Cleanup: Clear cache for this URL
        try:
            redis_client = get_redis_client()
            cache_key = f"cache:analysis:{url}"
            redis_client.delete(cache_key)
            logger.info(f"🧹 Cleared cache for {url}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear cache during timeout cleanup: {e}")

        # Browser will be released by the finally block in _capture_and_analyze_async
        raise AnalysisTimeoutError(f"Analysis timed out after {timeout_seconds} seconds")


async def _capture_and_analyze_async(
    url: str, include_screenshots: bool = False, deep_info: bool = False, task=None
) -> dict:
    """
    Async function to capture screenshot and analyze with Claude.
    This is the core logic extracted from main.py for reuse in Celery tasks.
    Now includes progress updates via task.update_state()
    """
    # STEP 1: Acquire browser (10% progress)
    if task:
        task.update_state(
            state='PROGRESS',
            meta={
                'current': 1,
                'total': 5,
                'percent': 10,
                'status': 'Acquiring browser from pool...',
                'url': str(url)
            }
        )

    # Get browser from pool (or create temporary one)
    try:
        pool = await get_browser_pool()
        # Add 15-second timeout to pool.acquire() to prevent hanging
        browser, context, page = await asyncio.wait_for(
            pool.acquire(),
            timeout=15
        )
        use_pool = True
    except asyncio.TimeoutError:
        logger.warning(
            f"⚠️ Browser pool acquisition timed out after 15s, using standalone browser"
        )
        # Fallback to standalone browser
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        use_pool = False
    except Exception as e:
        logger.warning(f"⚠️  Browser pool unavailable, using standalone browser: {str(e)}")
        # Fallback to standalone browser
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        use_pool = False

    try:
        # STEP 2: Load page (30% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 2,
                    'total': 5,
                    'percent': 30,
                    'status': f'Loading webpage: {url}',
                    'url': str(url)
                }
            )

        # Navigate to the URL with progressive timeout retry
        logger.info(f"📡 Navigating to {url}")
        nav_start = time.time()

        # Try with 60s timeout first
        nav_success = False
        attempt = 1
        timeout_ms = 60000

        while attempt <= 2 and not nav_success:
            try:
                logger.info(f"🔄 Navigation attempt {attempt} with {timeout_ms/1000}s timeout")
                await page.goto(str(url), wait_until="load", timeout=timeout_ms)
                nav_success = True
                nav_duration = time.time() - nav_start
                logger.info(f"⏱️  Page navigation completed in {nav_duration:.2f}s (attempt {attempt})")
            except Exception as nav_error:
                if attempt == 1 and "Timeout" in str(nav_error):
                    logger.warning(f"⚠️  Navigation timeout at {timeout_ms/1000}s, retrying with {120}s timeout...")
                    timeout_ms = 120000  # Retry with 120s timeout
                    attempt += 1
                else:
                    # Not a timeout or second attempt failed
                    raise

        if not nav_success:
            raise Exception(f"Failed to navigate to {url} after 2 attempts")

        # Wait for dynamic content
        await page.wait_for_timeout(2000)

        # STEP 3: Capture screenshot (50% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 3,
                    'total': 5,
                    'percent': 50,
                    'status': 'Capturing full page screenshot...',
                    'url': str(url)
                }
            )

        # Capture full page screenshot
        logger.info(f"📸 Capturing screenshot of {url}")
        screenshot_start = time.time()
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)
        screenshot_duration = time.time() - screenshot_start
        logger.info(f"⏱️  Screenshot capture completed in {screenshot_duration:.2f}s")

        # Get page title
        page_title = await page.title()
        logger.info(f"📄 Page title: {page_title}")

        # Get the appropriate prompt
        cro_prompt = get_cro_prompt(deep_info=deep_info)

        # STEP 4: AI Analysis (70% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 4,
                    'total': 5,
                    'percent': 70,
                    'status': 'Analyzing with Claude AI (this may take 5-10 seconds)...',
                    'url': str(url)
                }
            )

        # Analyze with Claude (with retry logic)
        logger.info(f"🤖 Analyzing {url} with Claude AI...")
        api_start = time.time()
        message = call_anthropic_api_with_retry(
            screenshot_base64=screenshot_base64,
            cro_prompt=cro_prompt,
            url=str(url),
            page_title=page_title,
            deep_info=deep_info,
        )
        api_duration = time.time() - api_start
        logger.info(f"⏱️  Claude API call completed in {api_duration:.2f}s")

        # STEP 5: Parse results (90% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 5,
                    'total': 5,
                    'percent': 90,
                    'status': 'Parsing analysis results...',
                    'url': str(url)
                }
            )

        # Parse Claude's response
        logger.info(f"🔍 Parsing Claude response...")
        parse_start = time.time()
        response_text = message.content[0].text.strip()

        # LOG: Raw response details for debugging
        logger.info(f"📝 Raw response length: {len(response_text)} characters")
        logger.info(f"📝 Raw response preview (first 500 chars): {response_text[:500]}")
        logger.info(f"📝 Raw response starts with: {response_text[:50]}")

        # Save full raw response to file for detailed analysis (only on parsing failures)
        raw_response_for_file = response_text

        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
            logger.info(f"📝 Removed ```json markdown wrapper")
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()
            logger.info(f"📝 Removed ``` markdown wrapper")

        # Extract JSON from response if wrapped in text
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                response_text = response_text[start_idx : end_idx + 1]
                logger.info(f"📝 Extracted JSON from position {start_idx} to {end_idx}")
            else:
                logger.warning(f"⚠️  No JSON object found in response (no {{ or }})")

        logger.info(f"📝 Cleaned response preview (first 500 chars): {response_text[:500]}")

        # Parse JSON with multi-layer repair
        analysis_data = repair_and_parse_json(response_text, deep_info=deep_info)

        # LOG: Save raw response to file if parsing failed or returned no issues
        if analysis_data.get("total_issues_identified", 0) == 0 or len(analysis_data.get("issues", [])) == 0:
            import os
            from urllib.parse import urlparse
            log_dir = "/app/logs" if os.path.exists("/app/logs") else "./logs"
            os.makedirs(log_dir, exist_ok=True)
            # Extract hostname from URL string for filename
            hostname = urlparse(str(url)).netloc.replace(":", "_").replace("/", "_")
            log_file = f"{log_dir}/claude_response_{hostname}_{int(time.time())}.txt"
            try:
                with open(log_file, "w") as f:
                    f.write("=== RAW CLAUDE RESPONSE ===\n")
                    f.write(raw_response_for_file)
                    f.write("\n\n=== CLEANED RESPONSE ===\n")
                    f.write(response_text)
                    f.write("\n\n=== PARSED DATA ===\n")
                    f.write(str(analysis_data))
                logger.warning(f"⚠️  Parsing resulted in 0 issues - saved full response to {log_file}")
            except Exception as e:
                logger.error(f"❌ Failed to save raw response to file: {e}")

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
            # Flexible matching for various key formats
            accepted_prefixes = ["key point", "keypoint", "issue", "finding", "point"]

            logger.info(f"DEBUG: Keys received from Claude: {list(analysis_data.keys())}")

            for key, value in analysis_data.items():
                if isinstance(value, dict):
                    # Check if key matches any accepted pattern (case-insensitive)
                    key_lower = key.lower().strip()
                    if any(key_lower.startswith(prefix) for prefix in accepted_prefixes):
                        logger.info(f"DEBUG: Matched key '{key}' as issue")
                        issues.append({
                            "title": key,
                            "description": value.get("Issue", "") or value.get("issue", "") or value.get("description", ""),
                            "recommendation": value.get("Recommendation", "") or value.get("recommendation", "") or value.get("solution", ""),
                            "screenshot_base64": screenshot_base64 if include_screenshots else None,
                        })

            result = {
                "url": str(url),
                "analyzed_at": datetime.utcnow().isoformat(),
                "issues": issues[:3],  # Limit to 3 issues
                "deep_info": False,
            }

        parse_duration = time.time() - parse_start
        logger.info(f"⏱️  Response parsing completed in {parse_duration:.2f}s")
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
    autoretry_for=(),  # Disable auto-retry, we'll handle manually
    max_retries=3,
    time_limit=720,  # Hard limit: 12 minutes (kills task)
    soft_time_limit=600,  # Soft limit: 10 minutes (raises exception)
)
def analyze_website(
    self, url: str, include_screenshots: bool = False, deep_info: bool = False
) -> dict:
    """
    Celery task to analyze a website for CRO issues.
    Includes 60-second timeout with automatic retry (up to 3 attempts).

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response
        deep_info: Use deep analysis mode (5 issues + scores)

    Returns:
        Dictionary with analysis results

    Raises:
        Exception: After 3 failed attempts or on non-recoverable errors
    """
    task_id = self.request.id
    retry_count = self.request.retries

    # Show RETRYING status if this is a retry
    if retry_count > 0:
        self.update_state(
            state='RETRYING',
            meta={
                'attempt': retry_count + 1,
                'max_attempts': 3,
                'reason': 'Previous attempt timed out after 60 seconds',
                'url': str(url),
                'message': f'Retrying analysis... (attempt {retry_count + 1} of 3)'
            }
        )
        logger.info(f"🔄 Retry attempt {retry_count + 1}/3 for {url}")

        # 2-second delay between retries
        time.sleep(2)
    else:
        logger.info(f"🚀 Starting analysis task {task_id} for {url}")

    try:
        # Check cache first (skip cache on retries to ensure fresh attempt)
        if retry_count == 0:
            redis_client = get_redis_client()
            cached_result = redis_client.get_cached_analysis(url)

            if cached_result:
                logger.info(f"💾 Cache hit for {url}, returning cached result")
                return cached_result
        else:
            logger.info(f"🔄 Retry attempt - skipping cache check for {url}")

        # Run async analysis with 60-second timeout
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _run_with_timeout(url, include_screenshots, deep_info, task=self, timeout_seconds=60)
            )
        finally:
            loop.close()

        # Cache the result (24 hours)
        redis_client = get_redis_client()
        redis_client.cache_analysis(url, result, ttl=86400)

        return result

    except AnalysisTimeoutError as e:
        logger.error(f"⏱️ Timeout error for {url}: {str(e)}")

        # Retry up to 3 times
        if retry_count < 2:  # 0, 1 = first 2 retries (total 3 attempts)
            logger.info(f"🔄 Scheduling retry {retry_count + 2}/3 for {url}")
            raise self.retry(exc=e, countdown=0)  # Immediate retry (delay handled above)
        else:
            # All retries exhausted
            logger.error(f"❌ All 3 retry attempts exhausted for {url}")
            raise Exception("Analysis failed after 3 attempts. Timeout after 60 seconds on each attempt. See logs for details.")

    except Exception as e:
        logger.error(f"❌ Task failed for {url}: {str(e)}")

        # For non-timeout errors, don't retry
        raise Exception(f"Analysis failed: {str(e)}")


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
