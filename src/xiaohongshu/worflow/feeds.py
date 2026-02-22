"""Feed 列表流程 - 从首页 __INITIAL_STATE__ 拉取 Feed 数据."""
import asyncio
import json
from typing import Any

from playwright.async_api import Page

# 与 feeds.go 一致：首页 URL，超时 60s
FEEDS_HOME_URL = "https://www.xiaohongshu.com"
FEEDS_PAGE_TIMEOUT_MS = 60_000


async def get_feeds_list(page: Page) -> list[dict[str, Any]]:
    """从当前页面的 window.__INITIAL_STATE__.feed.feeds 获取 Feed 列表。

    会先导航到小红书首页并等待 DOM 稳定，再执行与 Go 相同的取值逻辑：
    feeds.value ?? feeds._value，返回解析后的 list[dict]。

    Returns:
        原始 Feed 项列表（每项为 dict），无数据或出错时返回空列表。
    """
    try:
        await page.goto(
            FEEDS_HOME_URL,
            wait_until="domcontentloaded",
            timeout=FEEDS_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_load_state("networkidle", timeout=FEEDS_PAGE_TIMEOUT_MS)
    except (TimeoutError, RuntimeError):
        return []

    await asyncio.sleep(1)

    try:
        result = await page.evaluate("""() => {
            if (window.__INITIAL_STATE__ &&
                window.__INITIAL_STATE__.feed &&
                window.__INITIAL_STATE__.feed.feeds) {
                const feeds = window.__INITIAL_STATE__.feed.feeds;
                const feedsData = feeds.value !== undefined ? feeds.value : feeds._value;
                if (feedsData) {
                    return JSON.stringify(feedsData);
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
        return items if isinstance(items, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
