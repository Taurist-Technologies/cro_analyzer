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
from core.celery import celery_app
from playwright.async_api import async_playwright
import anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from analyzer.prompts import get_cro_prompt
from core.cache import get_redis_client
from core.browser import get_browser_pool
from utils.images.processor import resize_screenshot_if_needed
from utils.parsing.json import repair_and_parse_json
from api.models import CROIssue, AnalysisResponse, DeepAnalysisResponse
from utils.clients.anthropic import call_anthropic_api_with_retry
from analyzer.sections.analyzer import SectionAnalyzer
from analyzer.patterns import VectorDBClient

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


async def _run_with_timeout(
    url: str,
    include_screenshots: bool,
    task,
    timeout_seconds: int = 150,
):
    """
    Wrapper to run analysis with timeout and cleanup on failure.

    CRITICAL: This function uses a shared result holder to prevent losing
    successful analysis results when timeout fires during browser cleanup.
    The analysis might complete successfully, but if the timeout fires while
    page.close() is running, we don't want to discard the valid result.

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response
        task: Celery task instance for progress updates
        timeout_seconds: Timeout in seconds (default: 100)

    Returns:
        dict: Analysis result with section-based CRO analysis

    Raises:
        AnalysisTimeoutError: If analysis exceeds timeout_seconds (and no result was obtained)
    """
    # Shared result holder - accessible after timeout
    result_holder = {"result": None, "completed": False}

    try:
        result = await asyncio.wait_for(
            _capture_and_analyze_async(
                url, include_screenshots, task=task, result_holder=result_holder
            ),
            timeout=timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"⏱️ Analysis timeout after {timeout_seconds}s for {url}")

        # CHECK: Did analysis complete successfully before timeout fired during cleanup?
        if result_holder["completed"] and result_holder["result"] is not None:
            logger.info(
                f"✅ Recovered successful result despite timeout (analysis completed before cleanup)"
            )
            return result_holder["result"]

        # Genuine timeout - analysis didn't complete
        # Cleanup: Clear cache for this URL
        try:
            redis_client = get_redis_client()
            cache_key = f"cache:analysis:{url}"
            redis_client.delete(cache_key)
            logger.info(f"🧹 Cleared cache for {url}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear cache during timeout cleanup: {e}")

        # Browser will be released by the finally block in _capture_and_analyze_async
        raise AnalysisTimeoutError(
            f"Analysis timed out after {timeout_seconds} seconds"
        )


async def _capture_and_analyze_async(
    url: str, include_screenshots: bool = False, task=None, result_holder=None
) -> dict:
    """
    Async function to capture section screenshots and analyze with Claude.
    This is the core logic extracted from main.py for reuse in Celery tasks.
    Uses section-based analysis with historical pattern matching from ChromaDB.

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response
        task: Celery task instance for progress updates

    Returns:
        dict: Analysis result with 5 quick_wins and 5 scorecards
    """
    # STEP 1: Acquire browser (10% progress)
    if task:
        task.update_state(
            state="PROGRESS",
            meta={
                "current": 1,
                "total": 5,
                "percent": 10,
                "status": "We load your site like a real visitor so we see what they see...",
                "url": str(url),
            },
        )

    # Get browser from pool (or create temporary one)
    try:
        pool = await get_browser_pool()
        # Add 15-second timeout to pool.acquire() to prevent hanging
        browser, context, page = await asyncio.wait_for(pool.acquire(), timeout=15)
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
        logger.warning(
            f"⚠️  Browser pool unavailable, using standalone browser: {str(e)}"
        )
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
                state="PROGRESS",
                meta={
                    "current": 2,
                    "total": 5,
                    "percent": 30,
                    "status": f"Waiting until images, fonts, and sections finish so nothing is missed...",
                    "url": str(url),
                },
            )

        # Navigate to the URL with progressive timeout retry
        logger.info(f"📡 Navigating to {url}")
        nav_start = time.time()

        # Try with 80s timeout first
        nav_success = False
        attempt = 1
        timeout_ms = 80000

        while attempt <= 2 and not nav_success:
            try:
                logger.info(
                    f"🔄 Navigation attempt {attempt} with {timeout_ms/1000}s timeout"
                )
                await page.goto(str(url), wait_until="load", timeout=timeout_ms)
                nav_success = True
                nav_duration = time.time() - nav_start
                logger.info(
                    f"⏱️  Page navigation completed in {nav_duration:.2f}s (attempt {attempt})"
                )
            except Exception as nav_error:
                if attempt == 1 and "Timeout" in str(nav_error):
                    logger.warning(
                        f"⚠️  Navigation timeout at {timeout_ms/1000}s, retrying with {120}s timeout..."
                    )
                    timeout_ms = 120000  # Retry with 120s timeout
                    attempt += 1
                else:
                    # Not a timeout or second attempt failed
                    raise

        if not nav_success:
            raise Exception(f"Failed to navigate to {url} after 2 attempts")

        # Wait for dynamic content
        await page.wait_for_timeout(2000)

        # STEP 2.5: Run interactive tests to verify functionality (NEW - prevents false positives)
        logger.info(f"🧪 Running interactive tests to verify page functionality")
        from utils.testing.interactions import InteractionTester

        interaction_tester = InteractionTester(page)
        interaction_results = await interaction_tester.run_all_tests()

        logger.info(f"✓ Interactive testing complete - {len(interaction_results['findings'])} findings")

        # STEP 2.6: Dismiss all overlays before screenshots (prevents false positives)
        logger.info(f"🧹 Dismissing overlays for clean screenshots")
        from utils.testing.overlays import OverlayDismisser

        overlay_dismisser = OverlayDismisser(page)
        overlay_results = await overlay_dismisser.dismiss_all_overlays()

        # Add overlay results to interaction results for Claude prompt
        interaction_results["overlay_dismissal"] = overlay_results
        interaction_results["verified_visible_elements"] = overlay_results.get("revealed_elements", [])

        logger.info(f"✓ Overlay dismissal complete - {len(overlay_results.get('overlays_dismissed', []))} dismissed, {len(overlay_results.get('revealed_elements', []))} elements verified")

        # STEP 2.7: Detect CRO elements at both viewports (Layer 1 - prevents false positives)
        logger.info(f"🔍 Detecting CRO elements at both viewports (pre-analysis)")
        from utils.testing.element_detector import detect_elements_both_viewports

        detected_elements = await detect_elements_both_viewports(page)
        desktop_types_found = len(detected_elements.get("desktop", {}).get("summary", {}).get("element_types_found", []))
        mobile_types_found = len(detected_elements.get("mobile", {}).get("summary", {}).get("element_types_found", []))
        logger.info(f"✓ Element detection complete - Desktop: {desktop_types_found} types, Mobile: {mobile_types_found} types")

        # Initialize VectorDBClient for historical patterns (OPTIONAL - falls back to CRO best practices)
        vector_db = None
        try:
            vector_db = VectorDBClient()
            logger.info(f"✓ VectorDB client initialized for historical pattern matching")
        except Exception as e:
            logger.warning(f"⚠️ VectorDB unavailable: {e}")
            logger.warning(f"⚠️ Continuing with CRO best practices (no historical pattern grounding)")
            vector_db = None

        # STEP 3: Capture screenshot (50% progress)
        if task:
            task.update_state(
                state="PROGRESS",
                meta={
                    "current": 3,
                    "total": 5,
                    "percent": 50,
                    "status": "Full-page snapshot and basic speed signals to give the audit context...",
                    "url": str(url),
                },
            )

        # Get page title
        page_title = await page.title()
        logger.info(f"📄 Page title: {page_title}")

        # Section-based analysis with historical patterns
        logger.info(f"📸 Starting section-based screenshot capture for {url}")
        screenshot_start = time.time()

        # Initialize SectionAnalyzer
        section_analyzer = SectionAnalyzer(page, vector_db=vector_db)

        # Capture viewport screenshots (desktop and mobile)
        viewport_screenshots = await section_analyzer.capture_viewport_screenshots()

        # Analyze page sections (captures desktop + mobile screenshots, queries ChromaDB)
        analysis_data = await section_analyzer.analyze_page_sections(
            include_screenshots=True,
            include_mobile=True
        )

        # Format context for Claude prompt
        section_context = section_analyzer.format_for_claude_prompt(analysis_data)

        # INFORMATIONAL: Log historical pattern availability
        total_patterns = sum(
            len(section.get("historical_patterns", []))
            for section in section_context["sections"]
        )

        if total_patterns == 0:
            warning_msg = (
                f"⚠️  No historical patterns found (>60% similarity) for any sections.\n"
                f"Analysis will proceed using CRO best practices and observable issues.\n"
                f"Sections analyzed: {', '.join([s['name'] for s in section_context['sections']])}"
            )
            logger.warning(warning_msg)
        else:
            logger.info(f"✓ Found {total_patterns} historical patterns across {len(section_context['sections'])} sections (>60% similarity)")

        # Extract section screenshots as list of base64 strings
        section_screenshots = [
            section['screenshot_base64']
            for section in section_context['sections']
            if section.get('screenshot_base64')
        ]

        # Extract mobile screenshot
        mobile_screenshot = section_context.get('mobile_screenshot')

        screenshot_duration = time.time() - screenshot_start
        logger.info(f"⏱️  Section-based screenshot capture completed in {screenshot_duration:.2f}s")
        logger.info(f"📊 Captured {len(section_screenshots)} section screenshots + mobile screenshot")

        # Get prompt with section context and detected elements (prevents false positives)
        cro_prompt = get_cro_prompt(section_context=section_context, detected_elements=detected_elements)

        # STEP 4: AI Analysis (70% progress)
        if task:
            task.update_state(
                state="PROGRESS",
                meta={
                    "current": 4,
                    "total": 5,
                    "percent": 70,
                    "status": "Our model reviews your layout and copy, compares them to 20,000+ proven CRO patterns, spots friction and trust gaps, and drafts 1–2 quick fixes for each issue...",
                    "url": str(url),
                },
            )

        # Analyze with Claude (with retry logic)
        logger.info(f"🤖 Analyzing {url} with Claude AI...")
        api_start = time.time()
        message = call_anthropic_api_with_retry(
            cro_prompt=cro_prompt,
            url=str(url),
            page_title=page_title,
            section_screenshots=section_screenshots,
            mobile_screenshot=mobile_screenshot,
            interaction_results=interaction_results,
        )
        api_duration = time.time() - api_start
        logger.info(f"⏱️  Claude API call completed in {api_duration:.2f}s")

        # STEP 5: Parse results (90% progress)
        if task:
            task.update_state(
                state="PROGRESS",
                meta={
                    "current": 5,
                    "total": 5,
                    "percent": 90,
                    "status": "We score by Impact • Confidence • Effort and format your report...",
                    "url": str(url),
                },
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
            response_text = (
                response_text.replace("```json", "").replace("```", "").strip()
            )
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

        logger.info(
            f"📝 Cleaned response preview (first 500 chars): {response_text[:500]}"
        )

        # Parse JSON with multi-layer repair (always uses enhanced mode structure)
        analysis_data = repair_and_parse_json(response_text)

        # LOG: Save raw response to file if parsing failed or returned no issues
        if (
            analysis_data.get("total_issues_identified", 0) == 0
            or len(analysis_data.get("issues", [])) == 0
        ):
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
                logger.warning(
                    f"⚠️  Parsing resulted in 0 issues - saved full response to {log_file}"
                )
            except Exception as e:
                logger.error(f"❌ Failed to save raw response to file: {e}")

        # STEP 5.5: Post-validate recommendations to filter false positives (Layers 2 & 3)
        logger.info(f"🔍 Post-validating Claude recommendations against live page")
        from utils.validation.recommendation_validator import validate_issues_both_viewports
        from utils.validation.ai_validator import ai_validate_uncertain_issues

        # Convert quick_wins to issue format for validation
        # Take up to 10 issues as buffer - validation will filter false positives, then we return exactly 5
        raw_issues = []
        if "quick_wins" in analysis_data:
            for quick_win in analysis_data["quick_wins"][:10]:
                raw_issues.append({
                    "section": quick_win.get("section", ""),
                    "title": quick_win.get("issue_title", ""),
                    "description": quick_win.get("whats_wrong", ""),
                    "why_it_matters": quick_win.get("why_it_matters", ""),
                    "recommendations": quick_win.get("recommendations", []),
                    "priority_score": quick_win.get("priority_score", 0),
                    "priority_rationale": quick_win.get("priority_rationale", ""),
                })

        # Layer 2: Playwright post-validation
        validated_issues, filtered_issues, validation_stats = await validate_issues_both_viewports(
            page, raw_issues
        )
        logger.info(f"🔍 Playwright validation: {len(validated_issues)} kept, {len(filtered_issues)} filtered")

        # Layer 3: AI post-validation for uncertain cases
        uncertain_issues = [
            i for i in validated_issues
            if i.get("validation", {}).get("needs_ai_validation", False)
        ]

        if uncertain_issues:
            logger.info(f"🤖 AI validating {len(uncertain_issues)} uncertain issues")
            ai_kept, ai_filtered, ai_stats = await ai_validate_uncertain_issues(
                anthropic_client, page, uncertain_issues
            )
            # Update validated_issues: remove uncertain ones and add back AI-validated ones
            validated_issues = [
                i for i in validated_issues
                if not i.get("validation", {}).get("needs_ai_validation", False)
            ] + ai_kept
            filtered_issues.extend(ai_filtered)
            logger.info(f"🤖 AI validation: {ai_stats.get('ai_kept', 0)} kept, {ai_stats.get('ai_filtered', 0)} filtered")

        # Log summary of false positive filtering
        total_filtered = len(filtered_issues)
        if total_filtered > 0:
            logger.info(f"⚠️  Filtered {total_filtered} false positive recommendations:")
            for fp in filtered_issues:
                reason = fp.get("validation", {}).get("reason", "Unknown")
                logger.info(f"   - '{fp.get('title', 'Unknown')}': {reason}")

        # Build response with section-based enhanced mode format
        issues = []

        # Sort validated issues by priority score and take EXACTLY 5 (or fewer if not enough passed validation)
        # User requirement: Always return exactly 5 issues to display (total_issues_identified can be any number)
        sorted_validated = sorted(validated_issues, key=lambda x: x.get("priority_score", 0), reverse=True)
        final_issues = sorted_validated[:5]  # Cap at exactly 5 issues

        if len(final_issues) < 5:
            logger.warning(f"⚠️ Only {len(final_issues)} issues passed validation (expected exactly 5)")
        else:
            logger.info(f"✅ Returning top 5 validated issues from {len(validated_issues)} that passed validation")

        # Use validated issues (false positives already filtered)
        for issue in final_issues:
            issues.append(
                {
                    "section": issue.get("section", ""),
                    "title": issue.get("title", ""),
                    "description": issue.get("description", ""),
                    "why_it_matters": issue.get("why_it_matters", ""),
                    "recommendations": issue.get("recommendations", []),
                    "priority_score": issue.get("priority_score", 0),
                    "priority_rationale": issue.get("priority_rationale", ""),
                    "screenshot_base64": None,  # Section screenshots not included in issues
                    "validation": issue.get("validation"),  # Include validation metadata
                }
            )

        result = {
            "url": str(url),
            "analyzed_at": datetime.utcnow().isoformat(),
            "total_issues_identified": analysis_data.get("total_issues_identified", len(issues)),
            "issues": issues,  # Quick wins
            "scorecards": {
                "ux_design": {
                    "score": analysis_data.get("scorecards", {}).get("ux_design", {}).get("score", 0),
                    "color": analysis_data.get("scorecards", {}).get("ux_design", {}).get("color", "yellow"),
                    "rationale": analysis_data.get("scorecards", {}).get("ux_design", {}).get("rationale", ""),
                },
                "content_copy": {
                    "score": analysis_data.get("scorecards", {}).get("content_copy", {}).get("score", 0),
                    "color": analysis_data.get("scorecards", {}).get("content_copy", {}).get("color", "yellow"),
                    "rationale": analysis_data.get("scorecards", {}).get("content_copy", {}).get("rationale", ""),
                },
                "site_performance": {
                    "score": analysis_data.get("scorecards", {}).get("site_performance", {}).get("score", 0),
                    "color": analysis_data.get("scorecards", {}).get("site_performance", {}).get("color", "yellow"),
                    "rationale": analysis_data.get("scorecards", {}).get("site_performance", {}).get("rationale", ""),
                },
                "conversion_potential": {
                    "score": analysis_data.get("scorecards", {}).get("conversion_potential", {}).get("score", 0),
                    "color": analysis_data.get("scorecards", {}).get("conversion_potential", {}).get("color", "yellow"),
                    "rationale": analysis_data.get("scorecards", {}).get("conversion_potential", {}).get("rationale", ""),
                },
                "mobile_experience": {
                    "score": analysis_data.get("scorecards", {}).get("mobile_experience", {}).get("score", 0),
                    "color": analysis_data.get("scorecards", {}).get("mobile_experience", {}).get("color", "yellow"),
                    "rationale": analysis_data.get("scorecards", {}).get("mobile_experience", {}).get("rationale", ""),
                },
            },
            "executive_summary": {
                "overview": analysis_data.get("executive_summary", {}).get("overview", ""),
                "how_to_act": analysis_data.get("executive_summary", {}).get("how_to_act", ""),
            },
            "conversion_rate_increase_potential": {
                "percentage": analysis_data.get("conversion_rate_increase_potential", {}).get("percentage", ""),
                "confidence": analysis_data.get("conversion_rate_increase_potential", {}).get("confidence", ""),
                "rationale": analysis_data.get("conversion_rate_increase_potential", {}).get("rationale", ""),
            },
            "desktop_viewport_screenshot": viewport_screenshots.get("desktop"),
            "mobile_viewport_screenshot": viewport_screenshots.get("mobile"),
        }

        parse_duration = time.time() - parse_start
        logger.info(f"⏱️  Response parsing completed in {parse_duration:.2f}s")
        logger.info(f"✅ Analysis complete for {url}: {len(issues)} issues found")

        # CRITICAL: Store result in shared holder BEFORE cleanup starts
        # This allows _run_with_timeout to recover the result if timeout fires during cleanup
        if result_holder is not None:
            result_holder["result"] = result
            result_holder["completed"] = True
            logger.debug(f"📦 Result saved to holder before cleanup")

        # IMPORTANT: Set analysis_complete flag BEFORE returning
        # This ensures result is preserved even if timeout fires during cleanup
        analysis_complete = True
        final_result = result

    except Exception as e:
        # Re-raise any analysis errors
        raise

    finally:
        # Cleanup - wrapped in try/except to prevent cleanup errors from losing results
        # This is critical: if timeout fires during cleanup, we still want to return the result
        try:
            if use_pool:
                await pool.release(browser, context, page)
            else:
                if page:
                    await page.close()
                if context:
                    await context.close()
                if browser:
                    await browser.close()
        except Exception as cleanup_error:
            # Log but don't raise - cleanup failures shouldn't lose analysis results
            logger.warning(f"⚠️ Browser cleanup warning (analysis result preserved): {cleanup_error}")

    return final_result


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
    self, url: str, include_screenshots: bool = False
) -> dict:
    """
    Celery task to analyze a website for CRO issues using section-based analysis.
    Includes 80-second timeout with automatic retry (up to 3 attempts).

    Args:
        url: Website URL to analyze
        include_screenshots: Include base64 screenshots in response

    Returns:
        Dictionary with analysis results containing:
        - Quick wins (5 prioritized CRO issues)
        - Scorecards (UX, Content, Performance, Conversion, Mobile)
        - Executive summary
        - Conversion rate increase potential

    Raises:
        Exception: After 3 failed attempts or on non-recoverable errors
    """
    task_id = self.request.id
    retry_count = self.request.retries

    # Show RETRYING status if this is a retry
    if retry_count > 0:
        self.update_state(
            state="RETRYING",
            meta={
                "attempt": retry_count + 1,
                "max_attempts": 3,
                "reason": "Previous attempt timed out after 60 seconds",
                "url": str(url),
                "message": f"Performance issue detected. Retrying analysis... (attempt {retry_count + 1} of 3)",
            },
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

        # Run async analysis with 100-second timeout (always uses section-based analysis)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _run_with_timeout(
                    url, include_screenshots, task=self, timeout_seconds=150
                )
            )
        finally:
            loop.close()

        # Cache the result (72 hours)
        redis_client = get_redis_client()
        redis_client.cache_analysis(url, result, ttl=259200)

        return result

    except AnalysisTimeoutError as e:
        logger.error(f"⏱️ Timeout error for {url}: {str(e)}")

        # Retry up to 3 times
        if retry_count < 2:  # 0, 1 = first 2 retries (total 3 attempts)
            logger.info(f"🔄 Scheduling retry {retry_count + 2}/3 for {url}")
            raise self.retry(
                exc=e, countdown=0
            )  # Immediate retry (delay handled above)
        else:
            # All retries exhausted
            logger.error(f"❌ All 3 retry attempts exhausted for {url}")
            raise Exception(
                "Analysis failed after 3 attempts. Timeout after 60 seconds on each attempt. See logs for details."
            )

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
