"""
Executor: translates structured Action objects into Playwright async API calls.

All exceptions are caught and returned as "ERROR: ..." strings so the Agent's
self-correction loop can feed them back to the LLM without crashing.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

from .models import Action, ActionType

logger = logging.getLogger(__name__)


class Executor:
    async def execute(
        self, page: Page, action: Action, element_map: dict[str, str]
    ) -> str:
        """Execute one action. Returns an observation string (success or ERROR)."""
        try:
            return await self._dispatch(page, action, element_map)
        except Exception as e:
            msg = f"ERROR: {type(e).__name__}: {e}"
            logger.error("Action %s failed: %s", action.action_type.value, msg)
            return msg

    async def _dispatch(
        self, page: Page, action: Action, element_map: dict[str, str]
    ) -> str:
        at = action.action_type

        if at == ActionType.GOTO:
            await page.goto(action.url, wait_until="domcontentloaded")
            logger.info("GOTO %s", action.url)
            return f"Navigated to {action.url}"

        if at == ActionType.CLICK:
            selector = self._resolve(action.element_id, element_map)
            await page.locator(selector).first.click()
            logger.info("CLICK %s (%s)", action.element_id, selector)
            return f"Clicked {action.element_id}"

        if at == ActionType.TYPE:
            selector = self._resolve(action.element_id, element_map)
            await page.locator(selector).first.fill(action.text)
            logger.info("TYPE '%s' into %s", action.text, action.element_id)
            return f"Typed '{action.text}' into {action.element_id}"

        if at == ActionType.SCROLL:
            await page.evaluate(
                f"window.scrollBy({action.scroll_x}, {action.scroll_y})"
            )
            logger.info("SCROLL (%s, %s)", action.scroll_x, action.scroll_y)
            return f"Scrolled by ({action.scroll_x}, {action.scroll_y})"

        if at == ActionType.WAIT:
            await page.wait_for_timeout(action.wait_ms)
            logger.info("WAIT %sms", action.wait_ms)
            return f"Waited {action.wait_ms}ms"

        if at == ActionType.EXTRACT:
            if action.element_id:
                selector = self._resolve(action.element_id, element_map)
                text = await page.locator(selector).first.inner_text()
                logger.info("EXTRACT %s -> %d chars", action.element_id, len(text))
                return f"Extracted from {action.element_id}: {text}"
            else:
                title = await page.title()
                body = await page.evaluate("document.body.innerText")
                result = f"Title: {title}\n\n{body[:2000]}"
                logger.info("EXTRACT page (%d chars)", len(result))
                return result

        if at == ActionType.DONE:
            return "__DONE__"

        return f"ERROR: Unknown action type {at}"

    def _resolve(self, element_id: str | None, element_map: dict[str, str]) -> str:
        if not element_id:
            raise ValueError("element_id is required but was None or empty")
        selector = element_map.get(element_id)
        if selector is None:
            available = list(element_map.keys())[:15]
            raise ValueError(
                f"element_id '{element_id}' not found in element_map. "
                f"Available IDs: {available}"
            )
        return selector
