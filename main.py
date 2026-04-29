"""
Demo entry point: navigates to https://example.com and extracts the h1 heading.

Usage:
    cp .env.example .env        # add your API key
    pip install -r requirements.txt
    playwright install chromium
    python main.py
"""
import asyncio
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from agentic_web_automator.agent import WebAgent
from agentic_web_automator.browser_env import BrowserEnvironment

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    goal = (
        "Navigate to https://example.com and extract the text of the main heading (h1). "
        "Return just the heading text as the result."
    )

    headless = os.getenv("HEADLESS", "true").lower() != "false"
    slow_mo = int(os.getenv("SLOW_MO", "0"))

    async with BrowserEnvironment(headless=headless, slow_mo=slow_mo) as env:
        agent = WebAgent()
        result = await agent.run(goal=goal, page=env.page)

    print(f"\n{'=' * 50}")
    print(f"Agent Result: {result}")
    print(f"{'=' * 50}\n")

    with open("output.json", "w") as f:
        json.dump({"goal": goal, "result": result}, f, indent=2)
    print("Result saved to output.json")


if __name__ == "__main__":
    asyncio.run(main())
