"""Xiaohongshu platform adapter - 小红书平台适配器."""
import asyncio
from pathlib import Path
from typing import Optional

from src.core.browser_manager import BrowserManager
from src.core.models import Comment, Post, PublishContent, UserProfile
from src.platforms.base import PlatformBase
from src.platforms.xiaohongshu.worflow import login_workflow

class XiaohongshuPlatform(PlatformBase):
    """Xiaohongshu (小红书) platform with fixed workflows."""

    name = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com/explore"


    async def login(self, headless: bool = False) -> bool:
        """Perform login via QR code. Returns True if successful."""
        page = await self.browser.new_page()
        try:
            # 1. 检查是否已登录（内部会 navigate 到 explore）
            if await login_workflow.check_login(page):
                return True
            # 2. 等待登录弹窗/二维码出现（与 Go 一致：约 2 秒）
            await asyncio.sleep(2)
            qr_src, already = await login_workflow.fetch_qrcode(page)
            if already:
                return True
            if not qr_src:
                return False
            # 3. 在终端打印二维码（可选）
            login_workflow.print_qrcode_in_terminal(qr_src)
            # 4. 轮询等待用户扫码登录（与 Go WaitForLogin 一致：500ms 轮询）
            ok = await login_workflow.wait_for_login(
                page, timeout_sec=120, poll_interval_sec=0.5
            )
            if ok:
                await self.browser.save_context_cookies()
            return ok
        finally:
            await page.close()

    async def check_login(self) -> bool:
        """Check if currently logged in."""
        page = await self.browser.new_page()
        try:
            return await login_workflow.check_login(page)
        finally:
            await page.close()