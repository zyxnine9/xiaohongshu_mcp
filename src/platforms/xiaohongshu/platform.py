"""Xiaohongshu platform adapter - 小红书平台适配器."""
from pathlib import Path
from typing import Optional

from src.core.browser_manager import BrowserManager
from src.core.llm_client import LLMClient
from src.core.models import Comment, Post, PublishContent, UserProfile
from src.platforms.base import PlatformBase
from src.platforms.xiaohongshu import workflows
from src.platforms.xiaohongshu.workflows import LOGIN_STATUS_SELECTOR


class XiaohongshuPlatform(PlatformBase):
    """Xiaohongshu (小红书) platform with fixed workflows."""

    name = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com/explore"

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
        """Open explore page for manual login (QR or other). Saves cookies after.

        Logic follows xiaohongshu-mcp/login.go:
        1. Navigate to /explore -> triggers QR code popup if not logged in
        2. Wait 2s for page load
        3. If already logged in, save cookies and return
        4. Otherwise poll for .main-container .user .link-wrapper .channel
        """
        import asyncio

        page = await self.browser.new_page()
        try:
            # 导航到首页，未登录时会触发二维码弹窗
            await page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await asyncio.sleep(2)

            # 检查是否已经登录（与 login.go 一致：.main-container .user .link-wrapper .channel）
            if await page.query_selector(LOGIN_STATUS_SELECTOR):
                await self.browser.save_context_cookies()
                return True

            # 未登录：获取并打印二维码到终端
            qr_src, _ = await workflows.workflow_fetch_qrcode(page)
            if qr_src:
                workflows._print_qrcode_in_terminal(qr_src)
            else:
                print("请在浏览器中完成扫码登录...")

            # 等待扫码/登录完成（轮询登录成功元素，同 login.go WaitForLogin）
            success = await workflows.workflow_wait_for_login(page, timeout_sec=120)
            if success:
                await self.browser.save_context_cookies()
                return True
            return False
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
