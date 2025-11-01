"""
Browser pool manager for CRO Analyzer
Manages a pool of pre-launched Playwright browser instances for efficient reuse
"""

import asyncio
import os
from typing import Optional, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BrowserPool:
    """
    Manages a pool of Playwright browser instances with automatic health checks and recycling.
    """

    def __init__(
        self,
        pool_size: int = int(os.getenv("BROWSER_POOL_SIZE", "5")),
        max_pages_per_browser: int = int(os.getenv("BROWSER_MAX_PAGES", "10")),
        browser_timeout: int = int(os.getenv("BROWSER_TIMEOUT", "300")),
    ):
        """
        Initialize browser pool.

        Args:
            pool_size: Number of browser instances to maintain
            max_pages_per_browser: Max pages before recycling a browser
            browser_timeout: Max seconds a browser can live before recycling
        """
        self.pool_size = pool_size
        self.max_pages_per_browser = max_pages_per_browser
        self.browser_timeout = browser_timeout

        self.playwright = None
        self.browsers: List[dict] = []
        self.semaphore = asyncio.Semaphore(pool_size)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the browser pool with warm instances"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                logger.info(f"🚀 Initializing browser pool with {self.pool_size} instances...")
                self.playwright = await async_playwright().start()

                # Pre-launch all browsers
                for i in range(self.pool_size):
                    browser = await self._create_browser()
                    self.browsers.append({
                        "browser": browser,
                        "created_at": datetime.now(),
                        "page_count": 0,
                        "in_use": False,
                    })
                    logger.info(f"✅ Browser {i+1}/{self.pool_size} launched")

                self._initialized = True
                logger.info(f"✅ Browser pool initialized with {len(self.browsers)} browsers")

            except Exception as e:
                logger.error(f"❌ Failed to initialize browser pool: {str(e)}")
                await self.cleanup()
                raise

    async def _create_browser(self) -> Browser:
        """Create a new browser instance with optimal settings"""
        return await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",  # Prevents memory issues in Docker
                "--no-sandbox",  # Required in some containerized environments
                "--disable-setuid-sandbox",
                "--disable-gpu",
            ],
        )

    async def acquire(self) -> tuple[Browser, BrowserContext, Page]:
        """
        Acquire a browser instance from the pool.

        Returns:
            Tuple of (browser, context, page)
        """
        # Wait for available slot
        await self.semaphore.acquire()

        async with self._lock:
            # Find available browser or create/recycle one
            browser_info = None

            for info in self.browsers:
                if not info["in_use"]:
                    # Check if browser needs recycling
                    age = datetime.now() - info["created_at"]
                    if (
                        age.total_seconds() > self.browser_timeout
                        or info["page_count"] >= self.max_pages_per_browser
                    ):
                        logger.info(
                            f"♻️  Recycling browser (age: {age.total_seconds()}s, pages: {info['page_count']})"
                        )
                        try:
                            await info["browser"].close()
                        except:
                            pass
                        info["browser"] = await self._create_browser()
                        info["created_at"] = datetime.now()
                        info["page_count"] = 0

                    browser_info = info
                    break

            if not browser_info:
                # All browsers in use, this should not happen due to semaphore
                # but we'll create a temporary one as fallback
                logger.warning("⚠️  All browsers in use, creating temporary browser")
                temp_browser = await self._create_browser()
                browser_info = {
                    "browser": temp_browser,
                    "created_at": datetime.now(),
                    "page_count": 0,
                    "in_use": True,
                }

            # Mark as in use
            browser_info["in_use"] = True
            browser_info["page_count"] += 1

            # Create context and page
            try:
                browser = browser_info["browser"]
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = await context.new_page()

                logger.info(
                    f"✅ Browser acquired (age: {(datetime.now() - browser_info['created_at']).total_seconds():.1f}s, "
                    f"page count: {browser_info['page_count']})"
                )

                return browser, context, page

            except Exception as e:
                logger.error(f"❌ Failed to create browser context/page: {str(e)}")
                browser_info["in_use"] = False
                self.semaphore.release()
                raise

    async def release(self, browser: Browser, context: BrowserContext, page: Page):
        """
        Release a browser instance back to the pool.

        Args:
            browser: Browser instance
            context: Browser context
            page: Page instance
        """
        try:
            # Close page and context (but keep browser alive)
            await page.close()
            await context.close()
            logger.info("✅ Browser released back to pool")

        except Exception as e:
            logger.error(f"⚠️  Error releasing browser: {str(e)}")

        finally:
            # Mark browser as available
            async with self._lock:
                for info in self.browsers:
                    if info["browser"] == browser:
                        info["in_use"] = False
                        break

            # Release semaphore
            self.semaphore.release()

    async def health_check(self) -> dict:
        """
        Check health of all browsers in the pool.

        Returns:
            Dictionary with health status
        """
        async with self._lock:
            total = len(self.browsers)
            in_use = sum(1 for b in self.browsers if b["in_use"])
            available = total - in_use

            ages = [
                (datetime.now() - b["created_at"]).total_seconds()
                for b in self.browsers
            ]
            avg_age = sum(ages) / len(ages) if ages else 0

            page_counts = [b["page_count"] for b in self.browsers]
            avg_pages = sum(page_counts) / len(page_counts) if page_counts else 0

            return {
                "total_browsers": total,
                "in_use": in_use,
                "available": available,
                "average_age_seconds": round(avg_age, 2),
                "average_page_count": round(avg_pages, 2),
                "status": "healthy" if available > 0 else "saturated",
            }

    async def cleanup(self):
        """Close all browsers and cleanup resources"""
        logger.info("🧹 Cleaning up browser pool...")

        async with self._lock:
            for info in self.browsers:
                try:
                    await info["browser"].close()
                except Exception as e:
                    logger.warning(f"⚠️  Error closing browser: {str(e)}")

            self.browsers.clear()

            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception as e:
                    logger.warning(f"⚠️  Error stopping Playwright: {str(e)}")

            self._initialized = False
            logger.info("✅ Browser pool cleaned up")


# Global browser pool instance
_browser_pool: Optional[BrowserPool] = None


async def get_browser_pool(pool_size: int = int(os.getenv("BROWSER_POOL_SIZE", "5"))) -> BrowserPool:
    """
    Get or create the global browser pool instance.

    Args:
        pool_size: Number of browsers to maintain in pool

    Returns:
        BrowserPool instance
    """
    global _browser_pool

    if _browser_pool is None:
        _browser_pool = BrowserPool(pool_size=pool_size)
        await _browser_pool.initialize()

    return _browser_pool


async def close_browser_pool():
    """Close the global browser pool"""
    global _browser_pool

    if _browser_pool is not None:
        await _browser_pool.cleanup()
        _browser_pool = None
