"""用户资料流程 - 从用户主页 __INITIAL_STATE__ 拉取用户信息及帖子列表.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/12fcfe109b198108b4e1c26cefdf296ebca5991e/xiaohongshu/user_profile.go
"""
import asyncio
import json
from typing import Any, Optional

from playwright.async_api import Page

# 与 user_profile.go 一致：超时 60s
USER_PROFILE_PAGE_TIMEOUT_MS = 60_000

# 侧边栏「我」入口选择器（与 navigate.go ToProfilePage 一致）
SIDEBAR_PROFILE_SELECTOR = "div.main-container li.user.side-bar-component a.link-wrapper span.channel"


def make_user_profile_url(user_id: str, xsec_token: str) -> str:
    """构造用户主页 URL，与 Go makeUserProfileURL 一致."""
    return (
        f"https://www.xiaohongshu.com/user/profile/{user_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_note"
    )


async def _extract_user_profile_data(page: Page) -> Optional[dict[str, Any]]:
    """从当前页面的 __INITIAL_STATE__ 提取用户资料与帖子（与 Go extractUserProfileData 一致）.

    读取 user.userPageData (basicInfo + interactions) 与 user.notes (双重数组 Feed)，
    展平 notes 后返回 { basic_info, interactions, feeds }。
    """
    try:
        await page.wait_for_function(
            "() => window.__INITIAL_STATE__ !== undefined",
            timeout=USER_PROFILE_PAGE_TIMEOUT_MS,
        )
    except (TimeoutError, RuntimeError):
        return None

    # 1. userPageData: basicInfo + interactions
    user_data_result: Optional[str] = None
    try:
        user_data_result = await page.evaluate("""() => {
            if (window.__INITIAL_STATE__ &&
                window.__INITIAL_STATE__.user &&
                window.__INITIAL_STATE__.user.userPageData) {
                const userPageData = window.__INITIAL_STATE__.user.userPageData;
                const data = userPageData.value !== undefined ? userPageData.value : userPageData._value;
                if (data) {
                    return JSON.stringify(data);
                }
            }
            return "";
        }""")
    except (TimeoutError, RuntimeError):
        return None

    if not user_data_result or not isinstance(user_data_result, str) or user_data_result == "":
        return None

    # 2. notes: 用户帖子（双重数组）
    notes_result: Optional[str] = None
    try:
        notes_result = await page.evaluate("""() => {
            if (window.__INITIAL_STATE__ &&
                window.__INITIAL_STATE__.user &&
                window.__INITIAL_STATE__.user.notes) {
                const notes = window.__INITIAL_STATE__.user.notes;
                const data = notes.value !== undefined ? notes.value : notes._value;
                if (data) {
                    return JSON.stringify(data);
                }
            }
            return "";
        }""")
    except (TimeoutError, RuntimeError):
        return None

    if not notes_result or not isinstance(notes_result, str) or notes_result == "":
        return None

    try:
        user_page_data = json.loads(user_data_result)
        notes_feeds = json.loads(notes_result)
    except (json.JSONDecodeError, TypeError):
        return None

    # basicInfo + interactions 来自 userPageData
    basic_info = user_page_data.get("basicInfo") or {}
    interactions = user_page_data.get("interactions") or []

    # 展平 notes 双重数组
    feeds: list[dict[str, Any]] = []
    if isinstance(notes_feeds, list):
        for item in notes_feeds:
            if isinstance(item, list):
                feeds.extend(item)
            elif isinstance(item, dict):
                feeds.append(item)

    return {
        "basic_info": basic_info,
        "interactions": interactions,
        "feeds": feeds,
    }


async def user_profile(
    page: Page,
    user_id: str,
    xsec_token: str,
) -> Optional[dict[str, Any]]:
    """打开指定用户主页并拉取用户信息及帖子（与 Go UserProfile 一致）.

    Args:
        page: Playwright 页面。
        user_id: 用户 ID。
        xsec_token: 访问令牌（可从 Feed/搜索等接口获取）。

    Returns:
        包含 basic_info、interactions、feeds 的字典；失败返回 None。
    """
    url = make_user_profile_url(user_id, xsec_token)
    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=USER_PROFILE_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_load_state("networkidle", timeout=USER_PROFILE_PAGE_TIMEOUT_MS)
    except (TimeoutError, RuntimeError):
        return None

    await asyncio.sleep(1)
    return await _extract_user_profile_data(page)


async def get_my_profile_via_sidebar(page: Page) -> Optional[dict[str, Any]]:
    """通过侧边栏进入「我的」主页并拉取当前登录用户资料（与 Go GetMyProfileViaSidebar 一致）.

    先进入 explore，点击侧边栏「我」入口，等待页面稳定后从 __INITIAL_STATE__ 提取数据。

    Args:
        page: Playwright 页面（需已登录）。

    Returns:
        包含 basic_info、interactions、feeds 的字典；失败返回 None。
    """
    try:
        await page.goto(
            "https://www.xiaohongshu.com/explore",
            wait_until="domcontentloaded",
            timeout=USER_PROFILE_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_load_state("networkidle", timeout=USER_PROFILE_PAGE_TIMEOUT_MS)
    except (TimeoutError, RuntimeError):
        return None

    await asyncio.sleep(1)

    # 点击侧边栏「我」
    try:
        profile_link = await page.wait_for_selector(
            SIDEBAR_PROFILE_SELECTOR,
            timeout=USER_PROFILE_PAGE_TIMEOUT_MS,
        )
        if profile_link:
            await profile_link.click()
        else:
            return None
    except (TimeoutError, RuntimeError):
        return None

    await page.wait_for_load_state("networkidle", timeout=USER_PROFILE_PAGE_TIMEOUT_MS)
    await asyncio.sleep(1)

    return await _extract_user_profile_data(page)
