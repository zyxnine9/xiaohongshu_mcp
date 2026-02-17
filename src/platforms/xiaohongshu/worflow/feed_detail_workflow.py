"""Feed 详情流程 - 打开笔记详情页、可选加载全部评论、从 __INITIAL_STATE__.note.noteDetailMap 提取数据.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/12fcfe109b198108b4e1c26cefdf296ebca5991e/xiaohongshu/feed_detail.go
"""
import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ========== 配置常量 ==========
DEFAULT_MAX_ATTEMPTS = 500
STAGNANT_LIMIT = 20
MIN_SCROLL_DELTA = 10
MAX_CLICK_PER_ROUND = 3
LARGE_SCROLL_TRIGGER = 5
BUTTON_CLICK_INTERVAL = 3
FINAL_SPRINT_PUSH_COUNT = 15
FEED_DETAIL_TIMEOUT_MS = 10 * 60 * 1000  # 10 min

# 延迟时间配置（毫秒）
HUMAN_DELAY_RANGE = (300, 700)
REACTION_TIME_RANGE = (300, 800)
HOVER_TIME_RANGE = (100, 300)
READ_TIME_RANGE = (500, 1200)
SHORT_READ_RANGE = (600, 1200)
SCROLL_WAIT_RANGE = (100, 200)
POST_SCROLL_RANGE = (300, 500)


@dataclass
class CommentLoadConfig:
    """评论加载配置，与 Go CommentLoadConfig 一致."""

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
    return f"https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed"


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


async def _get_scroll_top(page: Page) -> int:
    try:
        result = await page.evaluate(
            "() => window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0"
        )
        return int(result) if result is not None else 0
    except Exception as e:
        logger.warning("获取滚动位置失败: %s", e)
        return 0


async def _get_comment_count(page: Page) -> int:
    try:
        elements = await page.query_selector_all(".parent-comment")
        return len(elements) if elements else 0
    except Exception as e:
        logger.warning("获取评论计数失败: %s", e)
        return 0


async def _get_total_comment_count(page: Page) -> int:
    try:
        total_el = await page.wait_for_selector(".comments-container .total", timeout=2000)
        if not total_el:
            return 0
        text = await total_el.text_content()
        if not text:
            return 0
        m = re.search(r"共(\d+)条评论", text)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


async def _check_no_comments_area(page: Page) -> bool:
    try:
        no_el = await page.wait_for_selector(".no-comments-text", timeout=2000)
        if not no_el:
            return False
        text = await no_el.text_content()
        return bool(text and "这是一片荒地" in text.strip())
    except Exception:
        return False


async def _check_end_container(page: Page) -> bool:
    try:
        end_el = await page.wait_for_selector(".end-container", timeout=2000)
        if not end_el:
            return False
        text = await end_el.text_content()
        if not text:
            return False
        upper = text.strip().upper()
        return "THE END" in upper or "THEEND" in upper
    except Exception:
        return False


async def _check_page_accessible(page: Page) -> Optional[str]:
    """检查页面是否可访问。可访问返回 None，不可访问返回错误信息."""
    await _sleep_random(500, 500)
    try:
        wrapper = await page.wait_for_selector(
            ".access-wrapper, .error-wrapper, .not-found-wrapper, .blocked-wrapper",
            timeout=2000,
        )
        if not wrapper:
            return None
        text = await wrapper.text_content()
        if not text:
            return None
        keywords = [
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
        for kw in keywords:
            if kw in text:
                logger.warning("笔记不可访问: %s", kw)
                return f"笔记不可访问: {kw}"
        trimmed = text.strip()
        if trimmed:
            logger.warning("笔记不可访问（未知原因）: %s", trimmed)
            return f"笔记不可访问: {trimmed}"
        return None
    except Exception:
        return None


# ========== 滚动相关 ==========


def _get_scroll_ratio(speed: str) -> float:
    if speed == "slow":
        return 0.5
    if speed == "fast":
        return 0.9
    return 0.7


def _calculate_scroll_delta(viewport_height: int, base_ratio: float) -> float:
    delta = float(viewport_height) * (base_ratio + random.random() * 0.2)
    if delta < 400:
        delta = 400
    return delta + (random.randint(-50, 50))


async def _human_scroll(
    page: Page,
    speed: str,
    large_mode: bool,
    push_count: int,
) -> tuple[bool, int, int]:
    before_top = await _get_scroll_top(page)
    viewport_height = await page.evaluate("() => window.innerHeight")
    viewport_height = viewport_height or 800
    base_ratio = _get_scroll_ratio(speed)
    if large_mode:
        base_ratio *= 2.0

    scrolled = False
    actual_delta = 0
    current_top = before_top

    for i in range(max(1, push_count)):
        scroll_delta = _calculate_scroll_delta(viewport_height, base_ratio)
        await page.evaluate("(delta) => window.scrollBy(0, delta)", scroll_delta)
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
        actual_delta = current_top - before_top + actual_delta
        scrolled = actual_delta > 5

    if scrolled:
        logger.debug("滚动: %s -> %s (Δ%s, large=%s, push=%s)", before_top - actual_delta, current_top, actual_delta, large_mode, push_count)
    return scrolled, actual_delta, current_top


async def _scroll_to_comments_area(page: Page) -> None:
    logger.info("滚动到评论区...")
    try:
        el = await page.wait_for_selector(".comments-container", timeout=2000)
        if el:
            await el.scroll_into_view_if_needed()
    except Exception:
        pass
    await asyncio.sleep(0.5)
    await _smart_scroll(page, 100)


async def _smart_scroll(page: Page, delta: float) -> None:
    """触发滚轮事件以正确触发懒加载."""
    await page.evaluate(
        """(delta) => {
        const target = document.querySelector('.note-scroller')
            || document.querySelector('.interaction-container')
            || document.documentElement;
        const ev = new WheelEvent('wheel', {
            deltaY: delta,
            deltaMode: 0,
            bubbles: true,
            cancelable: true,
            view: window
        });
        target.dispatchEvent(ev);
    }""",
        delta,
    )


async def _scroll_to_last_comment(page: Page) -> None:
    try:
        elements = await page.query_selector_all(".parent-comment")
        if not elements:
            return
        last = elements[-1]
        await last.scroll_into_view_if_needed()
    except Exception:
        pass


# ========== 按钮点击 ==========

REPLY_COUNT_REGEX = re.compile(r"展开\s*(\d+)\s*条回复")


def _should_skip_button(text: str, threshold: int) -> bool:
    if threshold <= 0:
        return False
    m = REPLY_COUNT_REGEX.search(text or "")
    if m:
        try:
            count = int(m.group(1))
            if count > threshold:
                logger.debug("跳过'%s'（回复数 %s > 阈值 %s）", text, count, threshold)
                return True
        except (ValueError, IndexError):
            pass
    return False


async def _click_element_with_human_behavior(page: Page, el: Any, text: str) -> bool:
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
            logger.debug("点击了'%s'", text)
            return True
        except Exception as e:
            logger.debug("点击重试 #%s: %s, 错误: %s", attempt, text, e)
            await asyncio.sleep(0.1 + random.random() * 0.2)
    logger.debug("点击失败 '%s'", text)
    return False


async def _click_show_more_buttons_smart(
    page: Page,
    max_replies_threshold: int,
) -> tuple[int, int]:
    clicked, skipped = 0, 0
    try:
        elements = await page.query_selector_all(".show-more")
    except Exception:
        return 0, 0
    max_click = MAX_CLICK_PER_ROUND + random.randint(0, MAX_CLICK_PER_ROUND)
    clicked_in_round = 0

    for el in elements:
        if clicked_in_round >= max_click:
            break
        try:
            is_visible = await el.is_visible()
            if not is_visible:
                continue
            box = await el.bounding_box()
            if not box or not box.get("width") or not box.get("height"):
                continue
            text = await el.text_content()
            if _should_skip_button(text or "", max_replies_threshold):
                skipped += 1
                continue
            if await _click_element_with_human_behavior(page, el, text or ""):
                clicked += 1
                clicked_in_round += 1
        except Exception:
            continue

    return clicked, skipped


# ========== 评论加载器 ==========


async def _load_all_comments_with_config(
    page: Page,
    config: CommentLoadConfig,
) -> None:
    max_attempts = DEFAULT_MAX_ATTEMPTS
    if config.max_comment_items > 0:
        max_attempts = config.max_comment_items * 3
    scroll_interval = _get_scroll_interval(config.scroll_speed)

    total_clicked = 0
    total_skipped = 0
    last_count = 0
    last_scroll_top = 0
    stagnant_checks = 0

    logger.info("开始加载评论...")
    await _scroll_to_comments_area(page)
    await _sleep_random(HUMAN_DELAY_RANGE[0], HUMAN_DELAY_RANGE[1])

    if await _check_no_comments_area(page):
        logger.info("✓ 检测到无评论区域（这是一片荒地），跳过加载")
        return

    for attempts in range(max_attempts):
        logger.debug("=== 尝试 %s/%s ===", attempts + 1, max_attempts)

        if await _check_end_container(page):
            current_count = await _get_comment_count(page)
            await _sleep_random(HUMAN_DELAY_RANGE[0], HUMAN_DELAY_RANGE[1])
            logger.info(
                "✓ 检测到 'THE END' 元素，已滑动到底部。加载完成: %s 条评论, 尝试: %s, 点击: %s, 跳过: %s",
                current_count,
                attempts + 1,
                total_clicked,
                total_skipped,
            )
            return

        if config.click_more_replies and attempts % BUTTON_CLICK_INTERVAL == 0:
            c, s = await _click_show_more_buttons_smart(page, config.max_replies_threshold)
            if c > 0 or s > 0:
                total_clicked += c
                total_skipped += s
                logger.info("点击'更多': %s 个, 跳过: %s 个, 累计点击: %s, 累计跳过: %s", c, s, total_clicked, total_skipped)
                await _sleep_random(READ_TIME_RANGE[0], READ_TIME_RANGE[1])
                c2, s2 = await _click_show_more_buttons_smart(page, config.max_replies_threshold)
                if c2 > 0 or s2 > 0:
                    total_clicked += c2
                    total_skipped += s2
                    logger.info("第 2 轮: 点击 %s, 跳过 %s", c2, s2)
                    await _sleep_random(SHORT_READ_RANGE[0], SHORT_READ_RANGE[1])

        current_count = await _get_comment_count(page)
        total_count = await _get_total_comment_count(page)
        logger.debug("当前评论: %s, 目标: %s", current_count, total_count)

        if current_count != last_count:
            logger.info("✓ 评论增加: %s -> %s (+%s)", last_count, current_count, current_count - last_count)
            last_count = current_count
            stagnant_checks = 0
        else:
            stagnant_checks += 1
            if stagnant_checks % 5 == 0:
                logger.debug("评论停滞 %s 次", stagnant_checks)

        if config.max_comment_items > 0 and current_count >= config.max_comment_items:
            logger.info("✓ 已达到目标评论数: %s/%s, 停止加载", current_count, config.max_comment_items)
            return

        if current_count > 0:
            await _scroll_to_last_comment(page)
            await _sleep_random(POST_SCROLL_RANGE[0], POST_SCROLL_RANGE[1])

        large_mode = stagnant_checks >= LARGE_SCROLL_TRIGGER
        push_count = 3 + random.randint(0, 2) if large_mode else 1
        _, scroll_delta, current_scroll_top = await _human_scroll(page, config.scroll_speed, large_mode, push_count)

        if scroll_delta < MIN_SCROLL_DELTA or current_scroll_top == last_scroll_top:
            stagnant_checks += 1
            if stagnant_checks % 5 == 0:
                logger.debug("滚动停滞 %s 次", stagnant_checks)
        else:
            stagnant_checks = 0
            last_scroll_top = current_scroll_top

        if stagnant_checks >= STAGNANT_LIMIT:
            logger.info("停滞过多，尝试大冲刺...")
            await _human_scroll(page, config.scroll_speed, True, 10)
            stagnant_checks = 0
            if await _check_end_container(page):
                current_count = await _get_comment_count(page)
                logger.info("✓ 到达底部，评论数: %s", current_count)

        await asyncio.sleep(scroll_interval)

    logger.info("达到最大尝试次数，最后冲刺...")
    await _human_scroll(page, config.scroll_speed, True, FINAL_SPRINT_PUSH_COUNT)
    current_count = await _get_comment_count(page)
    has_end = await _check_end_container(page)
    logger.info("✓ 加载结束: %s 条评论, 点击: %s, 跳过: %s, 到达底部: %s", current_count, total_clicked, total_skipped, has_end)


# ========== 数据提取 ==========


async def _extract_feed_detail(page: Page, feed_id: str) -> Optional[dict[str, Any]]:
    for _ in range(3):
        try:
            result = await page.evaluate(
                """() => {
                if (window.__INITIAL_STATE__
                    && window.__INITIAL_STATE__.note
                    && window.__INITIAL_STATE__.note.noteDetailMap) {
                    const noteDetailMap = window.__INITIAL_STATE__.note.noteDetailMap;
                    return JSON.stringify(noteDetailMap);
                }
                return "";
            }"""
            )
            if result and isinstance(result, str) and result != "":
                note_detail_map = json.loads(result)
                if not isinstance(note_detail_map, dict):
                    return None
                entry = note_detail_map.get(feed_id)
                if entry is None:
                    logger.error("feed %s not found in noteDetailMap", feed_id)
                    return None
                return entry
            await _sleep_random(200, 300)
        except Exception as e:
            logger.debug("提取 Feed 详情重试: %s", e)
            await _sleep_random(200, 300)
    logger.error("提取 Feed 详情失败")
    return None


# ========== 主入口 ==========


async def get_feed_detail(
    page: Page,
    feed_id: str,
    xsec_token: str,
    load_all_comments: bool = False,
    config: Optional[CommentLoadConfig] = None,
) -> Optional[dict[str, Any]]:
    """获取单条 Feed 详情（与 Go GetFeedDetail 一致）。

    打开笔记详情页，可选加载全部评论，从 window.__INITIAL_STATE__.note.noteDetailMap 提取 note + comments。

    Args:
        page: Playwright 页面。
        feed_id: 笔记 ID。
        xsec_token: xsec_token（从 feed 列表项获取）。
        load_all_comments: 是否加载全部评论（滚动+点击「更多回复」）。
        config: 评论加载配置，默认使用 default_comment_load_config()。

    Returns:
        包含 "note" 和 "comments" 的 dict，与 Go FeedDetailResponse 对应；失败返回 None。
    """
    return await get_feed_detail_with_config(
        page, feed_id, xsec_token, load_all_comments, config or default_comment_load_config()
    )


async def get_feed_detail_with_config(
    page: Page,
    feed_id: str,
    xsec_token: str,
    load_all_comments: bool,
    config: CommentLoadConfig,
) -> Optional[dict[str, Any]]:
    """与 Go GetFeedDetailWithConfig 一致."""
    page.set_default_timeout(FEED_DETAIL_TIMEOUT_MS)
    url = make_feed_detail_url(feed_id, xsec_token)

    logger.info("打开 feed 详情页: %s", url)
    logger.info(
        "配置: 点击更多=%s, 回复阈值=%s, 最大评论数=%s, 滚动速度=%s",
        config.click_more_replies,
        config.max_replies_threshold,
        config.max_comment_items,
        config.scroll_speed,
    )

    for attempt in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=FEED_DETAIL_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            break
        except Exception as e:
            logger.debug("页面导航重试 #%s: %s", attempt, e)
            await asyncio.sleep(0.5 + random.random())
    else:
        logger.error("页面导航失败")
        return None

    await _sleep_random(1000, 1000)

    err = await _check_page_accessible(page)
    if err:
        logger.warning("页面不可访问: %s", err)
        return None

    if load_all_comments:
        try:
            await _load_all_comments_with_config(page, config)
        except Exception as e:
            logger.warning("加载全部评论失败: %s", e)

    return await _extract_feed_detail(page, feed_id)
