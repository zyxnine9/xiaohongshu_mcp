"""Xiaohongshu platform adapter - 小红书平台适配器."""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.core.browser_manager import BrowserManager
from src.core.models import Comment, Post, PublishContent, UserProfile
from src.platforms.base import PlatformBase
from src.platforms.xiaohongshu.worflow import (
    feed_detail_workflow,
    feeds_workflow,
    login_workflow,
    publish_workflow,
    search_workflow,
    user_profile_workflow,
)

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

    def _feed_dict_to_post(self, item: dict[str, Any]) -> Post:
        """将小红书 __INITIAL_STATE__ 中的 feed 项转为 Post."""
        note_card = item.get("noteCard") or {}
        user = note_card.get("user") or {}
        interact = note_card.get("interactInfo") or {}
        cover = note_card.get("cover") or {}
        info_list = cover.get("infoList") or []
        images = [img.get("url") or "" for img in info_list if img.get("url")]
        author = user.get("nickname") or user.get("nickName") or ""
        author_id = user.get("userId") or ""
        liked = interact.get("likedCount") or "0"
        comments = interact.get("commentCount") or "0"
        shared = interact.get("sharedCount") or "0"
        try:
            likes = int(liked) if isinstance(liked, str) else liked
        except (TypeError, ValueError):
            likes = 0
        try:
            comments_count = int(comments) if isinstance(comments, str) else comments
        except (TypeError, ValueError):
            comments_count = 0
        try:
            shares = int(shared) if isinstance(shared, str) else shared
        except (TypeError, ValueError):
            shares = 0
        return Post(
            id=item.get("id") or "",
            title=note_card.get("displayTitle") or "",
            content="",
            author=author,
            author_id=author_id,
            xsec_token=item.get("xsecToken") or "",
            likes=likes,
            comments_count=comments_count,
            shares=shares,
            images=images,
            video_url="",
            raw=item,
        )

    async def get_feeds(self, limit: int = 20) -> list[Post]:
        """Get feed/recommended list from homepage __INITIAL_STATE__.feed.feeds."""
        page = await self.browser.new_page()
        try:
            raw_list = await feeds_workflow.get_feeds_list(page)
            return [self._feed_dict_to_post(item) for item in raw_list[:limit]]
        finally:
            await page.close()

    async def search(self, keyword: str, limit: int = 20) -> list[Post]:
        """Search content by keyword via search_workflow."""
        page = await self.browser.new_page()
        try:
            raw_list = await search_workflow.get_search_feeds_list(
                page, keyword=keyword, limit=limit
            )
            return [self._feed_dict_to_post(item) for item in raw_list]
        finally:
            await page.close()

    async def get_post_detail(
        self,
        post_id: str,
        xsec_token: str = "",
        load_all_comments: bool = False,
    ) -> Optional[Post]:
        """Get post detail via feed_detail_workflow; optionally load all comments."""
        if not xsec_token:
            return None
        page = await self.browser.new_page()
        try:
            raw = await feed_detail_workflow.get_feed_detail(
                page, post_id, xsec_token, load_all_comments=load_all_comments
            )
            if not raw:
                return None
            return self._note_detail_to_post(raw.get("note") or {}, post_id, raw)
        finally:
            await page.close()

    def _note_detail_to_post(
        self, note: dict[str, Any], post_id: str, raw_detail: Optional[dict[str, Any]] = None
    ) -> Post:
        """将 feed_detail_workflow 返回的 note 转为 Post（noteDetailMap 单条结构）."""
        user = note.get("user") or {}
        interact = note.get("interactInfo") or {}
        image_list = note.get("imageList") or []
        images = [img.get("url") or "" for img in image_list if isinstance(img, dict) and img.get("url")]
        author = user.get("nickname") or user.get("nickName") or ""
        author_id = user.get("userId") or ""
        liked = interact.get("likedCount") or "0"
        comments = interact.get("commentCount") or "0"
        shared = interact.get("sharedCount") or "0"
        try:
            likes = int(liked) if isinstance(liked, str) else liked
        except (TypeError, ValueError):
            likes = 0
        try:
            comments_count = int(comments) if isinstance(comments, str) else comments
        except (TypeError, ValueError):
            comments_count = 0
        try:
            shares = int(shared) if isinstance(shared, str) else shared
        except (TypeError, ValueError):
            shares = 0
        return Post(
            id=note.get("noteId") or post_id,
            title=note.get("title") or "",
            content=note.get("desc") or "",
            author=author,
            author_id=author_id,
            xsec_token=note.get("xsecToken") or "",
            likes=likes,
            comments_count=comments_count,
            shares=shares,
            images=images,
            video_url=note.get("video", {}).get("url") if isinstance(note.get("video"), dict) else "",
            raw=raw_detail or note,
        )

    def _user_profile_data_to_user_profile(
        self, user_id: str, data: dict[str, Any]
    ) -> UserProfile:
        """将 user_profile_workflow 返回的 basic_info + interactions 转为 UserProfile."""
        basic_info = data.get("basic_info") or {}
        interactions = data.get("interactions") or []
        nickname = basic_info.get("nickname") or ""
        bio = basic_info.get("desc") or ""
        followers = following = likes_count = 0
        for item in interactions:
            if not isinstance(item, dict):
                continue
            count_str = item.get("count") or "0"
            try:
                count = int(count_str) if isinstance(count_str, str) else count_str
            except (TypeError, ValueError):
                count = 0
            t = (item.get("type") or "").lower()
            name = (item.get("name") or "")
            if t == "fans" or name == "粉丝":
                followers = count
            elif t == "follows" or name == "关注":
                following = count
            elif t == "interaction" or "获赞" in name or "收藏" in name:
                likes_count = count
        return UserProfile(
            user_id=user_id,
            nickname=nickname,
            bio=bio,
            followers=followers,
            following=following,
            likes_count=likes_count,
        )

    async def get_user_profile(self, user_id: str, xsec_token: str = "") -> Optional[UserProfile]:
        """Get user profile via user_profile_workflow. Requires xsec_token from feed/search."""
        if not xsec_token:
            return None
        page = await self.browser.new_page()
        try:
            data = await user_profile_workflow.user_profile(page, user_id, xsec_token)
            if not data:
                return None
            return self._user_profile_data_to_user_profile(user_id, data)
        finally:
            await page.close()

    async def publish(
        self, content: PublishContent, schedule_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Publish post via creator center (init_publish_page + publish_workflow.publish).
        Returns a sentinel value on success (post_id not available from creator flow), None on failure.
        """
        page = await self.browser.new_page()
        try:
            if not await publish_workflow.init_publish_page(page):
                return None
            ok = await publish_workflow.publish(page, content, schedule_time=schedule_time)
            return "published" if ok else None
        finally:
            await page.close()

    async def comment(self, post_id: str, content: str, xsec_token: str = "") -> bool:
        """Post comment on a post. Not implemented yet."""
        return False