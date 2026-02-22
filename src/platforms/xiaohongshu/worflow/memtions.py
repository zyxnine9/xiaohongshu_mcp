"""@人/提及流程 - 从消息通知页 __INITIAL_STATE__.notification.notificationMap.mentions 拉取提及列表."""
import asyncio
import json
from typing import Any

from playwright.async_api import Page

# 与 search.go 一致：超时 60s
SEARCH_PAGE_TIMEOUT_MS = 60_000


def make_mentions_url() -> str:
    """构造小红书消息通知（@人/提及）页 URL."""
    return "https://www.xiaohongshu.com/notification"


async def get_mention_list(
    page: Page,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """从消息通知页 window.__INITIAL_STATE__.notification.notificationMap.mentions 获取提及列表。

    Args:
        page: Playwright 页面。
        limit: 最多返回条数，默认 20。

    Returns:
        原始提及消息列表（每项为 dict），无数据或出错时返回空列表。
    """
    mentions_url = make_mentions_url()
    try:
        await page.goto(
            mentions_url,
            wait_until="domcontentloaded",
            timeout=SEARCH_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_load_state("networkidle", timeout=SEARCH_PAGE_TIMEOUT_MS)
    except (TimeoutError, RuntimeError):
        return []

    # 与 Go MustWait 一致：等待 __INITIAL_STATE__ 存在
    try:
        await page.wait_for_function(
            "() => window.__INITIAL_STATE__ !== undefined",
            timeout=SEARCH_PAGE_TIMEOUT_MS,
        )
    except (TimeoutError, RuntimeError):
        return []

    await asyncio.sleep(1)

    try:
        result = await page.evaluate("""() => {
            if (window.__INITIAL_STATE__ &&
                window.__INITIAL_STATE__.notification &&
                window.__INITIAL_STATE__.notification.notificationMap &&
                window.__INITIAL_STATE__.notification.notificationMap.mentions) {
                const mentions = window.__INITIAL_STATE__.notification.notificationMap.mentions;
                const msgList = mentions.messageList;
                if (!msgList) return "";
                const listData = msgList.value !== undefined ? msgList.value :
                    (msgList._value !== undefined ? msgList._value : msgList);
                if (listData) {
                    const arr = Array.isArray(listData) ? listData : [];
                    return JSON.stringify(arr);
                }
            }
            return "";
        }""")
    except (TimeoutError, RuntimeError):
        return []

    if not result or not isinstance(result, str):
        return []

    try:
        items = json.loads(result)
        if not isinstance(items, list):
            return []
        return items[:limit]
    except (json.JSONDecodeError, TypeError):
        return []
