"""
WebAgent: the ReAct (Reason + Act) loop.

Each step:
  1. Inject data-agent-id attributes into the live DOM
  2. Observe — parse page into a compact snapshot + element_map
  3. Think — call LLM with goal + history + snapshot, get a structured Action
  4. Act — execute the Action via Executor, capture observation
  5. Repeat until DONE or max_steps

Self-correction is implicit: errors from the Executor are appended to history
and the LLM sees them on the next iteration, letting it reason about alternatives.
"""
from __future__ import annotations

import logging
import os

import litellm
from playwright.async_api import Page
from pydantic import ValidationError

from .executor import Executor
from .models import Action, ActionType, AgentStep
from .observer import Observer

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an autonomous web automation agent controlling a real browser.
Complete the user's goal by issuing one action at a time.

AVAILABLE ACTIONS:
- GOTO    Navigate to a URL.                        Required: url (must start with http/https)
- CLICK   Click an interactive element.             Required: element_id
- TYPE    Type text into an input or textarea.      Required: element_id, text
- SCROLL  Scroll the viewport.                      Fields: scroll_x (default 0), scroll_y (default 500)
- WAIT    Pause execution.                          Field: wait_ms (default 1000)
- EXTRACT Get text content from an element or page. Field: element_id (omit for full page text)
- DONE    Signal task complete.                     Field: result (the final answer string)

OUTPUT FORMAT — respond with ONLY a single valid JSON object, no markdown fences:
{
  "thought": "<your step-by-step reasoning before deciding>",
  "action_type": "<one of the actions above>",
  "url": null,
  "element_id": null,
  "text": null,
  "scroll_x": 0,
  "scroll_y": 500,
  "wait_ms": 1000,
  "result": null
}
Set fields irrelevant to your chosen action to null or their defaults.

RULES:
1. Always write your reasoning in "thought" before choosing action_type.
2. Only reference element_ids that appear in the current PAGE SNAPSHOT.
3. If an action returns ERROR, analyse why and try a different approach.
4. Never repeat the exact same failed action twice in a row.
5. Use SCROLL to reveal elements not yet visible.
6. Use EXTRACT when you need to read content before deciding.
7. Use DONE as soon as the goal is accomplished — do not continue unnecessarily.
"""


class WebAgent:
    def __init__(
        self,
        model: str | None = None,
        max_steps: int | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.getenv("DEFAULT_MODEL", "openai/gpt-4o")
        self.max_steps = max_steps or int(os.getenv("MAX_STEPS", "15"))
        self.temperature = temperature
        self._observer = Observer()
        self._executor = Executor()

    async def run(self, goal: str, page: Page) -> str:
        """Run the ReAct loop until DONE or max_steps. Returns the final result string."""
        history: list[AgentStep] = []

        for step in range(self.max_steps):
            # Inject stable selectors into the live DOM
            try:
                await page.evaluate(Observer.INJECT_JS)
            except Exception as e:
                logger.debug("ID injection skipped (step %d): %s", step + 1, e)

            url = page.url
            html = await page.content()
            snapshot, element_map = self._observer.observe(html, url)

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": self._build_prompt(goal, snapshot, history, step)},
            ]

            logger.debug("[Step %d] Snapshot tail:\n%s", step + 1, snapshot[-400:])

            # LLM call
            try:
                response = await litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                logger.debug("[Step %d] LLM raw: %s", step + 1, raw[:400])
            except Exception as e:
                logger.error("LLM call failed at step %d: %s", step + 1, e)
                raise

            # Parse structured action
            try:
                action = Action.model_validate_json(raw)
            except (ValidationError, ValueError) as e:
                logger.warning("[Step %d] Parse failed: %s", step + 1, e)
                # Feed parse failure back into history for self-correction
                history.append(
                    AgentStep(
                        step_number=step + 1,
                        thought="(parse failed)",
                        action=Action(thought="(parse failed)", action_type=ActionType.WAIT),
                        observation=f"ERROR: LLM output failed validation: {e}",
                    )
                )
                continue

            logger.debug("[Step %d] THOUGHT: %s", step + 1, action.thought)
            logger.info("[Step %d] ACTION: %s", step + 1, action.action_type.value)

            if action.action_type == ActionType.DONE:
                logger.info("Task complete. Result: %s", action.result)
                return action.result or ""

            observation = await self._executor.execute(page, action, element_map)
            history.append(
                AgentStep(
                    step_number=step + 1,
                    thought=action.thought,
                    action=action,
                    observation=observation,
                )
            )

            if observation.startswith("ERROR"):
                logger.warning(
                    "[Step %d] Self-correction triggered: %s", step + 1, observation[:120]
                )

        logger.warning("Max steps (%d) reached without DONE", self.max_steps)
        return "Task did not complete within the maximum number of steps."

    def _build_prompt(
        self,
        goal: str,
        snapshot: str,
        history: list[AgentStep],
        step: int,
    ) -> str:
        lines = [f"GOAL: {goal}", ""]

        if history:
            lines.append("STEP HISTORY (last 5):")
            for s in history[-5:]:
                action_summary = self._fmt_action(s.action)
                obs = s.observation[:200].replace("\n", " ")
                lines.append(
                    f"  Step {s.step_number}: "
                    f'Thought: "{s.thought[:100]}" | '
                    f"Action: {action_summary} | "
                    f"Observation: {obs}"
                )
            lines.append("")

        lines.append(f"CURRENT PAGE SNAPSHOT (step {step + 1} of {self.max_steps}):")
        lines.append(snapshot)
        lines.append("")
        lines.append("Output your next JSON action:")

        return "\n".join(lines)

    @staticmethod
    def _fmt_action(action: Action) -> str:
        at = action.action_type
        if at == ActionType.GOTO:
            return f"GOTO url={action.url}"
        if at == ActionType.CLICK:
            return f"CLICK element_id={action.element_id}"
        if at == ActionType.TYPE:
            return f"TYPE element_id={action.element_id} text='{action.text}'"
        if at == ActionType.EXTRACT:
            return f"EXTRACT element_id={action.element_id or 'page'}"
        if at == ActionType.SCROLL:
            return f"SCROLL ({action.scroll_x}, {action.scroll_y})"
        return at.value
