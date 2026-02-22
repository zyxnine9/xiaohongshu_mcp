"""Feed 评论流程 - 发表评论、回复评论.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/main/xiaohongshu/comment_feed.go
"""
import asyncio
import logging
from typing import Optional

from playwright.async_api import ElementHandle, Page

from .feed_detail import (
    make_feed_detail_url,
    _check_page_accessible,
    _check_end_container,
    _scroll_to_comments_area,
)

logger = logging.getLogger(__name__)

# 超时配置（与 Go 一致）
POST_COMMENT_TIMEOUT_MS = 60_000
REPLY_COMMENT_TIMEOUT_MS = 5 * 60 * 1000  # 5 min
FIND_COMMENT_MAX_ATTEMPTS = 100
FIND_COMMENT_SCROLL_INTERVAL_MS = 800
ELEMENT_WAIT_TIMEOUT_MS = 2000


async def post_comment(
    page: Page,
    feed_id: str,
    xsec_token: str,
    content: str,
) -> bool:
    """发表评论到 Feed（与 Go PostComment 一致）.

    Args:
        page: Playwright 页面。
        feed_id: 笔记 ID。
        xsec_token: 访问令牌。
        content: 评论内容。

    Returns:
        成功返回 True，失败返回 False。
    """
    page.set_default_timeout(POST_COMMENT_TIMEOUT_MS)
    url = make_feed_detail_url(feed_id, xsec_token)
    logger.info("打开 feed 详情页: %s", url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=POST_COMMENT_TIMEOUT_MS)
        await page.wait_for_load_state("networkidle", timeout=POST_COMMENT_TIMEOUT_MS)
    except (TimeoutError, RuntimeError) as e:
        logger.warning("页面导航失败: %s", e)
        return False

    await asyncio.sleep(1)

    err = await _check_page_accessible(page)
    if err:
        logger.warning("页面不可访问: %s", err)
        return False

    # 查找并点击评论输入框（触发聚焦）
    elem = await page.query_selector("div.input-box div.content-edit span")
    if not elem:
        logger.warning("未找到评论输入框，该帖子可能不支持评论或网页端不可访问")
        return False

    try:
        await elem.click()
    except Exception as e:
        logger.warning("无法点击评论输入框: %s", e)
        return False

    # 查找评论输入区域并输入内容
    elem2 = await page.query_selector("div.input-box div.content-edit p.content-input")
    if not elem2:
        logger.warning("未找到评论输入区域")
        return False

    try:
        await elem2.fill(content)
    except Exception as e:
        logger.warning("无法输入评论内容: %s", e)
        return False

    await asyncio.sleep(1)

    # 查找并点击提交按钮
    submit_button = await page.query_selector("div.bottom button.submit")
    if not submit_button:
        logger.warning("未找到提交按钮")
        return False

    try:
        await submit_button.click()
    except Exception as e:
        logger.warning("无法点击提交按钮: %s", e)
        return False

    await asyncio.sleep(1)
    logger.info("评论发表成功: feed=%s", feed_id)
    return True


async def reply_to_comment(
    page: Page,
    feed_id: str,
    xsec_token: str,
    content: str,
    comment_id: str = "",
    user_id: str = "",
) -> bool:
    """回复指定评论（与 Go ReplyToComment 一致）.

    需要提供 comment_id 或 user_id 至少其一以定位目标评论。

    Args:
        page: Playwright 页面。
        feed_id: 笔记 ID。
        xsec_token: 访问令牌。
        content: 回复内容。
        comment_id: 目标评论 ID，用于 #comment-{commentID} 查找。
        user_id: 目标用户 ID，用于 [data-user-id] 查找。

    Returns:
        成功返回 True，失败返回 False。
    """
    if not comment_id and not user_id:
        logger.warning("必须提供 comment_id 或 user_id 至少其一")
        return False

    page.set_default_timeout(REPLY_COMMENT_TIMEOUT_MS)
    url = make_feed_detail_url(feed_id, xsec_token)
    logger.info("打开 feed 详情页进行回复: %s", url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=REPLY_COMMENT_TIMEOUT_MS)
        await page.wait_for_load_state("networkidle", timeout=REPLY_COMMENT_TIMEOUT_MS)
    except (TimeoutError, RuntimeError) as e:
        logger.warning("页面导航失败: %s", e)
        return False

    await asyncio.sleep(1)

    err = await _check_page_accessible(page)
    if err:
        logger.warning("页面不可访问: %s", err)
        return False

    # 等待评论容器加载
    await asyncio.sleep(2)

    comment_el = await _find_comment_element(page, comment_id, user_id)
    if not comment_el:
        logger.warning("无法找到评论 (comment_id=%s, user_id=%s)", comment_id, user_id)
        return False

    try:
        logger.info("滚动到评论位置...")
        await comment_el.scroll_into_view_if_needed()
        await asyncio.sleep(1)

        logger.info("准备点击回复按钮")
        reply_btn = await comment_el.query_selector(".right .interactions .reply")
        if not reply_btn:
            logger.warning("无法找到回复按钮")
            return False

        await reply_btn.click()
        await asyncio.sleep(1)

        input_el = await page.query_selector("div.input-box div.content-edit p.content-input")
        if not input_el:
            logger.warning("无法找到回复输入框")
            return False

        await input_el.fill(content)
        await asyncio.sleep(0.5)

        submit_btn = await page.query_selector("div.bottom button.submit")
        if not submit_btn:
            logger.warning("无法找到提交按钮")
            return False

        await submit_btn.click()
        await asyncio.sleep(2)
        logger.info("回复评论成功")
        return True
    except Exception as e:
        logger.warning("回复评论失败: %s", e)
        return False


async def _get_comment_count_for_find(page: Page) -> int:
    """获取当前可见评论数量（与 Go getCommentCount 一致，使用多个选择器）."""
    for _ in range(3):
        try:
            elements = await page.query_selector_all(
                ".parent-comment, .comment-item, .comment"
            )
            return len(elements) if elements else 0
        except Exception:
            await asyncio.sleep(0.1)
    return 0


async def _find_comment_element(
    page: Page,
    comment_id: str,
    user_id: str,
) -> Optional[ElementHandle]:
    """查找指定评论元素（与 Go findCommentElement 一致）."""
    logger.info("开始查找评论 - comment_id: %s, user_id: %s", comment_id, user_id)

    await _scroll_to_comments_area(page)
    await asyncio.sleep(1)

    last_comment_count = 0
    stagnant_checks = 0

    for attempt in range(FIND_COMMENT_MAX_ATTEMPTS):
        logger.debug("=== 查找尝试 %d/%d ===", attempt + 1, FIND_COMMENT_MAX_ATTEMPTS)

        if await _check_end_container(page):
            logger.info("已到达评论底部，未找到目标评论")
            break

        current_count = await _get_comment_count_for_find(page)
        logger.debug("当前评论数: %d", current_count)

        if current_count != last_comment_count:
            logger.debug("✓ 评论数增加: %d -> %d", last_comment_count, current_count)
            last_comment_count = current_count
            stagnant_checks = 0
        else:
            stagnant_checks += 1
            if stagnant_checks % 5 == 0:
                logger.debug("评论数停滞 %d 次", stagnant_checks)

        if stagnant_checks >= 10:
            logger.info("评论数量停滞超过10次，可能已加载完所有评论")
            break

        if current_count > 0:
            elements = await page.query_selector_all(
                ".parent-comment, .comment-item, .comment"
            )
            if elements:
                await elements[-1].scroll_into_view_if_needed()
            await asyncio.sleep(0.3)

        await page.evaluate(
            "() => { window.scrollBy(0, window.innerHeight * 0.8); return true; }"
        )
        await asyncio.sleep(0.5)

        if comment_id:
            selector = f"#comment-{comment_id}"
            try:
                page_with_timeout = page
                el = await page_with_timeout.wait_for_selector(
                    selector, timeout=ELEMENT_WAIT_TIMEOUT_MS
                )
                if el:
                    logger.info("✓ 通过 comment_id 找到评论: %s (尝试 %d 次)", comment_id, attempt + 1)
                    return el
            except Exception:
                pass
            logger.debug("未找到 comment_id (超时)")

        if user_id:
            elements = await page.query_selector_all(
                ".comment-item, .comment, .parent-comment"
            )
            if elements:
                for i, el in enumerate(elements):
                    try:
                        user_el = await el.query_selector(f'[data-user-id="{user_id}"]')
                        if user_el:
                            logger.info(
                                "✓ 通过 user_id 在第 %d 个元素中找到评论: %s (尝试 %d 次)",
                                i + 1,
                                user_id,
                                attempt + 1,
                            )
                            return el
                    except Exception:
                        continue
            logger.debug("获取评论元素失败或超时")

        logger.debug("本次尝试未找到目标评论，继续下一轮...")
        await asyncio.sleep(FIND_COMMENT_SCROLL_INTERVAL_MS / 1000.0)

    logger.warning(
        "未找到评论 (comment_id: %s, user_id: %s), 尝试次数: %d",
        comment_id,
        user_id,
        FIND_COMMENT_MAX_ATTEMPTS,
    )
    return None
