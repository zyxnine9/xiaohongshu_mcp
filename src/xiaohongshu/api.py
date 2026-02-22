"""小红书功能 API - 基于 workflow 的纯函数接口，无面向对象封装."""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.core.browser_manager import BrowserManager
from src.core.models import Post, PublishContent, UserProfile
from src.xiaohongshu.worflow import (
    feed_comments,
    feed_detail,
    feeds,
    login,
    memtions,
    publish,
    search,
    user_profile,
)

logger = logging.getLogger(__name__)


def _feed_dict_to_post(item: dict[str, Any]) -> Post:
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
        raw=item,
    )


def _note_detail_to_post(
    note: dict[str, Any], post_id: str, raw_detail: Optional[dict[str, Any]] = None
) -> Post:
    """将 feed_detail 返回的 note 转为 Post."""
    user = note.get("user") or {}
    interact = note.get("interactInfo") or {}
    image_list = note.get("imageList") or []
    images = [
        img.get("url")
        for img in image_list
        if isinstance(img, dict) and img.get("url")
    ]
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
        raw=raw_detail or note,
    )


def _user_profile_data_to_user_profile(user_id: str, data: dict[str, Any]) -> UserProfile:
    """将 user_profile 返回的 basic_info + interactions 转为 UserProfile."""
    basic_info = data.get("basic_info") or data.get("basicInfo") or {}
    interactions = data.get("interactions") or []
    nickname = basic_info.get("nickname") or basic_info.get("nickName") or ""
    bio = basic_info.get("desc") or basic_info.get("description") or ""
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
        name = item.get("name") or ""
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


async def login_xiaohongshu(
    browser: BrowserManager,
    headless: bool = False,
    cookies_path: Optional[Path] = None,
) -> bool:
    """执行登录（二维码）。成功返回 True."""
    page = await browser.new_page()
    try:
        if await login.check_login(page):
            return True
        await asyncio.sleep(2)
        qr_src, already = await login.fetch_qrcode(page)
        if already:
            return True
        if not qr_src:
            return False
        login.print_qrcode_in_terminal(qr_src)
        ok = await login.wait_for_login(page, timeout_sec=120, poll_interval_sec=0.5)
        if ok:
            await browser.save_context_cookies()
        return ok
    finally:
        await page.close()


async def check_login(browser: BrowserManager) -> bool:
    """检查当前是否已登录."""
    page = await browser.new_page()
    try:
        return await login.check_login(page)
    finally:
        await page.close()


async def get_feeds(browser: BrowserManager, limit: int = 20) -> list[Post]:
    """获取首页推荐 Feed 列表."""
    page = await browser.new_page()
    try:
        raw_list = await feeds.get_feeds_list(page)
        return [_feed_dict_to_post(item) for item in raw_list[:limit]]
    finally:
        await page.close()


async def search_feeds(
    browser: BrowserManager, keyword: str, limit: int = 20
) -> list[Post]:
    """按关键词搜索内容."""
    page = await browser.new_page()
    try:
        raw_list = await search.get_search_feeds_list(page, keyword=keyword, limit=limit)
        return [_feed_dict_to_post(item) for item in raw_list]
    finally:
        await page.close()


async def get_mentions(
    browser: BrowserManager, limit: int = 20
) -> list[dict[str, Any]]:
    """获取 @人/提及 消息列表."""
    page = await browser.new_page()
    try:
        return await memtions.get_mention_list(page, limit=limit)
    finally:
        await page.close()


async def get_post_detail(
    browser: BrowserManager,
    post_id: str,
    xsec_token: str,
    load_all_comments: bool = False,
) -> Optional[Post]:
    """获取帖子详情，可选加载全部评论."""
    if not xsec_token:
        return None
    page = await browser.new_page()
    try:
        raw = await feed_detail.get_feed_detail(
            page, post_id, xsec_token, load_all_comments=load_all_comments
        )
        if not raw:
            return None
        return _note_detail_to_post(raw.get("note") or {}, post_id, raw)
    finally:
        await page.close()


async def get_user_profile(
    browser: BrowserManager, user_id: str, xsec_token: str
) -> Optional[UserProfile]:
    """获取用户资料。需要 xsec_token（从 feed/搜索结果获取）。"""
    if not xsec_token:
        return None
    page = await browser.new_page()
    try:
        data = await user_profile.user_profile(page, user_id, xsec_token)
        if not data:
            return None
        return _user_profile_data_to_user_profile(user_id, data)
    finally:
        await page.close()


async def publish_content(
    browser: BrowserManager,
    content: PublishContent,
    schedule_time: Optional[datetime] = None,
) -> Optional[str]:
    """发布图文笔记。成功返回非 None（当前实现返回空字符串），失败返回 None。"""
    page = await browser.new_page()
    try:
        await publish.publish_image_from_content(
            page,
            title=content.title,
            content=content.content,
            images=content.images,
            tags=content.tags,
            schedule_time=schedule_time,
        )
        return "ok"
    except (ValueError, TimeoutError, RuntimeError) as e:
        logger.warning("发布失败: %s", e)
        return None
    finally:
        await page.close()


async def post_comment(
    browser: BrowserManager,
    post_id: str,
    content: str,
    xsec_token: str,
) -> bool:
    """在帖子下发表评论."""
    if not xsec_token:
        return False
    page = await browser.new_page()
    try:
        return await feed_comments.post_comment(page, post_id, xsec_token, content)
    finally:
        await page.close()


async def reply_comment(
    browser: BrowserManager,
    post_id: str,
    comment_id: str,
    content: str,
    xsec_token: str,
) -> bool:
    """回复指定评论."""
    if not xsec_token:
        return False
    page = await browser.new_page()
    try:
        return await feed_comments.reply_to_comment(
            page, post_id, xsec_token, content, comment_id=comment_id
        )
    finally:
        await page.close()
