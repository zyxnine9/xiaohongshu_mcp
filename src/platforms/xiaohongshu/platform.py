"""Xiaohongshu platform adapter - 小红书平台适配器."""
from pathlib import Path
from typing import Optional

from src.core.browser_manager import BrowserManager
from src.core.llm_client import LLMClient
from src.core.types import Comment, Post, PublishContent, UserProfile
from src.platforms.base import PlatformBase
from src.platforms.xiaohongshu import workflows


class XiaohongshuPlatform(PlatformBase):
    """Xiaohongshu (小红书) platform with fixed workflows."""

    name = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com"

    def __init__(
        self,
        browser: BrowserManager,
        llm: Optional[LLMClient] = None,
        cookies_path: Optional[Path] = None,
    ):
        cookies_path = cookies_path or Path("data") / "cookies" / "xiaohongshu.json"
        super().__init__(browser, llm, cookies_path)
        self.browser.cookies_path = self.cookies_path

    async def login(self, headless: bool = False) -> bool:
        """Open login page for manual login. Saves cookies after."""
        import asyncio
        page = await self.browser.new_page()
        try:
            await page.goto(
                f"{self.base_url}/passport",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            # 等待用户手动登录（轮询 URL 变化）
            for _ in range(120):
                await asyncio.sleep(1)
                url = page.url
                if "passport" not in url and "login" not in url.lower():
                    break
            else:
                return False
            await self.browser.save_context_cookies()
            return True
        except Exception:
            return False
        finally:
            await page.close()

    async def check_login(self) -> bool:
        """Check if currently logged in."""
        page = await self.browser.new_page()
        try:
            return await workflows.workflow_check_login(page)
        finally:
            await page.close()

    async def get_feeds(self, limit: int = 20) -> list[Post]:
        """Get feed list (DOM-based read)."""
        page = await self.browser.new_page()
        try:
            raw = await workflows.workflow_get_feeds(page, limit=limit)
            return [self._raw_to_post(r) for r in raw]
        finally:
            await page.close()

    async def search(self, keyword: str, limit: int = 20) -> list[Post]:
        """Search by keyword (DOM-based read)."""
        page = await self.browser.new_page()
        try:
            raw = await workflows.workflow_search(page, keyword, limit=limit)
            return [self._raw_to_post(r) for r in raw]
        finally:
            await page.close()

    async def get_post_detail(self, post_id: str, xsec_token: str = "") -> Optional[Post]:
        """Get post detail including comments."""
        page = await self.browser.new_page()
        try:
            raw = await workflows.workflow_get_post_detail(
                page, post_id, xsec_token
            )
            if not raw:
                return None
            return self._raw_to_post_detail(raw)
        finally:
            await page.close()

    async def publish(self, content: PublishContent) -> Optional[str]:
        """Publish content (fixed workflow)."""
        page = await self.browser.new_page()
        try:
            return await workflows.workflow_publish_content(page, content)
        finally:
            await page.close()

    async def comment(self, post_id: str, content: str, xsec_token: str = "") -> bool:
        """Post comment (fixed workflow)."""
        page = await self.browser.new_page()
        try:
            return await workflows.workflow_post_comment(
                page, post_id, content, xsec_token
            )
        finally:
            await page.close()

    @staticmethod
    def _raw_to_post(r: dict) -> Post:
        return Post(
            id=r.get("id", ""),
            title=r.get("title", ""),
            xsec_token=r.get("xsec_token", ""),
            raw=r,
        )

    @staticmethod
    def _raw_to_post_detail(r: dict) -> Post:
        return Post(
            id=r.get("id", ""),
            title=r.get("title", ""),
            content=r.get("content", ""),
            author=r.get("author", ""),
            author_id=r.get("author_id", ""),
            likes=r.get("likes", 0),
            comments_count=r.get("comments_count", 0),
            images=r.get("images", []),
            xsec_token=r.get("xsec_token", ""),
            raw=r,
        )
