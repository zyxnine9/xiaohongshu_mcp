"""Feed 详情流程 - 打开笔记详情页、加载评论、从 __INITIAL_STATE__.note.noteDetailMap 提取数据.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/12fcfe109b198108b4e1c26cefdf296ebca5991e/xiaohongshu/feed_detail.go
"""
import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

from playwright.async_api import ElementHandle, Page

logger = logging.getLogger(__name__)

# ========== 配置常量（与 feed_detail.go 一致）==========
DEFAULT_MAX_ATTEMPTS = 500
STAGNANT_LIMIT = 20
MIN_SCROLL_DELTA = 10
MAX_CLICK_PER_ROUND = 3
LARGE_SCROLL_TRIGGER = 5
BUTTON_CLICK_INTERVAL = 3
FINAL_SPRINT_PUSH_COUNT = 15
FEED_DETAIL_PAGE_TIMEOUT_MS = 10 * 60 * 1000  # 10 min

# 延迟范围（毫秒）
HUMAN_DELAY_RANGE = (300, 700)
REACTION_TIME_RANGE = (300, 800)
HOVER_TIME_RANGE = (100, 300)
READ_TIME_RANGE = (500, 1200)
SHORT_READ_RANGE = (600, 1200)
SCROLL_WAIT_RANGE = (100, 200)
POST_SCROLL_RANGE = (300, 500)

# 页面不可访问关键词
PAGE_BLOCKED_KEYWORDS = [
    "当前笔记暂时无法浏览",
    "该内容因违规已被删除",
    "该笔记已被删除",
    "内容不存在",
    "笔记不存在",
    "已失效",
    "私密笔记",
    "仅作者可见",
    "因用户设置，你无法查看",
    "因违规无法查看",
]

REPLY_COUNT_REGEX = re.compile(r"展开\s*(\d+)\s*条回复")
TOTAL_COMMENT_REGEX = re.compile(r"共(\d+)条评论")


@dataclass
class CommentLoadConfig:
    """评论加载配置（与 Go CommentLoadConfig 一致）."""

    click_more_replies: bool = False
    max_replies_threshold: int = 10
    max_comment_items: int = 0
    scroll_speed: str = "normal"


def default_comment_load_config() -> CommentLoadConfig:
    """默认评论加载配置."""
    return CommentLoadConfig(
        click_more_replies=False,
        max_replies_threshold=10,
        max_comment_items=0,
        scroll_speed="normal",
    )


def make_feed_detail_url(feed_id: str, xsec_token: str) -> str:
    """构造笔记详情页 URL，与 Go makeFeedDetailURL 一致."""
    return (
        f"https://www.xiaohongshu.com/explore/{feed_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_feed"
    )


# ========== 工具函数 ==========


async def _sleep_random(min_ms: int, max_ms: int) -> None:
    if max_ms <= min_ms:
        await asyncio.sleep(min_ms / 1000.0)
        return
    delay_ms = min_ms + random.randint(0, max_ms - min_ms)
    await asyncio.sleep(delay_ms / 1000.0)


def _get_scroll_interval(speed: str) -> float:
    """返回滚动间隔秒数."""
    if speed == "slow":
        return (1200 + random.randint(0, 300)) / 1000.0
    if speed == "fast":
        return (300 + random.randint(0, 100)) / 1000.0
    return (600 + random.randint(0, 200)) / 1000.0


def _get_scroll_ratio(speed: str) -> float:
    if speed == "slow":
        return 0.5
    if speed == "fast":
        return 0.9
    return 0.7


# ========== 页面检查 ==========


async def _check_page_accessible(page: Page) -> Optional[str]:
    """检查页面是否可访问。可访问返回 None，不可访问返回错误信息."""
    await asyncio.sleep(0.5)
    try:
        wrapper = await page.query_selector(
            ".access-wrapper, .error-wrapper, .not-found-wrapper, .blocked-wrapper"
        )
    except (TimeoutError, RuntimeError):
        return None
    if not wrapper:
        return None
    try:
        text = await wrapper.text_content()
    except Exception:
        return None
    text = (text or "").strip()
    for kw in PAGE_BLOCKED_KEYWORDS:
        if kw in text:
            logger.warning("笔记不可访问: %s", kw)
            return f"笔记不可访问: {kw}"
    if text:
        logger.warning("笔记不可访问（未知原因）: %s", text)
        return f"笔记不可访问: {text}"
    return None


# ========== DOM 查询 ==========


async def _get_scroll_top(page: Page) -> int:
    for _ in range(3):
        try:
            result = await page.evaluate(
                "() => window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0"
            )
            return int(result)
        except Exception:
            await asyncio.sleep(0.1 + random.random() * 0.2)
    return 0


async def _get_comment_count(page: Page) -> int:
    for _ in range(3):
        try:
            elements = await page.query_selector_all(".parent-comment")
            return len(elements) if elements else 0
        except Exception:
            await asyncio.sleep(0.1 + random.random() * 0.2)
    return 0


async def _get_total_comment_count(page: Page) -> int:
    for _ in range(3):
        try:
            el = await page.query_selector(".comments-container .total")
            if not el:
                return 0
            text = await el.text_content() or ""
            m = TOTAL_COMMENT_REGEX.search(text)
            if m:
                return int(m.group(1))
            return 0
        except Exception:
            await asyncio.sleep(0.1 + random.random() * 0.2)
    return 0


async def _check_no_comments_area(page: Page) -> bool:
    try:
        el = await page.query_selector(".no-comments-text")
        if not el:
            return False
        text = (await el.text_content() or "").strip()
        return "这是一片荒地" in text
    except Exception:
        return False


async def _check_end_container(page: Page) -> bool:
    for _ in range(3):
        try:
            el = await page.query_selector(".end-container")
            if not el:
                return False
            text = (await el.text_content() or "").strip().upper()
            return "THE END" in text or "THEEND" in text
        except Exception:
            await asyncio.sleep(0.1 + random.random() * 0.2)
    return False


# ========== 滚动 ==========


async def _scroll_to_comments_area(page: Page) -> None:
    logger.info("滚动到评论区...")
    try:
        el = await page.wait_for_selector(".comments-container", timeout=2000)
        if el:
            await el.scroll_into_view_if_needed()
    except Exception:
        pass
    await asyncio.sleep(0.5)
    await page.evaluate(
        """(delta) => {
        const target = document.querySelector('.note-scroller')
            || document.querySelector('.interaction-container')
            || document.documentElement;
        const ev = new WheelEvent('wheel', { deltaY: delta, deltaMode: 0, bubbles: true, cancelable: true, view: window });
        target.dispatchEvent(ev);
    }""",
        100,
    )


async def _scroll_to_last_comment(page: Page) -> None:
    try:
        elements = await page.query_selector_all(".parent-comment")
        if not elements:
            return
        await elements[-1].scroll_into_view_if_needed()
    except Exception:
        pass


async def _human_scroll(
    page: Page,
    speed: str,
    large_mode: bool,
    push_count: int,
) -> tuple[bool, int, int]:
    before_top = await _get_scroll_top(page)
    viewport_height = await page.evaluate("() => window.innerHeight")
    base_ratio = _get_scroll_ratio(speed)
    if large_mode:
        base_ratio *= 2.0
    actual_delta = 0
    current_top = before_top
    scrolled = False
    for i in range(max(1, push_count)):
        scroll_delta = viewport_height * (base_ratio + random.random() * 0.2)
        if scroll_delta < 400:
            scroll_delta = 400
        scroll_delta += random.randint(-50, 50)
        await page.evaluate("(d) => { window.scrollBy(0, d); }", scroll_delta)
        await _sleep_random(SCROLL_WAIT_RANGE[0], SCROLL_WAIT_RANGE[1])
        current_top = await _get_scroll_top(page)
        delta_this = current_top - before_top
        actual_delta += delta_this
        if delta_this > 5:
            scrolled = True
        before_top = current_top
        if i < push_count - 1:
            await _sleep_random(HUMAN_DELAY_RANGE[0], HUMAN_DELAY_RANGE[1])
    if not scrolled and push_count > 0:
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await _sleep_random(POST_SCROLL_RANGE[0], POST_SCROLL_RANGE[1])
        current_top = await _get_scroll_top(page)
        actual_delta = current_top - (before_top - actual_delta) + actual_delta
        scrolled = actual_delta > 5
    return scrolled, actual_delta, current_top


# ========== 按钮点击 ==========


def _should_skip_button(text: str, threshold: int) -> bool:
    if threshold <= 0:
        return False
    m = REPLY_COUNT_REGEX.search(text)
    if m:
        try:
            reply_count = int(m.group(1))
            if reply_count > threshold:
                logger.debug("跳过'%s'（回复数 %d > 阈值 %d）", text, reply_count, threshold)
                return True
        except ValueError:
            pass
    return False


async def _is_element_clickable(el: ElementHandle) -> bool:
    try:
        visible = await el.is_visible()
        if not visible:
            return False
        box = await el.bounding_box()
        return box is not None
    except Exception:
        return False


async def _click_element_with_human_behavior(
    page: Page,
    el: ElementHandle,
    text: str,
) -> bool:
    for attempt in range(3):
        try:
            await el.evaluate("el => el.scrollIntoView({ behavior: 'smooth', block: 'center' })")
            await _sleep_random(REACTION_TIME_RANGE[0], REACTION_TIME_RANGE[1])
            box = await el.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await page.mouse.move(x, y)
                await _sleep_random(HOVER_TIME_RANGE[0], HOVER_TIME_RANGE[1])
            await el.click()
            await _sleep_random(READ_TIME_RANGE[0], READ_TIME_RANGE[1])
            return True
        except Exception as e:
            logger.debug("点击重试 #%d: %s, 错误: %s", attempt + 1, text, e)
            await asyncio.sleep(0.1 + random.random() * 0.2)
    return False


async def _click_show_more_buttons_smart(
    page: Page,
    max_replies_threshold: int,
) -> tuple[int, int]:
    elements = await page.query_selector_all(".show-more")
    if not elements:
        return 0, 0
    max_click = MAX_CLICK_PER_ROUND + random.randint(0, MAX_CLICK_PER_ROUND)
    clicked = skipped = 0
    for el in elements:
        if clicked >= max_click:
            break
        if not await _is_element_clickable(el):
            continue
        try:
            text = await el.text_content() or ""
        except Exception:
            continue
        if _should_skip_button(text, max_replies_threshold):
            skipped += 1
            continue
        if await _click_element_with_human_behavior(page, el, text):
            clicked += 1
    return clicked, skipped


# ========== 评论加载器 ==========


@dataclass
class _LoadState:
    last_count: int = 0
    last_scroll_top: int = 0
    stagnant_checks: int = 0


@dataclass
class _LoadStats:
    total_clicked: int = 0
    total_skipped: int = 0
    attempts: int = 0


async def _load_all_comments_with_config(
    page: Page,
    config: CommentLoadConfig,
) -> None:
    state = _LoadState()
    stats = _LoadStats()
    max_attempts = (
        config.max_comment_items * 3 if config.max_comment_items > 0 else DEFAULT_MAX_ATTEMPTS
    )
    scroll_interval = _get_scroll_interval(config.scroll_speed)

    logger.info("开始加载评论...")
    await _scroll_to_comments_area(page)
    await _sleep_random(HUMAN_DELAY_RANGE[0], HUMAN_DELAY_RANGE[1])

    if await _check_no_comments_area(page):
        logger.info("✓ 检测到无评论区域（这是一片荒地），跳过加载")
        return

    for stats.attempts in range(max_attempts):
        logger.debug("=== 尝试 %d/%d ===", stats.attempts + 1, max_attempts)

        if await _check_end_container(page):
            current_count = await _get_comment_count(page)
            logger.info(
                "✓ 检测到 'THE END' 元素，已滑动到底部。加载完成: %d 条评论, 尝试: %d, 点击: %d, 跳过: %d",
                current_count,
                stats.attempts + 1,
                stats.total_clicked,
                stats.total_skipped,
            )
            return

        if config.click_more_replies and stats.attempts % BUTTON_CLICK_INTERVAL == 0:
            clicked, skipped = await _click_show_more_buttons_smart(
                page, config.max_replies_threshold
            )
            if clicked > 0 or skipped > 0:
                stats.total_clicked += clicked
                stats.total_skipped += skipped
                logger.info(
                    "点击'更多': %d 个, 跳过: %d 个, 累计点击: %d, 累计跳过: %d",
                    clicked,
                    skipped,
                    stats.total_clicked,
                    stats.total_skipped,
                )
                await _sleep_random(READ_TIME_RANGE[0], READ_TIME_RANGE[1])
                clicked2, skipped2 = await _click_show_more_buttons_smart(
                    page, config.max_replies_threshold
                )
                if clicked2 > 0 or skipped2 > 0:
                    stats.total_clicked += clicked2
                    stats.total_skipped += skipped2
                    logger.info("第 2 轮: 点击 %d, 跳过 %d", clicked2, skipped2)
                    await _sleep_random(SHORT_READ_RANGE[0], SHORT_READ_RANGE[1])

        current_count = await _get_comment_count(page)
        total_count = await _get_total_comment_count(page)
        logger.debug("当前评论: %d, 目标: %d", current_count, total_count)

        if current_count != state.last_count:
            logger.info(
                "✓ 评论增加: %d -> %d (+%d)",
                state.last_count,
                current_count,
                current_count - state.last_count,
            )
            state.last_count = current_count
            state.stagnant_checks = 0
        else:
            state.stagnant_checks += 1
            if state.stagnant_checks % 5 == 0:
                logger.debug("评论停滞 %d 次", state.stagnant_checks)

        if config.max_comment_items > 0 and current_count >= config.max_comment_items:
            logger.info(
                "✓ 已达到目标评论数: %d/%d, 停止加载",
                current_count,
                config.max_comment_items,
            )
            return

        await _scroll_to_last_comment(page)
        await _sleep_random(POST_SCROLL_RANGE[0], POST_SCROLL_RANGE[1])
        large_mode = state.stagnant_checks >= LARGE_SCROLL_TRIGGER
        push_count = 3 + random.randint(0, 3) if large_mode else 1
        _scrolled, scroll_delta, current_scroll_top = await _human_scroll(
            page, config.scroll_speed, large_mode, push_count
        )
        if scroll_delta < MIN_SCROLL_DELTA or current_scroll_top == state.last_scroll_top:
            state.stagnant_checks += 1
            if state.stagnant_checks % 5 == 0:
                logger.debug("滚动停滞 %d 次", state.stagnant_checks)
        else:
            state.stagnant_checks = 0
            state.last_scroll_top = current_scroll_top

        if state.stagnant_checks >= STAGNANT_LIMIT:
            logger.info("停滞过多，尝试大冲刺...")
            await _human_scroll(page, config.scroll_speed, True, 10)
            state.stagnant_checks = 0
            if await _check_end_container(page):
                current_count = await _get_comment_count(page)
                logger.info("✓ 到达底部，评论数: %d", current_count)

        await asyncio.sleep(scroll_interval)

    logger.info("达到最大尝试次数，最后冲刺...")
    await _human_scroll(page, config.scroll_speed, True, FINAL_SPRINT_PUSH_COUNT)
    current_count = await _get_comment_count(page)
    has_end = await _check_end_container(page)
    logger.info(
        "✓ 加载结束: %d 条评论, 点击: %d, 跳过: %d, 到达底部: %s",
        current_count,
        stats.total_clicked,
        stats.total_skipped,
        has_end,
    )


# ========== 数据提取 ==========


async def _extract_feed_detail(page: Page, feed_id: str) -> Optional[dict[str, Any]]:
    """从 window.__INITIAL_STATE__.note.noteDetailMap 提取笔记详情与评论."""
    result: Optional[str] = None
    for _ in range(3):
        try:
            raw = await page.evaluate(
                """() => {
                if (window.__INITIAL_STATE__
                    && window.__INITIAL_STATE__.note
                    && window.__INITIAL_STATE__.note.noteDetailMap) {
                    return JSON.stringify(window.__INITIAL_STATE__.note.noteDetailMap);
                }
                return "";
            }"""
            )
            if raw and isinstance(raw, str) and raw != "":
                result = raw
                break
        except Exception:
            await asyncio.sleep(0.2 + random.random() * 0.3)
    if not result:
        logger.error("无法获取初始状态数据")
        return None
    try:
        note_detail_map = json.loads(result)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("解析 noteDetailMap 失败: %s", e)
        return None
    if not isinstance(note_detail_map, dict) or feed_id not in note_detail_map:
        logger.error("feed %s 不在 noteDetailMap 中", feed_id)
        return None
    entry = note_detail_map[feed_id]
    return {
        "note": entry.get("note", {}),
        "comments": entry.get("comments", {}),
    }


# ========== 主入口 ==========


async def get_feed_detail(
    page: Page,
    feed_id: str,
    xsec_token: str,
    load_all_comments: bool = False,
    config: Optional[CommentLoadConfig] = None,
) -> Optional[dict[str, Any]]:
    """打开笔记详情页，可选加载全部评论，并提取 note + comments（与 Go GetFeedDetailWithConfig 一致）.

    Args:
        page: Playwright 页面。
        feed_id: 笔记 ID。
        xsec_token: 访问令牌。
        load_all_comments: 是否滚动加载全部评论。
        config: 评论加载配置，默认使用 default_comment_load_config()。

    Returns:
        包含 "note" 和 "comments" 的字典；失败返回 None。
    """
    page.set_default_timeout(FEED_DETAIL_PAGE_TIMEOUT_MS)
    url = make_feed_detail_url(feed_id, xsec_token)
    cfg = config or default_comment_load_config()

    logger.info("打开 feed 详情页: %s", url)
    logger.info(
        "配置: 点击更多=%s, 回复阈值=%d, 最大评论数=%d, 滚动速度=%s",
        cfg.click_more_replies,
        cfg.max_replies_threshold,
        cfg.max_comment_items,
        cfg.scroll_speed,
    )

    for attempt in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=FEED_DETAIL_PAGE_TIMEOUT_MS)
            await page.wait_for_load_state("networkidle", timeout=FEED_DETAIL_PAGE_TIMEOUT_MS)
            break
        except (TimeoutError, RuntimeError) as e:
            logger.debug("页面导航重试 #%d: %s", attempt + 1, e)
            await asyncio.sleep(0.5 + random.random())
    else:
        logger.error("页面导航失败")
        return None

    await _sleep_random(1000, 2000)

    err = await _check_page_accessible(page)
    if err:
        logger.warning("页面不可访问: %s", err)
        return None

    if load_all_comments:
        try:
            await _load_all_comments_with_config(page, cfg)
        except Exception as e:
            logger.warning("加载全部评论失败: %s", e)

    return await _extract_feed_detail(page, feed_id)
