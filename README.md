# Agentic-Web-Automator

An intelligent, LLM-driven web automation framework. Give it a natural language goal — it reasons, acts, and self-corrects until the task is done.

```
"Log into this site, search for X, and extract the first 5 results into a JSON file."
```

No hard-coded selectors. No fragile XPath. Just intent.

---

## How It Works

The agent runs a **ReAct loop** (Reason + Act) backed by a live Playwright browser:

```
┌─────────────────────────────────────────────────────┐
│                    ReAct Loop                       │
│                                                     │
│  ┌──────────┐   snapshot + element_map              │
│  │ Observer │ ──────────────────────────┐           │
│  └──────────┘                           ▼           │
│                                   ┌──────────┐      │
│  page.evaluate(inject JS)         │  Brain   │      │
│        ▲                          │ (LiteLLM)│      │
│        │                          └──────────┘      │
│  ┌──────────┐   structured Action       │           │
│  │ Browser  │ ◄─────────────────────────┘           │
│  │  (PW)   │                                        │
│  └──────────┘                                       │
│        │        observation (or ERROR)              │
│        └─────────────────────────────► history      │
└─────────────────────────────────────────────────────┘
```

1. **Observer** — injects `data-agent-id` attributes into the live DOM, then parses the HTML into a compact, token-efficient snapshot the LLM can read without overflow.
2. **Brain** — sends the goal + page snapshot + step history to the LLM (via LiteLLM), receives a structured JSON action back.
3. **Executor** — translates the action into a Playwright async API call. Catches every exception and returns it as a plain error string.
4. **Self-correction** — errors are appended to history. The LLM sees them on the next step and reasons about an alternative strategy automatically.

---

## Project Structure

```
Agentic-Web-Automator/
├── agentic_web_automator/
│   ├── __init__.py        # Public API
│   ├── models.py          # Pydantic v2 schemas
│   ├── observer.py        # DOM parser + JS injector
│   ├── browser_env.py     # Playwright async context manager
│   ├── executor.py        # Action → Playwright dispatcher
│   └── agent.py           # ReAct loop
├── main.py                # Demo entry point
├── requirements.txt
└── .env.example
```

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and add at least one API key:

```env
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

DEFAULT_MODEL=openai/gpt-4o
```

### 3. Run the demo

```bash
python main.py
```

The agent navigates to `https://example.com`, reads the page, and extracts the main heading. Output is printed to the console and saved to `output.json`.

---

## Supported Actions

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `GOTO` | Navigate to a URL | `url` |
| `CLICK` | Click an element | `element_id` |
| `TYPE` | Type into an input | `element_id`, `text` |
| `SCROLL` | Scroll the viewport | `scroll_x`, `scroll_y` |
| `WAIT` | Pause | `wait_ms` |
| `EXTRACT` | Read element or full-page text | `element_id` (optional) |
| `DONE` | Signal completion | `result` (the final answer) |

---

## Using the Agent in Your Code

```python
import asyncio
from agentic_web_automator import BrowserEnvironment, WebAgent

async def run():
    async with BrowserEnvironment(headless=True) as env:
        agent = WebAgent(model="openai/gpt-4o", max_steps=20)
        result = await agent.run(
            goal="Go to news.ycombinator.com and return the titles of the top 3 posts.",
            page=env.page,
        )
    print(result)

asyncio.run(run())
```

---

## Switching LLM Providers

LiteLLM handles provider routing. Change `DEFAULT_MODEL` in `.env` — no code changes needed:

```env
# OpenAI
DEFAULT_MODEL=openai/gpt-4o

# Anthropic
DEFAULT_MODEL=anthropic/claude-3-5-sonnet-20241022

# Google
DEFAULT_MODEL=gemini/gemini-2.0-flash

# OpenRouter (access 100+ models)
DEFAULT_MODEL=openrouter/google/gemini-2.0-flash-exp
```

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `DEFAULT_MODEL` | `openai/gpt-4o` | LiteLLM model identifier |
| `HEADLESS` | `true` | Run browser headlessly |
| `SLOW_MO` | `0` | Milliseconds between Playwright actions (useful for debugging) |
| `MAX_STEPS` | `15` | Maximum ReAct loop iterations |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG` shows LLM thoughts) |

Set `LOG_LEVEL=DEBUG` to see the agent's full reasoning at every step.

---

## How the Selector System Works

Hard-coded CSS selectors break constantly. This framework avoids them entirely:

1. Before reading the page, the agent runs a small JavaScript snippet that stamps every visible interactive element with a `data-agent-id` attribute (`btn_0`, `input_1`, `link_2`, …).
2. The Observer parses the annotated HTML and builds an `element_map`: `{"btn_0": '[data-agent-id="btn_0"]', …}`.
3. The LLM references elements by logical ID (e.g. `"element_id": "btn_0"`).
4. The Executor resolves the ID to its injected selector and calls `page.locator(selector).first`.

The IDs are re-assigned fresh on every step, so stale references are automatically caught and reported as errors for the LLM to handle.

---

## Tech Stack

- **Python 3.10+**
- **[Playwright](https://playwright.dev/python/)** — async browser automation
- **[LiteLLM](https://github.com/BerriAI/litellm)** — unified LLM API (OpenAI, Anthropic, Gemini, OpenRouter, …)
- **[Pydantic v2](https://docs.pydantic.dev/)** — structured action schemas and validation
- **[BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)** + **lxml** — DOM parsing
