"""FastAPI HTTP API - 对外暴露 REST 接口."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.core.browser_manager import BrowserManager
from src.core.llm_client import get_llm_client
from src.core.models import PublishContent
from src.platforms.xiaohongshu import XiaohongshuPlatform
from src.servers.state import get_platform, set_platform

# 默认路径（可被 run 时覆盖）
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_COOKIES_PATH = DEFAULT_DATA_DIR / "cookies" / "xiaohongshu.json"


def _make_platform(headless: bool = True):
    """Create browser and platform instance."""
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    browser = BrowserManager(
        headless=headless,
        cookies_path=DEFAULT_COOKIES_PATH,
    )
    llm = get_llm_client()
    return browser, XiaohongshuPlatform(
        browser,
        llm=llm,
        cookies_path=DEFAULT_COOKIES_PATH,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage browser lifecycle: start on startup, close on shutdown."""
    browser, platform = None, None
    try:
        browser, platform = _make_platform(headless=True)
        await browser.start()
        set_platform(platform)
        yield
    finally:
        set_platform(None)
        if browser:
            await browser.close()


app = FastAPI(
    title="Social Media Operations API",
    description="HTTP API for 小红书 etc. (发布、评论、拉取 Feed 等)",
    lifespan=lifespan,
)

# --- Request/Response models ---


class PublishRequest(BaseModel):
    title: str = Field("", max_length=20, description="标题，小红书最多 20 字")
    content: str = Field("", max_length=1000, description="正文，最多 1000 字")
    images: list[str] = Field(default_factory=list, description="图片 URL 或本地路径")
    video: str = Field("", description="视频本地路径")
    tags: list[str] = Field(default_factory=list, description="标签")


class CommentRequest(BaseModel):
    post_id: str
    content: str = Field(..., max_length=500)
    xsec_token: str = ""


class PostDetailRequest(BaseModel):
    post_id: str
    xsec_token: str = ""


def _post_to_dict(p: Any) -> dict:
    """Convert Post dataclass to JSON-serializable dict."""
    return {
        "id": p.id,
        "title": getattr(p, "title", "") or "",
        "content": getattr(p, "content", "") or "",
        "author": getattr(p, "author", "") or "",
        "author_id": getattr(p, "author_id", "") or "",
        "xsec_token": getattr(p, "xsec_token", "") or "",
        "likes": getattr(p, "likes", 0) or 0,
        "comments_count": getattr(p, "comments_count", 0) or 0,
        "images": getattr(p, "images", []) or [],
    }


# --- Routes ---


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/xiaohongshu/check_login")
async def check_login():
    """检查小红书登录状态."""
    try:
        platform = get_platform()
        ok = await platform.check_login()
        return {"logged_in": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/xiaohongshu/feeds")
async def list_feeds(limit: int = 20):
    """获取小红书首页推荐列表."""
    try:
        platform = get_platform()
        feeds = await platform.get_feeds(limit=limit)
        return {"feeds": [_post_to_dict(p) for p in feeds]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/xiaohongshu/search")
async def search_feeds(keyword: str, limit: int = 20):
    """搜索小红书内容."""
    try:
        platform = get_platform()
        results = await platform.search(keyword, limit=limit)
        return {"feeds": [_post_to_dict(p) for p in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/xiaohongshu/post_detail")
async def get_post_detail(body: PostDetailRequest):
    """获取帖子详情（含评论）."""
    try:
        platform = get_platform()
        post = await platform.get_post_detail(body.post_id, body.xsec_token)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return _post_to_dict(post)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/xiaohongshu/publish")
async def publish(body: PublishRequest):
    """发布图文/视频到小红书."""
    try:
        platform = get_platform()
        content = PublishContent(
            title=body.title,
            content=body.content,
            images=body.images,
            video=body.video or "",
            tags=body.tags,
        )
        post_id = await platform.publish(content)
        if not post_id:
            raise HTTPException(status_code=500, detail="Publish failed")
        return {"post_id": post_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/xiaohongshu/comment")
async def post_comment(body: CommentRequest):
    """在帖子下发表评论."""
    try:
        platform = get_platform()
        ok = await platform.comment(body.post_id, body.content, body.xsec_token)
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
