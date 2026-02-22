"""搜索流程 - 从搜索页 __INITIAL_STATE__.search.feeds 拉取搜索结果.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/12fcfe109b198108b4e1c26cefdf296ebca5991e/xiaohongshu/search.go
"""
import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import Page

# 与 search.go 一致：超时 60s
SEARCH_PAGE_TIMEOUT_MS = 60_000


def make_search_url(keyword: str) -> str:
    """构造小红书搜索页 URL，与 Go makeSearchURL 一致."""
    params = {"keyword": keyword, "source": "web_explore_feed"}
    return f"https://www.xiaohongshu.com/search_result?{urlencode(params)}"


async def get_search_feeds_list(
    page: Page,
    keyword: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """从搜索页的 window.__INITIAL_STATE__.search.feeds 获取搜索结果列表。

    与 search.go Search 一致：先导航到搜索 URL，等待页面稳定与 __INITIAL_STATE__，
    再执行取值逻辑 feeds.value ?? feeds._value，返回解析后的 list[dict]。
    暂不实现筛选面板（FilterOption），仅按关键词搜索。

    Args:
        page: Playwright 页面。
        keyword: 搜索关键词。
        limit: 最多返回条数，默认 20。

    Returns:
        原始 Feed 项列表（每项为 dict），无数据或出错时返回空列表。
    """
    search_url = make_search_url(keyword)
    try:
        await page.goto(
            search_url,
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
                window.__INITIAL_STATE__.search &&
                window.__INITIAL_STATE__.search.feeds) {
                const feeds = window.__INITIAL_STATE__.search.feeds;
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
        if not isinstance(items, list):
            return []
        return items[:limit]
    except (json.JSONDecodeError, TypeError):
        return []
