"""MCP server - 对外暴露 MCP 工具，供 Claude / Cursor 等客户端调用.

独立运行（scripts/run_mcp.py）时使用自带 lifespan 启动浏览器。
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from src.core.browser_manager import BrowserManager
from src.core.models import PublishContent
from src.servers.state import get_browser, set_browser
from src.xiaohongshu import (
    check_login,
    get_feeds,
    get_mentions,
    get_post_detail,
    post_comment,
    publish_content,
    reply_comment as xhs_reply_comment,
    search_feeds as xhs_search_feeds,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_COOKIES_PATH = DEFAULT_DATA_DIR / "cookies" / "xiaohongshu.json"


@asynccontextmanager
async def _mcp_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """独立运行 MCP 时：启动浏览器，与工具共用同一 event loop。"""
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    browser = BrowserManager(headless=True, cookies_path=DEFAULT_COOKIES_PATH)
    try:
        await browser.start()
        set_browser(browser)
        yield
    finally:
        set_browser(None)
        await browser.close()


mcp = FastMCP(
    "social-media-op",
    json_response=True,
    lifespan=_mcp_lifespan,
)


def _get_browser() -> BrowserManager:
    return get_browser()


# --- MCP Tools (与 xiaohongshu-mcp 对齐) ---


@mcp.tool()
async def check_login_status() -> str:
    """检查小红书登录状态。无参数。"""
    browser = _get_browser()
    ok = await check_login(browser)
    return "已登录" if ok else "未登录，请先运行 scripts/login.py 完成登录"


@mcp.tool()
async def list_feeds(limit: int = 20) -> str:
    """获取小红书首页推荐列表。limit 默认 20。"""
    browser = _get_browser()
    feeds_list = await get_feeds(browser, limit=limit)
    lines = [f"- id: {p.id}, title: {p.title[:50] if p.title else '(无标题)'}" for p in feeds_list]
    return "\n".join(lines) if lines else "无数据"


@mcp.tool()
async def list_mentions(limit: int = 20) -> str:
    """获取小红书 @人/提及 消息列表。limit 默认 20。"""
    browser = _get_browser()
    mentions = await get_mentions(browser, limit=limit)
    if not mentions:
        return "无提及消息"
    lines = []
    for i, m in enumerate(mentions, 1):
        msg_id = m.get("id") or m.get("msgId") or m.get("messageId") or "(无id)"
        msg_type = m.get("msgType") or m.get("type") or ""
        content = (m.get("content") or m.get("msg") or "")[:80]
        from_user = (m.get("fromUser") or {}).get("nickname") if isinstance(m.get("fromUser"), dict) else ""
        note_id = m.get("noteId") or m.get("targetNoteId") or ""
        line = f"- {i}. id: {msg_id}, type: {msg_type}"
        if from_user:
            line += f", 来自: {from_user}"
        if note_id:
            line += f", 笔记id: {note_id}"
        if content:
            line += f", 内容: {content}"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
async def search_feeds(keyword: str, limit: int = 20) -> str:
    """根据关键词搜索小红书内容。"""
    browser = _get_browser()
    results = await xhs_search_feeds(browser, keyword, limit=limit)
    lines = [f"- id: {p.id}, title: {p.title[:50] if p.title else '(无标题)'}" for p in results]
    return "\n".join(lines) if results else "无结果"


@mcp.tool()
async def get_feed_detail(feed_id: str, xsec_token: str = "") -> str:
    """获取小红书帖子详情（含互动数据与评论）。需要 feed_id，xsec_token 可从 Feed 列表或搜索结果中获取。"""
    browser = _get_browser()
    post = await get_post_detail(browser, feed_id, xsec_token)
    if not post:
        return "未找到该帖子或需要登录"
    parts = [
        f"标题: {post.title}",
        f"内容: {post.content[:500]}..." if len(post.content or "") > 500 else f"内容: {post.content}",
        f"作者: {post.author}",
        f"点赞: {post.likes}, 评论数: {post.comments_count}",
    ]
    raw = post.raw if hasattr(post, "raw") else None
    if isinstance(raw, dict):
        comments = raw.get("comments", {})
        if isinstance(comments, dict):
            comment_list = list(comments.values()) if comments else []
        else:
            comment_list = comments if isinstance(comments, list) else []
        if comment_list:
            contents = []
            for c in comment_list[:10]:
                if isinstance(c, dict) and "content" in c:
                    contents.append(str(c.get("content", ""))[:80])
                elif hasattr(c, "content"):
                    contents.append(str(getattr(c, "content", ""))[:80])
            if contents:
                parts.append("评论: " + "; ".join(contents))
    return "\n".join(parts)


@mcp.tool()
async def publish_content_tool(
    title: str,
    content: str,
    images: list[str],
    tags: list[str] = None,
) -> str:
    """发布图文内容到小红书。title 必填且不超过 20 字，content 正文不超过 1000 字，images 为图片 URL 或本地绝对路径列表，推荐本地路径。"""
    browser = _get_browser()
    tags = tags or []
    pub = PublishContent(title=title[:20], content=content[:1000], images=images, tags=tags)
    result = await publish_content(browser, pub)
    return f"发布成功" if result else "发布失败"


@mcp.tool()
async def post_comment_to_feed(feed_id: str, xsec_token: str, content: str) -> str:
    """在指定小红书帖子下发表评论。需要 feed_id、xsec_token 和评论内容。"""
    browser = _get_browser()
    ok = await post_comment(browser, feed_id, content, xsec_token)
    return "评论成功" if ok else "评论失败"


@mcp.tool()
async def reply_comment(feed_id: str, comment_id: str, xsec_token: str, content: str) -> str:
    """回复指定评论。需要 feed_id、comment_id（目标评论 id）、xsec_token 和回复内容。comment_id 可从 get_feed_detail 返回的评论中获取。"""
    browser = _get_browser()
    ok = await xhs_reply_comment(browser, feed_id, comment_id, content, xsec_token)
    return "回复成功" if ok else "回复失败"
