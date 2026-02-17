"""发布流程 - 导航到创作者中心发布页，上传图文并提交."""
import asyncio
import logging
import os
import random
import time
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

from src.core.models import PublishContent

logger = logging.getLogger(__name__)

# 与 publish.go 一致：创作者中心发布页
PUBLISH_PAGE_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
PUBLISH_PAGE_TIMEOUT_MS = 300_000  # 300s
UPLOAD_COMPLETE_TIMEOUT_MS = 60_000  # 60s
TAB_DEADLINE_MS = 15_000  # 15s


async def init_publish_page(page: Page) -> bool:
    """导航到发布页并点击「上传图文」Tab。

    Returns:
        True 表示成功进入上传图文页，False 表示失败。
    """
    try:
        page.set_default_timeout(PUBLISH_PAGE_TIMEOUT_MS)
        await page.goto(
            PUBLISH_PAGE_URL,
            wait_until="domcontentloaded",
            timeout=PUBLISH_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_load_state("load", timeout=PUBLISH_PAGE_TIMEOUT_MS)
    except Exception as e:
        logger.warning("等待页面加载出现问题: %s，继续尝试", e)
    await asyncio.sleep(2)

    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception as e:
        logger.warning("等待 DOM 稳定出现问题: %s，继续尝试", e)
    await asyncio.sleep(1)

    if not await _must_click_publish_tab(page, "上传图文"):
        logger.error("点击上传图文 TAB 失败")
        return False
    await asyncio.sleep(1)
    return True


async def publish(page: Page, content: PublishContent, schedule_time: Optional[datetime] = None) -> bool:
    """执行发布：上传图片、填写标题/正文/标签，可选定时发布并提交。

    Args:
        page: Playwright 页面
        content: 标题、正文、图片路径、标签
        schedule_time: 定时发布时间，None 表示立即发布

    Returns:
        True 表示提交成功，False 表示失败。
    """
    if not content.images:
        logger.error("图片不能为空")
        return False

    if not await upload_images(page, content.images):
        logger.error("小红书上传图片失败")
        return False

    tags = content.tags[:10] if len(content.tags) >= 10 else content.tags
    if len(content.tags) >= 10:
        logger.warning("标签数量超过10，截取前10个标签")

    logger.info(
        "发布内容: title=%s, images=%s, tags=%s, schedule=%s",
        content.title,
        len(content.images),
        tags,
        schedule_time,
    )

    if not await _submit_publish(page, content.title, content.content, tags, schedule_time):
        logger.error("小红书发布失败")
        return False
    return True


# ---------- 弹窗与 Tab ----------


async def _remove_pop_cover(page: Page) -> None:
    """移除可能遮挡的弹窗（如 d-popover），并点击空白处."""
    try:
        if page.locator("div.d-popover").count() > 0:
            pop = page.locator("div.d-popover").first
            await pop.evaluate("el => el.remove()")
    except Exception:
        pass
    await _click_empty_position(page)


async def _click_empty_position(page: Page) -> None:
    x = 380 + random.randint(0, 99)
    y = 20 + random.randint(0, 59)
    await page.mouse.click(x, y)


async def _must_click_publish_tab(page: Page, tab_name: str) -> bool:
    """等待并点击指定名称的发布 Tab（如「上传图文」）."""
    try:
        await page.locator("div.upload-content").first.wait_for(state="visible", timeout=TAB_DEADLINE_MS)
    except Exception:
        return False

    deadline = time.monotonic() + (TAB_DEADLINE_MS / 1000.0)
    while time.monotonic() < deadline:
        tab_elem, blocked = await _get_tab_element(page, tab_name)
        if tab_elem is None:
            await asyncio.sleep(0.2)
            continue
        if blocked:
            logger.info("发布 TAB 被遮挡，尝试移除遮挡")
            await _remove_pop_cover(page)
            await asyncio.sleep(0.2)
            continue
        try:
            await tab_elem.click(button="left", click_count=1)
            return True
        except Exception as e:
            logger.warning("点击发布 TAB 失败: %s", e)
            await asyncio.sleep(0.2)
    logger.error("没有找到发布 TAB - %s", tab_name)
    return False


async def _get_tab_element(page: Page, tab_name: str) -> tuple[Optional[object], bool]:
    """获取指定文本的 creator-tab 元素及是否被遮挡。返回 (element_handle, blocked)."""
    elems = await page.query_selector_all("div.creator-tab")
    for elem in elems:
        try:
            if not await elem.is_visible():
                continue
            text = await elem.text_content()
            if text is None or text.strip() != tab_name:
                continue
            blocked = await _is_element_blocked(elem)
            return elem, blocked
        except Exception:
            continue
    return None, False


async def _is_element_blocked(elem) -> bool:
    """判断元素中心是否被其他元素遮挡."""
    try:
        result = await elem.evaluate("""el => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return true;
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;
            const target = document.elementFromPoint(x, y);
            return !(target === el || el.contains(target));
        }""")
        return bool(result)
    except Exception:
        return False


# ---------- 上传图片 ----------


async def upload_images(page: Page, image_paths: list[str]) -> bool:
    """逐张上传图片，每张等待预览出现再传下一张."""
    valid_paths: list[str] = []
    for path in image_paths:
        if not os.path.isfile(path):
            logger.warning("图片文件不存在: %s", path)
            continue
        valid_paths.append(path)
        logger.info("获取有效图片：%s", path)

    for i, path in enumerate(valid_paths):
        selector = ".upload-input" if i == 0 else 'input[type="file"]'
        upload_input = await page.query_selector(selector)
        if upload_input is None:
            logger.error("查找上传输入框失败(第%d张)", i + 1)
            return False
        try:
            await upload_input.set_input_files(path)
        except Exception as e:
            logger.error("上传第%d张图片失败: %s", i + 1, e)
            return False
        logger.info("图片已提交上传 index=%s path=%s", i + 1, path)
        if not await _wait_for_upload_complete(page, i + 1):
            logger.error("第%d张图片上传超时", i + 1)
            return False
        await asyncio.sleep(1)
    return True


async def _wait_for_upload_complete(page: Page, expected_count: int) -> bool:
    """等待预览区图片数量达到 expected_count，最多等 60 秒."""
    max_wait = UPLOAD_COMPLETE_TIMEOUT_MS / 1000.0
    interval = 0.5
    start = time.monotonic()
    while time.monotonic() - start < max_wait:
        try:
            previews = await page.query_selector_all(".img-preview-area .pr")
            current = len(previews)
            if current >= expected_count:
                logger.info("图片上传完成 count=%s", current)
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    return False


# ---------- 填写与提交 ----------


async def _submit_publish(
    page: Page,
    title: str,
    content: str,
    tags: list[str],
    schedule_time: Optional[datetime] = None,
) -> bool:
    """填写标题、正文、标签，可选定时发布并点击发布按钮."""
    title_input = await page.query_selector("div.d-input input")
    if title_input is None:
        logger.error("查找标题输入框失败")
        return False
    await title_input.fill(title)
    await asyncio.sleep(0.5)
    err = await _check_title_max_length(page)
    if err:
        logger.error("标题长度校验: %s", err)
        return False
    logger.info("检查标题长度：通过")
    await asyncio.sleep(1)

    content_elem = await _get_content_element(page)
    if content_elem is None:
        logger.error("没有找到内容输入框")
        return False
    await content_elem.fill(content)
    if not await _input_tags(content_elem, page, tags):
        logger.warning("部分标签输入异常，继续提交")
    await asyncio.sleep(1)
    err = await _check_content_max_length(page)
    if err:
        logger.error("正文长度校验: %s", err)
        return False
    logger.info("检查正文长度：通过")

    if schedule_time is not None:
        if not await _set_schedule_publish(page, schedule_time):
            logger.error("设置定时发布失败")
            return False
        logger.info("定时发布设置完成 schedule_time=%s", schedule_time.strftime("%Y-%m-%d %H:%M"))

    submit_btn = await page.query_selector(".publish-page-publish-btn button.bg-red")
    if submit_btn is None:
        logger.error("查找发布按钮失败")
        return False
    await submit_btn.click(button="left", click_count=1)
    await asyncio.sleep(3)
    return True


async def _check_title_max_length(page: Page) -> Optional[str]:
    """若标题超长，返回错误信息；否则返回 None."""
    elem = await page.query_selector("div.title-container div.max_suffix")
    if elem is None:
        return None
    try:
        text = await elem.text_content()
        return f"标题超长: {text}" if text else "标题超长"
    except Exception:
        return "标题超长"


async def _check_content_max_length(page: Page) -> Optional[str]:
    """若正文超长，返回错误信息；否则返回 None."""
    elem = await page.query_selector("div.edit-container div.length-error")
    if elem is None:
        return None
    try:
        text = await elem.text_content()
        return f"正文超长: {text}" if text else "正文超长"
    except Exception:
        return "正文超长"


async def _get_content_element(page: Page):
    """查找正文输入框：优先 div.ql-editor，否则按 placeholder「输入正文描述」找."""
    ql = await page.query_selector("div.ql-editor")
    if ql is not None:
        return ql
    return await _find_textbox_by_placeholder(page, "输入正文描述")


async def _find_textbox_by_placeholder(page: Page, placeholder_substr: str):
    """根据 placeholder 包含的文案找到 textbox 父元素."""
    p_elems = await page.query_selector_all("p")
    for p in p_elems:
        try:
            ph = await p.get_attribute("data-placeholder")
            if ph and placeholder_substr in ph:
                parent = await _find_textbox_parent(page, p)
                if parent is not None:
                    return parent
        except Exception:
            continue
    return None


async def _find_textbox_parent(page: Page, elem) -> Optional[object]:
    """向上查找 role=textbox 的父节点，最多 5 层."""
    current = elem
    for _ in range(5):
        try:
            parent = await current.evaluate_handle("el => el.parentElement")
            if parent is None:
                break
            role = await parent.evaluate("el => (el && el.getAttribute && el.getAttribute('role')) || null")
            if role == "textbox":
                return parent
            current = parent
        except Exception:
            break
    return None


async def _input_tags(content_elem, page: Page, tags: list[str]) -> bool:
    """在正文框中输入标签（# + 文案，并尝试点选联想项）."""
    if not tags:
        return True
    await asyncio.sleep(1)
    for _ in range(20):
        await content_elem.press("ArrowDown")
        await asyncio.sleep(0.01)
    await content_elem.press("Enter")
    await content_elem.press("Enter")
    await asyncio.sleep(1)
    for tag in tags:
        tag = tag.lstrip("#")
        await content_elem.type("#", delay=50)
        await asyncio.sleep(0.2)
        await content_elem.type(tag, delay=50)
        await asyncio.sleep(1)
        topic = await page.query_selector("#creator-editor-topic-container .item")
        if topic is not None:
            try:
                await topic.click(button="left", click_count=1)
                logger.info("成功点击标签联想选项 tag=%s", tag)
            except Exception:
                await content_elem.type(" ", delay=50)
        else:
            await content_elem.type(" ", delay=50)
        await asyncio.sleep(0.5)
    return True


async def _set_schedule_publish(page: Page, t: datetime) -> bool:
    """点击定时发布开关并设置日期时间."""
    switch_elem = await page.query_selector(".post-time-wrapper .d-switch")
    if switch_elem is None:
        logger.error("查找定时发布开关失败")
        return False
    await switch_elem.click(button="left", click_count=1)
    await asyncio.sleep(0.8)
    date_input = await page.query_selector(".date-picker-container input")
    if date_input is None:
        logger.error("查找日期时间输入框失败")
        return False
    dt_str = t.strftime("%Y-%m-%d %H:%M")
    await date_input.fill(dt_str)
    logger.info("已设置日期时间 datetime=%s", dt_str)
    await asyncio.sleep(0.5)
    return True
