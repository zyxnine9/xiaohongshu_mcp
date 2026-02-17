"""Fixed workflows for Xiaohongshu operations (inspired by xiaohongshu-mcp).

These workflows use deterministic Playwright steps to avoid anti-bot detection.
Key: human-like delays, stable selectors, no rapid-fire actions.
"""
import asyncio
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from src.core.types import PublishContent

# Human-like delay range (seconds)
MIN_DELAY = 0.3
MAX_DELAY = 0.8


def _random_delay() -> float:
    return random.uniform(MIN_DELAY, MAX_DELAY)


async def _human_delay():
    await asyncio.sleep(_random_delay())


async def workflow_check_login(page: Page) -> bool:
    """Check if user is logged in by looking for login indicators."""
    base = "https://www.xiaohongshu.com"
    try:
        await page.goto(base, wait_until="domcontentloaded", timeout=15000)
        await _human_delay()

        # 未登录会跳转到登录页或显示登录按钮
        url = page.url
        if "login" in url.lower() or "passport" in url.lower():
            return False

        # 尝试找到用户相关元素（登录后才有）
        user_elem = await page.query_selector(
            "text=我的|text=消息|text=发现"
        )
        return user_elem is not None
    except Exception:
        return False


async def workflow_get_feeds(page: Page, limit: int = 20) -> list[dict]:
    """Get feed list by reading DOM. Returns list of post info dicts."""
    try:
        await page.goto(
            "https://www.xiaohongshu.com/explore",
            wait_until="networkidle",
            timeout=20000,
        )
        await asyncio.sleep(1.5)

        # 小红书 Feed 在 section 或带 note 的容器内
        items = await page.query_selector_all(
            "section[class*='note'], [class*='note-item'], a[href*='/explore/']"
        )
        feeds = []
        seen_ids = set()

        for i, item in enumerate(items[:limit * 2]):  # 多取一些，过滤后取 limit
            if len(feeds) >= limit:
                break
            try:
                link = await item.get_attribute("href") or await (
                    await item.query_selector("a[href*='/explore/']")
                )?.get_attribute("href")
                if not link or "/explore/" not in link:
                    continue

                # 解析 post_id，格式通常为 /explore/xxxxx 或 ?noteId=xxx
                post_id = ""
                if "/explore/" in link:
                    parts = link.split("/explore/")[-1].split("?")[0]
                    post_id = parts.strip("/") if parts else ""

                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                # 尝试获取 xsec_token（小红书 API 需要）
                try:
                    xsec_token = await page.evaluate("""
                        () => {
                            const m = document.cookie.match(/xsec_token=([^;]+)/);
                            return m ? m[1] : '';
                        }
                    """) or ""
                except Exception:
                    xsec_token = ""

                title_elem = await item.query_selector(
                    "[class*='title'], [class*='Title']"
                )
                title = await title_elem.inner_text() if title_elem else ""

                feeds.append({
                    "id": post_id,
                    "title": title[:100] if title else "",
                    "xsec_token": xsec_token or "",
                    "link": link if link.startswith("http") else f"https://www.xiaohongshu.com{link}",
                })
            except Exception:
                continue

        return feeds
    except Exception as e:
        return []


async def workflow_search(page: Page, keyword: str, limit: int = 20) -> list[dict]:
    """Search by keyword. Returns list of post info dicts."""
    try:
        await page.goto(
            "https://www.xiaohongshu.com/search_result?"
            f"keyword={keyword}&source=web_search_result_notes",
            wait_until="networkidle",
            timeout=20000,
        )
        await asyncio.sleep(1.5)

        # 复用 feed 解析逻辑
        items = await page.query_selector_all(
            "section[class*='note'], [class*='note-item'], a[href*='/explore/']"
        )
        feeds = []
        seen_ids = set()

        for item in items[:limit * 2]:
            if len(feeds) >= limit:
                break
            try:
                link_elem = await item.query_selector("a[href*='/explore/']") or item
                link = await link_elem.get_attribute("href")
                if not link or "/explore/" not in link:
                    continue

                post_id = link.split("/explore/")[-1].split("?")[0].strip("/")
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                title_elem = await item.query_selector(
                    "[class*='title'], [class*='Title']"
                )
                title = await title_elem.inner_text() if title_elem else ""

                feeds.append({
                    "id": post_id,
                    "title": title[:100] if title else "",
                    "xsec_token": "",
                    "link": link if link.startswith("http") else f"https://www.xiaohongshu.com{link}",
                })
            except Exception:
                continue

        return feeds
    except Exception:
        return []


async def workflow_get_post_detail(
    page: Page,
    post_id: str,
    xsec_token: str = "",
) -> Optional[dict]:
    """Get post detail and comments."""
    try:
        url = f"https://www.xiaohongshu.com/explore/{post_id}"
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await asyncio.sleep(1.5)

        # 从 DOM 或 __INITIAL_STATE__ 提取详情
        detail = await page.evaluate("""
            () => {
                const state = window.__INITIAL_STATE__ || {};
                const noteMap = state.note && state.note.noteDetailMap;
                const note = state.note && state.note.note || 
                    (noteMap && noteMap[Object.keys(noteMap)[0]]);
                if (!note) return null;
                const m = document.cookie.match(/xsec_token=([^;]+)/);
                return {
                    id: note.noteId || note.id || '',
                    title: note.title || '',
                    content: note.desc || '',
                    author: (note.user && note.user.nickname) || '',
                    author_id: (note.user && note.user.userId) || '',
                    likes: (note.interactInfo && note.interactInfo.likedCount) || 0,
                    comments_count: (note.interactInfo && note.interactInfo.commentCount) || 0,
                    images: (note.imageList || []).map(function(i) { return i.url || i; }),
                    xsec_token: m ? m[1] : ''
                };
            }
        """)

        if not detail:
            # Fallback: 从 DOM 读取
            title_elem = await page.query_selector("[class*='title'], h1")
            content_elem = await page.query_selector("[class*='desc'], [class*='content']")
            detail = {
                "id": post_id,
                "title": await title_elem.inner_text() if title_elem else "",
                "content": await content_elem.inner_text() if content_elem else "",
                "author": "",
                "author_id": "",
                "likes": 0,
                "comments_count": 0,
                "images": [],
                "xsec_token": xsec_token or "",
            }

        # 评论列表
        comment_elems = await page.query_selector_all(
            "[class*='comment'] [class*='content'], [class*='comment-item']"
        )
        comments = []
        for ce in comment_elems[:50]:
            try:
                text = await ce.inner_text()
                if text and len(text) < 500:
                    comments.append({"content": text})
            except Exception:
                pass

        detail["comments"] = comments
        return detail
    except Exception:
        return None


async def workflow_post_comment(
    page: Page,
    post_id: str,
    content: str,
    xsec_token: str = "",
) -> bool:
    """Post a comment to a post (fixed workflow)."""
    try:
        url = f"https://www.xiaohongshu.com/explore/{post_id}"
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await _human_delay()

        # 查找评论输入框
        input_selectors = [
            "textarea[placeholder*='评论']",
            "textarea[placeholder*='说点什么']",
            "[contenteditable='true'][placeholder*='评论']",
            "div[class*='comment'] textarea",
        ]
        input_elem = None
        for sel in input_selectors:
            input_elem = await page.query_selector(sel)
            if input_elem:
                break

        if not input_elem:
            return False

        await input_elem.click()
        await _human_delay()
        await input_elem.fill(content[:500])  # 小红书评论有长度限制
        await _human_delay()

        # 查找发送按钮
        submit_selectors = [
            "button:has-text('发送')",
            "button:has-text('发布')",
            "[class*='submit']",
        ]
        for sel in submit_selectors:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                await asyncio.sleep(1)
                return True

        return False
    except Exception:
        return False


async def workflow_publish_content(
    page: Page,
    content: PublishContent,
) -> Optional[str]:
    """Publish image/text content (fixed workflow).

    小红书要求：标题不超过 20 字，正文不超过 1000 字。
    """
    try:
        await page.goto(
            "https://www.xiaohongshu.com/publish/publish",
            wait_until="networkidle",
            timeout=20000,
        )
        await asyncio.sleep(2)

        # 1. 上传图片
        if content.images:
            file_input = await page.query_selector(
                "input[type='file'][accept*='image']"
            )
            if file_input:
                for img_path in content.images[:9]:  # 最多 9 张
                    path = Path(img_path)
                    if path.exists():
                        await file_input.set_input_files(str(path))
                        await asyncio.sleep(1)

        # 2. 填写标题（最多 20 字）
        title = (content.title or "")[:20]
        if title:
            title_elem = await page.query_selector(
                "input[placeholder*='标题'], [placeholder*='添加标题']"
            )
            if title_elem:
                await title_elem.fill(title)
                await _human_delay()

        # 3. 填写正文（最多 1000 字）
        body = (content.content or "")[:1000]
        if body:
            body_elem = await page.query_selector(
                "textarea[placeholder*='正文'], [placeholder*='填写正文']"
            )
            if body_elem:
                await body_elem.fill(body)
                await _human_delay()

        # 4. 添加标签
        if content.tags:
            for tag in content.tags[:5]:
                tag_input = await page.query_selector(
                    "input[placeholder*='标签'], [placeholder*='添加标签']"
                )
                if tag_input:
                    await tag_input.fill(tag)
                    await asyncio.sleep(0.5)
                    # 选择弹出的标签
                    first = await page.query_selector("[class*='tag']:has-text('" + tag[:5] + "')")
                    if first:
                        await first.click()
                        await _human_delay()

        # 5. 点击发布
        publish_btn = await page.query_selector(
            "button:has-text('发布'), button:has-text('发布笔记']"
        )
        if publish_btn:
            await publish_btn.click()
            await asyncio.sleep(3)

            # 发布成功后会跳转，可尝试从 URL 或页面获取新帖子 ID
            url = page.url
            if "/explore/" in url:
                return url.split("/explore/")[-1].split("?")[0]
            return "published"

        return None
    except Exception:
        return None
