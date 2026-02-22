"""Shared state for HTTP and MCP servers (browser instance)."""
from typing import Optional

from src.core.browser_manager import BrowserManager

# 全局 browser 实例，由 server lifespan 设置
_browser: Optional[BrowserManager] = None


def get_browser() -> BrowserManager:
    if _browser is None:
        raise RuntimeError("Browser not initialized. Start the server first.")
    return _browser


def set_browser(browser: Optional[BrowserManager]) -> None:
    global _browser
    _browser = browser
