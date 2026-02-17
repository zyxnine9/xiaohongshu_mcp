"""发布图文流程 - 创作者中心上传图文并发布.

参考: https://github.com/xpzouying/xiaohongshu-mcp/blob/main/xiaohongshu/publish.go
"""
import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

URL_OF_PUBLISH = "https://creator.xiaohongshu.com/publish/publish?source=official"
PUBLISH_PAGE_TIMEOUT_MS = 300_000  # 5 min
UPLOAD_WAIT_TIMEOUT_MS = 60_000   # 单张图片上传最多等 60s
TAB_NAME_IMAGE = "上传图文"
MAX_TAGS = 10


async def _remove_pop_cover(page: Page) -> None:
    """移除可能遮挡的弹窗封面."""
    try:
        pop = await page.query_selector("div.d-popover")
        if pop:
            await pop.evaluate("el => el.remove()")
    except Exception:
        pass
    x = 380 + random.randint(0, 99)
    y = 20 + random.randint(0, 59)
    await page.mouse.move(x, y)
    await page.mouse.click(x, y)


async def _element_visible(elem) -> bool:
    """检查元素是否可见（无隐藏样式且 visible）."""
    if not elem:
        return False
    try:
        style = await elem.get_attribute("style")
        if style and (
            "left: -9999px" in style
            or "top: -9999px" in style
            or "display: none" in style
            or "visibility: hidden" in style
        ):
            return False
        return await elem.is_visible()
    except Exception:
        return True


async def _is_element_blocked(page: Page, elem) -> bool:
    """元素中心点是否被其他元素遮挡."""
    try:
        return await elem.evaluate("""el => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return true;
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;
            const target = document.elementFromPoint(x, y);
            return !(target === el || el.contains(target));
        }""")
    except Exception:
        return False


async def _click_publish_tab(page: Page, tab_name: str) -> None:
    """点击发布类型 TAB（如「上传图文」）."""
    await page.wait_for_selector("div.upload-content", state="visible", timeout=15000)
    deadline = asyncio.get_event_loop().time() + 15
    while asyncio.get_event_loop().time() < deadline:
        tabs = await page.query_selector_all("div.creator-tab")
        for tab in tabs:
            if not await _element_visible(tab):
                continue
            try:
                text = await tab.text_content()
                if not text or text.strip() != tab_name:
                    continue
            except Exception:
                continue
            blocked = await _is_element_blocked(page, tab)
            if blocked:
                logger.info("发布 TAB 被遮挡，尝试移除遮挡")
                await _remove_pop_cover(page)
                await asyncio.sleep(0.2)
                break
            try:
                await tab.click(button="left", click_count=1)
                return
            except Exception as e:
                logger.warning("点击发布 TAB 失败: %s", e)
                await asyncio.sleep(0.2)
                break
        await asyncio.sleep(0.2)
    raise RuntimeError(f"没有找到发布 TAB - {tab_name}")


async def _wait_upload_complete(page: Page, expected_count: int) -> None:
    """等待已上传图片数量达到 expected_count."""
    max_wait = 60.0
    interval = 0.5
    start = asyncio.get_event_loop().time()
    last_log = expected_count - 1
    while asyncio.get_event_loop().time() - start < max_wait:
        elems = await page.query_selector_all(".img-preview-area .pr")
        current = len(elems)
        if current != last_log:
            logger.info("等待图片上传 current=%s expected=%s", current, expected_count)
            last_log = current
        if current >= expected_count:
            logger.info("图片上传完成 count=%s", current)
            return
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"第 {expected_count} 张图片上传超时(60s)，请检查网络连接和图片大小"
    )


async def _upload_images(page: Page, image_paths: list[str]) -> None:
    """逐张上传图片."""
    valid_paths: list[str] = []
    for path in image_paths:
        if not Path(path).exists():
            logger.warning("图片文件不存在: %s", path)
            continue
        valid_paths.append(path)
        logger.info("获取有效图片: %s", path)
    if not valid_paths:
        raise ValueError("没有有效的图片路径")

    for i, path in enumerate(valid_paths):
        selector = ".upload-input" if i == 0 else 'input[type="file"]'
        upload_input = await page.wait_for_selector(
            selector, state="attached", timeout=10000
        )
        if not upload_input:
            raise RuntimeError(f"查找上传输入框失败(第{i+1}张)")
        await upload_input.set_input_files(path)
        logger.info("图片已提交上传 index=%s path=%s", i + 1, path)
        await _wait_upload_complete(page, i + 1)
        await asyncio.sleep(1)


async def _get_content_element(page: Page):
    """查找正文输入框：优先 ql-editor，否则按 placeholder 找 role=textbox 父元素."""
    ql = await page.query_selector("div.ql-editor")
    if ql:
        return ql
    handle = await page.evaluate_handle("""() => {
        const ps = document.querySelectorAll('p[data-placeholder]');
        for (const p of ps) {
            if ((p.getAttribute('data-placeholder') || '').includes('输入正文描述')) {
                let cur = p.parentElement;
                for (let i = 0; i < 5 && cur; i++) {
                    if (cur.getAttribute('role') === 'textbox') return cur;
                    cur = cur.parentElement;
                }
                break;
            }
        }
        return null;
    }""")
    try:
        if await handle.evaluate("el => el !== null"):
            return handle.as_element()
    except Exception as e:
        print(e)
    return None


async def _input_tag(content_elem, tag: str, page: Page) -> None:
    """在正文区域追加输入一个标签并选择联想第一项（不清空已有内容）."""
    tag = tag.lstrip("#")
    await content_elem.focus()
    await page.keyboard.type("#", delay=50)
    await asyncio.sleep(0.2)
    await page.keyboard.type(tag, delay=50)
    await asyncio.sleep(1)
    topic = await page.query_selector("#creator-editor-topic-container .item")
    if topic:
        await topic.click()
        logger.info("成功点击标签联想选项 tag=%s", tag)
        await asyncio.sleep(0.2)
    else:
        logger.warning("未找到标签联想选项，直接输入空格 tag=%s", tag)
        await page.keyboard.press(" ")


async def _input_tags(page: Page, content_elem, tags: list[str]) -> None:
    """在正文末尾输入多个标签（先聚焦、移动到底部、换行，再逐个输入 #tag）."""
    if not tags:
        return
    await asyncio.sleep(1)
    await content_elem.click()
    # 移动到底部：End 或 Ctrl+End，再换两行
    await page.keyboard.press("End")
    await page.keyboard.press("Enter")
    await page.keyboard.press("Enter")
    await asyncio.sleep(1)
    for tag in tags:
        await _input_tag(content_elem, tag, page)
        await asyncio.sleep(0.5)


async def _check_title_max_length(page: Page) -> Optional[str]:
    """若标题超长返回错误信息."""
    suffix = await page.query_selector("div.title-container div.max_suffix")
    if not suffix:
        return None
    try:
        text = await suffix.text_content()
        if text:
            parts = text.strip().split("/")
            if len(parts) == 2:
                return f"当前输入长度为{parts[0]}，最大长度为{parts[1]}"
        return f"长度超过限制: {text}"
    except Exception:
        return "标题超过最大长度"


async def _check_content_max_length(page: Page) -> Optional[str]:
    """若正文超长返回错误信息."""
    err_elem = await page.query_selector("div.edit-container div.length-error")
    if not err_elem:
        return None
    try:
        text = await err_elem.text_content()
        if text:
            parts = text.strip().split("/")
            if len(parts) == 2:
                return f"当前输入长度为{parts[0]}，最大长度为{parts[1]}"
        return f"长度超过限制: {text}"
    except Exception:
        return "正文超过最大长度"


async def _set_schedule_publish(page: Page, schedule_time: datetime) -> None:
    """设置定时发布时间."""
    switch_elem = await page.query_selector(".post-time-wrapper .d-switch")
    if not switch_elem:
        raise RuntimeError("查找定时发布开关失败")
    await switch_elem.click()
    await asyncio.sleep(0.8)
    dt_str = schedule_time.strftime("%Y-%m-%d %H:%M")
    inp = await page.query_selector(".date-picker-container input")
    if not inp:
        raise RuntimeError("查找日期时间输入框失败")
    await inp.fill(dt_str)
    logger.info("已设置日期时间 datetime=%s", dt_str)


async def _submit_publish(
    page: Page,
    title: str,
    content: str,
    tags: list[str],
    schedule_time: Optional[datetime],
) -> None:
    """填写标题、正文、标签并点击发布."""
    title_input = await page.wait_for_selector(
        "div.d-input input", state="visible", timeout=10000
    )
    if not title_input:
        raise RuntimeError("查找标题输入框失败")
    await title_input.fill(title)
    await asyncio.sleep(0.5)
    err = await _check_title_max_length(page)
    if err:
        raise ValueError(err)
    logger.info("检查标题长度：通过")
    await asyncio.sleep(1)

    content_elem = await _get_content_element(page)
    if not content_elem:
        raise RuntimeError("没有找到内容输入框")
    await content_elem.fill(content)
    await _input_tags(page, content_elem, tags)
    await asyncio.sleep(1)
    err = await _check_content_max_length(page)
    if err:
        raise ValueError(err)
    logger.info("检查正文长度：通过")

    if schedule_time is not None:
        await _set_schedule_publish(page, schedule_time)
        logger.info("定时发布设置完成 schedule_time=%s", schedule_time.strftime("%Y-%m-%d %H:%M"))

    submit_btn = await page.query_selector(".publish-page-publish-btn button.bg-red")
    if not submit_btn:
        raise RuntimeError("查找发布按钮失败")
    await submit_btn.click()
    await asyncio.sleep(3)


async def publish_image(
    page: Page,
    title: str,
    content: str,
    image_paths: list[str],
    tags: list[str],
    schedule_time: Optional[datetime] = None,
) -> None:
    """在创作者中心发布图文笔记.

    流程：打开发布页 -> 点击「上传图文」-> 上传图片 -> 填写标题/正文/标签 -> 可选定时 -> 点击发布.

    Args:
        page: Playwright 页面（已登录创作者账号）.
        title: 笔记标题.
        content: 正文描述.
        image_paths: 本地图片路径列表，至少一张.
        tags: 标签列表（会加 #），最多 10 个.
        schedule_time: 定时发布时间，None 表示立即发布.

    Raises:
        ValueError: 无有效图片或标题/正文超长.
        TimeoutError: 上传或等待超时.
        RuntimeError: 页面元素找不到或操作失败.
    """
    if not image_paths:
        raise ValueError("图片不能为空")

    page.set_default_timeout(PUBLISH_PAGE_TIMEOUT_MS)

    await page.goto(URL_OF_PUBLISH, wait_until="domcontentloaded", timeout=PUBLISH_PAGE_TIMEOUT_MS)
    try:
        await page.wait_for_load_state("load", timeout=PUBLISH_PAGE_TIMEOUT_MS)
    except Exception as e:
        logger.warning("等待页面 load 出现问题: %s，继续尝试", e)
    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as e:
        logger.warning("等待 networkidle 出现问题: %s，继续尝试", e)
    await asyncio.sleep(1)

    await _click_publish_tab(page, TAB_NAME_IMAGE)
    await asyncio.sleep(1)

    await _upload_images(page, image_paths)

    tags = tags[:MAX_TAGS] if len(tags) > MAX_TAGS else tags
    logger.info(
        "发布内容: title=%s images=%s tags=%s schedule=%s",
        title, len(image_paths), tags, schedule_time,
    )

    await _submit_publish(page, title, content, tags, schedule_time)
    logger.info("发布流程已完成")


async def publish_image_from_content(
    page: Page,
    title: str,
    content: str,
    images: list[str],
    tags: list[str],
    schedule_time: Optional[datetime] = None,
) -> None:
    """基于 PublishContent 字段发布图文.

    images 为本地文件路径列表；若非路径或不存在会跳过并至少保留一张有效路径.
    """
    valid_paths = [p for p in images if Path(p).exists()]
    if not valid_paths:
        raise ValueError("图片不能为空：没有有效的本地图片路径")
    await publish_image(
        page,
        title=title,
        content=content,
        image_paths=valid_paths,
        tags=tags,
        schedule_time=schedule_time,
    )
