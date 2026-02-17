"""Playwright browser manager for DOM read and automation."""
import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


class BrowserManager:
    """Manages browser lifecycle and provides page access."""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: Optional[Path] = None,
        cookies_path: Optional[Path] = None,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.cookies_path = cookies_path
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self) -> None:
        """Start browser and create context."""
        self._playwright = await async_playwright().start()
        launch_options = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        }
        self._browser = await self._playwright.chromium.launch(**launch_options)

        context_options = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "zh-CN",
        }
        if self.user_data_dir:
            context_options["storage_state"] = None  # Will load after
        self._context = await self._browser.new_context(**context_options)

        if self.cookies_path and self.cookies_path.exists():
            await self._context.add_cookies(
                self._load_cookies() or []
            )

    def _load_cookies(self) -> list:
        """Load cookies from file. Override for JSON format."""
        import json
        try:
            with open(self.cookies_path) as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("cookies", [])
        except Exception:
            return []

    def save_cookies(self, cookies: list) -> None:
        """Save cookies to file."""
        if not self.cookies_path:
            return
        import json
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cookies_path, "w") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)

    async def save_context_cookies(self) -> None:
        """Save current context cookies to file."""
        if self._context and self.cookies_path:
            cookies = await self._context.cookies()
            self.save_cookies(cookies)

    async def new_page(self) -> Page:
        """Create a new page (tab)."""
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    @property
    def context(self) -> BrowserContext:
        if not self._context:
            raise RuntimeError("Browser not started.")
        return self._context

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._context = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
