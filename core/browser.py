"""
Per-worker browser runtime.

The old design created a fresh asyncio event loop per Celery task while
sharing an async browser pool across tasks — pool objects ended up bound to
closed loops, which is why acquire() regularly timed out and fell back to a
standalone browser.

New design: each worker process owns ONE persistent event loop and ONE
persistent Chromium instance, recycled after a bounded number of analyses or
age. With prefork concurrency N this is effectively an N-browser pool with
none of the cross-loop hazards.
"""

import asyncio
import logging
import time
from typing import Optional

from playwright.async_api import async_playwright, Browser, Playwright

from config import settings

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_browser_started_at: float = 0.0
_browser_use_count: int = 0

BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
]


def get_worker_loop() -> asyncio.AbstractEventLoop:
    """The one event loop this worker process runs everything on."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


async def get_browser() -> Browser:
    """
    Return this process's browser, launching or recycling as needed.
    Must be awaited on the loop from get_worker_loop().
    """
    global _playwright, _browser, _browser_started_at, _browser_use_count

    needs_recycle = (
        _browser is not None
        and (
            not _browser.is_connected()
            or _browser_use_count >= settings.BROWSER_MAX_USES
            or (time.time() - _browser_started_at) > settings.BROWSER_MAX_AGE_SECONDS
        )
    )
    if needs_recycle:
        logger.info(
            "Recycling browser (uses=%s, age=%.0fs)",
            _browser_use_count,
            time.time() - _browser_started_at,
        )
        try:
            await asyncio.wait_for(_browser.close(), timeout=settings.BROWSER_CLOSE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Browser close during recycle failed: {e}")
        _browser = None

    if _browser is None:
        if _playwright is None:
            _playwright = await async_playwright().start()
        _browser = await asyncio.wait_for(
            _playwright.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS),
            timeout=settings.BROWSER_LAUNCH_TIMEOUT,
        )
        _browser_started_at = time.time()
        _browser_use_count = 0
        logger.info("Launched worker browser")

    _browser_use_count += 1
    return _browser


async def close_browser() -> None:
    global _playwright, _browser
    if _browser is not None:
        try:
            await _browser.close()
        except Exception as e:
            logger.warning(f"Browser close failed: {e}")
        _browser = None
    if _playwright is not None:
        try:
            await _playwright.stop()
        except Exception as e:
            logger.warning(f"Playwright stop failed: {e}")
        _playwright = None


def browser_health() -> dict:
    """Snapshot for /status/detailed (works even if nothing launched yet)."""
    return {
        "launched": _browser is not None,
        "connected": _browser.is_connected() if _browser else False,
        "use_count": _browser_use_count,
        "age_seconds": round(time.time() - _browser_started_at, 1) if _browser else 0,
    }
