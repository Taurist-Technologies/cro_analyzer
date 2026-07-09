"""
Celery task for background PDP analysis.

Kept intentionally thin: URL safety + cache + timeout/retry policy live here;
all analysis logic lives in analyzer/pdp/.
"""

import asyncio
import logging
import time

from celery import Task

from config import settings
from core.celery import celery_app
from core.cache import get_redis_client
from core.browser import get_worker_loop, get_browser
from analyzer.pdp.analysis import run_pdp_analysis
from utils.net import normalize_url, validate_public_url, UnsafeURLError

logger = logging.getLogger(__name__)

# Screenshots are stored out-of-band so poll/result payloads stay small
SCREENSHOT_TTL = 3600  # 1 hour


class AnalysisTimeoutError(Exception):
    """Analysis exceeded its per-attempt time budget."""


class CallbackTask(Task):
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} completed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="tasks.analyze_website",
    max_retries=1,
    time_limit=settings.TASK_TIME_LIMIT,
    soft_time_limit=settings.TASK_SOFT_TIME_LIMIT,
)
def analyze_website(self, url: str, include_screenshots: bool = False) -> dict:
    """
    Analyze a product detail page.

    Policy: one attempt of ANALYSIS_TIMEOUT seconds, one retry on timeout.
    Results cache for CACHE_TTL keyed by normalized URL; screenshots are
    stored separately under the task id for 1 hour.
    """
    task_id = self.request.id
    retry_count = self.request.retries

    normalized = normalize_url(url)
    try:
        validate_public_url(normalized)
    except UnsafeURLError as e:
        raise Exception(f"URL rejected: {e}")

    def progress(percent: int, status: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"percent": percent, "status": status, "url": normalized},
        )

    redis_client = _redis_or_none()

    if retry_count == 0 and redis_client:
        cached = redis_client.get_cached_analysis(normalized)
        if cached:
            logger.info(f"Cache hit for {normalized}")
            return cached

    progress(5, "Warming up the analysis browser...")

    loop = get_worker_loop()
    try:
        result = loop.run_until_complete(
            _run_with_timeout(normalized, include_screenshots, progress)
        )
    except AnalysisTimeoutError as e:
        if retry_count < 1:
            logger.warning(f"Timeout for {normalized}, retrying once")
            raise self.retry(exc=e, countdown=2)
        raise Exception(
            f"Analysis timed out after {settings.ANALYSIS_TIMEOUT}s on both attempts. "
            "The site may be extremely slow or blocking automated browsers."
        )

    # Stash screenshots under the task id, keep the result payload lean
    screenshots = result.pop("_screenshots", None)
    if redis_client and screenshots:
        redis_client.set(f"screens:{task_id}", screenshots, ttl=SCREENSHOT_TTL)
        result["screenshots_url"] = f"/analyze/screenshots/{task_id}"

    if redis_client and result.get("status") == "success":
        redis_client.cache_analysis(normalized, result, ttl=settings.CACHE_TTL)

    return result


async def _run_with_timeout(url: str, include_screenshots: bool, progress) -> dict:
    browser = await get_browser()
    try:
        return await asyncio.wait_for(
            run_pdp_analysis(browser, url, include_screenshots, progress=progress),
            timeout=settings.ANALYSIS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise AnalysisTimeoutError(f"Analysis exceeded {settings.ANALYSIS_TIMEOUT}s")


def _redis_or_none():
    try:
        return get_redis_client()
    except Exception as e:
        logger.warning(f"Redis unavailable, running uncached: {e}")
        return None


@celery_app.task(name="tasks.cleanup_old_results")
def cleanup_old_results():
    """Periodic cache cleanup (wire into beat_schedule if desired)."""
    try:
        redis_client = get_redis_client()
        deleted = redis_client.clear_cache("cache:analysis:*")
        logger.info(f"Cleaned {deleted} cached results")
        return {"deleted_count": deleted}
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise
