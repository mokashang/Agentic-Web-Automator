"""
DOM Observer: converts a live Playwright page into a compact, token-efficient
snapshot the LLM can reason over, plus an element_map for the Executor.

Strategy: inject data-agent-id attributes into the live DOM via JS before
capturing HTML, so every interactive element has a stable, unambiguous selector.
"""
from __future__ import annotations

import logging
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Injected into the live DOM before page.content() is called.
# Assigns data-agent-id="<prefix>_<n>" to every visible interactive element.
_INJECT_JS = """
(function() {
    const sel = [
        'button',
        'input:not([type="hidden"])',
        'select',
        'textarea',
        'a[href]',
        'h1', 'h2', 'h3',
        'p', 'li'
    ].join(',');

    function isVisible(el) {
        const s = window.getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
    }

    const counters = {};
    document.querySelectorAll(sel).forEach(function(el) {
        if (!isVisible(el)) return;
        const tag = el.tagName.toLowerCase();
        let prefix = tag;
        if (tag === 'a') {
            prefix = 'link';
        } else if (tag === 'button') {
            prefix = 'btn';
        } else if (tag === 'input') {
            const t = (el.getAttribute('type') || 'text').toLowerCase();
            if (['submit', 'button', 'reset'].includes(t)) prefix = 'btn';
            else if (t === 'checkbox') prefix = 'checkbox';
            else if (t === 'radio') prefix = 'radio';
            else prefix = 'input';
        }
        if (!(prefix in counters)) counters[prefix] = 0;
        el.setAttribute('data-agent-id', prefix + '_' + counters[prefix]);
        counters[prefix]++;
    });
})();
"""

_INTERACTIVE = {"button", "input", "select", "textarea", "a"}
_CONTENT = {"h1", "h2", "h3", "p", "li"}


class Observer:
    # Expose JS so Agent can call page.evaluate(Observer.INJECT_JS)
    INJECT_JS = _INJECT_JS

    def __init__(self, max_chars: int = 4000) -> None:
        self.max_chars = max_chars

    def observe(self, html: str, url: str = "") -> tuple[str, dict[str, str]]:
        """Parse HTML and return (snapshot_string, element_map).

        snapshot_string: compact page description for the LLM prompt.
        element_map: maps logical IDs (e.g. "btn_0") to CSS selectors.
        """
        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style", "noscript", "svg", "head"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        element_map: dict[str, str] = {}
        lines_interactive: list[str] = []
        lines_content: list[str] = []

        for tag in soup.find_all(True):
            agent_id = tag.get("data-agent-id")
            if not agent_id:
                continue

            tag_name = tag.name.lower() if tag.name else ""
            element_map[agent_id] = f'[data-agent-id="{agent_id}"]'

            if tag_name in _INTERACTIVE:
                lines_interactive.append(self._describe_interactive(tag, tag_name, agent_id))
            elif tag_name in _CONTENT:
                text = tag.get_text(strip=True)[:200]
                if text:
                    lines_content.append(f'[{agent_id}] {tag_name.upper()}: "{text}"')

        parts = [f"=== PAGE: {title} | URL: {url} ==="]
        if lines_interactive:
            parts.append("[INTERACTIVE]")
            parts.extend(lines_interactive[:50])
        if lines_content:
            parts.append("[CONTENT]")
            parts.extend(lines_content[:20])

        snapshot = "\n".join(parts)
        if len(snapshot) > self.max_chars:
            snapshot = snapshot[: self.max_chars] + "\n...(truncated)"

        logger.debug("Observer: %d elements, %d chars", len(element_map), len(snapshot))
        return snapshot, element_map

    def _describe_interactive(self, tag: Tag, tag_name: str, agent_id: str) -> str:
        text = tag.get_text(strip=True)[:80]

        if tag_name == "a":
            href = (tag.get("href") or "")[:60]
            label = f'[{agent_id}] LINK "{text}"' if text else f"[{agent_id}] LINK"
            return f'{label} href="{href}"' if href else label

        if tag_name == "input":
            itype = (tag.get("type") or "text").lower()
            placeholder = tag.get("placeholder") or ""
            name = tag.get("name") or ""
            desc = f"[{agent_id}] INPUT[{itype}]"
            if placeholder:
                desc += f' placeholder="{placeholder}"'
            if name:
                desc += f' name="{name}"'
            return desc

        if tag_name == "button":
            return f'[{agent_id}] BUTTON "{text}"' if text else f"[{agent_id}] BUTTON"

        if tag_name == "select":
            name = tag.get("name") or ""
            options = [o.get_text(strip=True) for o in tag.find_all("option")][:5]
            desc = f"[{agent_id}] SELECT"
            if name:
                desc += f' name="{name}"'
            if options:
                desc += f" options=[{', '.join(options)}]"
            return desc

        if tag_name == "textarea":
            placeholder = tag.get("placeholder") or ""
            desc = f"[{agent_id}] TEXTAREA"
            if placeholder:
                desc += f' placeholder="{placeholder}"'
            return desc

        return f'[{agent_id}] {tag_name.upper()} "{text}"' if text else f"[{agent_id}] {tag_name.upper()}"
