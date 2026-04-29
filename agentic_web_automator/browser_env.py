"""
BrowserEnvironment: thin async context manager wrapping Playwright lifecycle.
All Playwright browser/context/page setup lives here; nothing else imports Playwright
directly except executor.py.
"""
from __future__ import annotations

import logging

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

logger = logging.getLogger(__name__)


class BrowserEnvironment:
    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: dict | None = None,
    ) -> None:
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport or {"width": 1280, "height": 800}
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserEnvironment not started — use 'async with'")
        return self._page

    async def __aenter__(self) -> "BrowserEnvironment":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self._context = await self._browser.new_context(viewport=self.viewport)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(30_000)
        logger.info("Browser started (headless=%s, slow_mo=%s)", self.headless, self.slow_mo)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser closed")
        except Exception as e:
            logger.warning("Error during browser cleanup: %s", e)
