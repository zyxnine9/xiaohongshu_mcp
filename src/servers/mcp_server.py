"""MCP server - 对外暴露 MCP 工具，供 Claude / Cursor 等客户端调用.

独立运行（scripts/run_mcp.py）时使用自带 lifespan 启动浏览器；
若将来挂载到 FastAPI，可改为无 lifespan，由 FastAPI lifespan 设置 platform。
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.core.browser_manager import BrowserManager
from src.core.llm_client import get_llm_client
from src.core.types import PublishContent
from src.platforms.xiaohongshu import XiaohongshuPlatform
from src.servers.state import set_platform

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_COOKIES_PATH = DEFAULT_DATA_DIR / "cookies" / "xiaohongshu.json"


@asynccontextmanager
async def _mcp_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """独立运行 MCP 时：启动浏览器并设置 platform，与工具共用同一 event loop。"""
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    browser = BrowserManager(headless=True, cookies_path=DEFAULT_COOKIES_PATH)
    platform = XiaohongshuPlatform(
        browser,
        llm=get_llm_client(),
        cookies_path=DEFAULT_COOKIES_PATH,
    )
    try:
        await browser.start()
        set_platform(platform)
        yield
    finally:
        set_platform(None)
        await browser.close()


mcp = FastMCP(
    "social-media-op",
    json_response=True,
    lifespan=_mcp_lifespan,
)


def _get_platform():
    from src.servers.state import get_platform
    return get_platform()


# --- MCP Tools (与 xiaohongshu-mcp 对齐) ---


@mcp.tool()
async def check_login_status() -> str:
    """检查小红书登录状态。无参数。"""
    platform = _get_platform()
    ok = await platform.check_login()
    return "已登录" if ok else "未登录，请先运行 scripts/login.py 完成登录"


@mcp.tool()
async def list_feeds(limit: int = 20) -> str:
    """获取小红书首页推荐列表。limit 默认 20。"""
    platform = _get_platform()
    feeds = await platform.get_feeds(limit=limit)
    lines = [f"- id: {p.id}, title: {p.title[:50] if p.title else '(无标题)'}" for p in feeds]
    return "\n".join(lines) if lines else "无数据"


@mcp.tool()
async def search_feeds(keyword: str, limit: int = 20) -> str:
    """根据关键词搜索小红书内容。"""
    platform = _get_platform()
    results = await platform.search(keyword, limit=limit)
    lines = [f"- id: {p.id}, title: {p.title[:50] if p.title else '(无标题)'}" for p in results]
    return "\n".join(lines) if lines else "无结果"


@mcp.tool()
async def get_feed_detail(feed_id: str, xsec_token: str = "") -> str:
    """获取小红书帖子详情（含互动数据与评论）。需要 feed_id，xsec_token 可从 Feed 列表或搜索结果中获取。"""
    platform = _get_platform()
    post = await platform.get_post_detail(feed_id, xsec_token)
    if not post:
        return "未找到该帖子或需要登录"
    parts = [
        f"标题: {post.title}",
        f"内容: {post.content[:500]}..." if len(post.content or "") > 500 else f"内容: {post.content}",
        f"作者: {post.author}",
        f"点赞: {post.likes}, 评论数: {post.comments_count}",
    ]
    comments = (post.raw or {}).get("comments", [])
    if comments:
        parts.append("评论: " + "; ".join([c.get("content", "")[:80] for c in comments[:10]]))
    return "\n".join(parts)


@mcp.tool()
async def publish_content(
    title: str,
    content: str,
    images: list[str],
    tags: list[str] = None,
) -> str:
    """发布图文内容到小红书。title 必填且不超过 20 字，content 正文不超过 1000 字，images 为图片 URL 或本地绝对路径列表，推荐本地路径。"""
    platform = _get_platform()
    tags = tags or []
    pub = PublishContent(title=title[:20], content=content[:1000], images=images, tags=tags)
    post_id = await platform.publish(pub)
    return f"发布成功，post_id: {post_id}" if post_id else "发布失败"


@mcp.tool()
async def post_comment_to_feed(feed_id: str, xsec_token: str, content: str) -> str:
    """在指定小红书帖子下发表评论。需要 feed_id、xsec_token 和评论内容。"""
    platform = _get_platform()
    ok = await platform.comment(feed_id, content, xsec_token)
    return "评论成功" if ok else "评论失败"
