"""Lightweight agentic browser helper using Playwright (optional).

This module is optional. To enable it:
  1) pip install playwright
  2) playwright install chromium

Usage pattern (via PluginRuntime):
  payload = {"op": "navigate"|"click"|"fill"|"extract"|"screenshot",
             "url": str,
             "selector": str,
             "text": str,
             "attr": str}
"""
from __future__ import annotations

import contextlib
from typing import Any, Optional


class AgentBrowserError(RuntimeError):
    pass


class AgentBrowser:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure(self) -> None:
        if self._page:
            return
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise AgentBrowserError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self._page:
                self._page.close()
        with contextlib.suppress(Exception):
            if self._browser:
                self._browser.close()
        with contextlib.suppress(Exception):
            if self._playwright:
                self._playwright.stop()
        self._page = self._browser = self._playwright = None

    def run(self, op: str, **kwargs: Any) -> Any:
        self._ensure()
        assert self._page is not None
        page = self._page
        op = (op or "").strip().lower()
        if op == "navigate":
            url = str(kwargs.get("url", ""))
            if not url:
                raise AgentBrowserError("url is required for navigate")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"url": page.url}
        if op == "click":
            selector = str(kwargs.get("selector", ""))
            if not selector:
                raise AgentBrowserError("selector is required for click")
            page.click(selector, timeout=15000)
            return {"status": "ok", "url": page.url}
        if op == "fill":
            selector = str(kwargs.get("selector", ""))
            text = str(kwargs.get("text", ""))
            if not selector:
                raise AgentBrowserError("selector is required for fill")
            page.fill(selector, text, timeout=15000)
            return {"status": "ok"}
        if op == "extract":
            selector = str(kwargs.get("selector", ""))
            attr = kwargs.get("attr")
            if not selector:
                raise AgentBrowserError("selector is required for extract")
            if attr:
                val = page.get_attribute(selector, str(attr), timeout=15000)
            else:
                val = page.text_content(selector, timeout=15000)
            return {"value": val}
        if op == "screenshot":
            path = str(kwargs.get("path", "page.png"))
            page.screenshot(path=path, full_page=True)
            return {"path": path}
        raise AgentBrowserError(f"Unknown op: {op}")


# Singleton helper (lazily created)
_INSTANCE: Optional[AgentBrowser] = None


def get_browser() -> AgentBrowser:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AgentBrowser()
    return _INSTANCE
