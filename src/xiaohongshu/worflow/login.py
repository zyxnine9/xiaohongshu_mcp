"""登录流程 - 检查登录、获取二维码、等待登录完成."""
import asyncio
import time
from typing import Optional

from playwright.async_api import Page

# 登录状态判断的选择器
LOGIN_STATUS_SELECTOR = ".main-container .user .link-wrapper .channel"

# 二维码弹窗选择器
QRCODE_IMG_SELECTOR = ".login-container .qrcode-img"


async def check_login(page: Page) -> bool:
    """检查用户是否已登录。"""
    try:
        await page.goto(
            "https://www.xiaohongshu.com/explore",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        await asyncio.sleep(1)
        elem = await page.query_selector(LOGIN_STATUS_SELECTOR)
        return elem is not None
    except Exception:
        return False


async def fetch_qrcode(page: Page) -> tuple[Optional[str], bool]:
    """获取二维码图片 src。

    Returns:
        (qrcode_src, already_logged_in)
        - 已登录: ("", True)
        - 需登录: (img_src, False)
    """
    try:
        if await page.query_selector(LOGIN_STATUS_SELECTOR):
            return "", True

        qr_elem = await page.query_selector(QRCODE_IMG_SELECTOR)
        if not qr_elem:
            return None, False
        src = await qr_elem.get_attribute("src")
        if not src or not src.strip():
            return None, False
        return src.strip(), False
    except Exception:
        return None, False


def print_qrcode_in_terminal(src: str) -> None:
    """在终端解码并打印可扫描的二维码。"""
    try:
        import base64
        from io import BytesIO

        if src.startswith("data:"):
            parts = src.split(",", 1)
            if len(parts) != 2:
                return
            img_data = base64.b64decode(parts[1])
        else:
            print("二维码已显示在浏览器中，请扫码登录。")
            return

        try:
            import os
            os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'
            from pyzbar.pyzbar import decode
            from PIL import Image

            img = Image.open(BytesIO(img_data))
            decoded = decode(img)
            if not decoded:
                print("无法解析二维码，请使用浏览器中的二维码扫码登录。")
                return
            qr_content = decoded[0].data.decode("utf-8", errors="ignore")
        except ImportError:
            print("提示: 安装 pyzbar 和 Pillow 可在终端显示二维码 (pip install pyzbar Pillow)")
            print("二维码已显示在浏览器中，请扫码登录。")
            return

        try:
            import qrcode

            qr = qrcode.QRCode(border=1, box_size=1)
            qr.add_data(qr_content)
            qr.make()
            qr.print_ascii(invert=True)
            print("请使用小红书 APP 扫描上方二维码完成登录。")
        except ImportError:
            print("提示: 安装 qrcode 可在终端显示二维码 (pip install qrcode)")
            print("登录链接:", qr_content[:80] + "..." if len(qr_content) > 80 else qr_content)
            print("请使用浏览器中的二维码或复制链接到手机打开。")
    except Exception:
        print("请在打开的浏览器窗口中扫码登录。")


async def wait_for_login(
    page: Page,
    timeout_sec: float = 120,
    poll_interval_sec: float = 0.5,
) -> bool:
    """轮询等待登录成功。"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        elem = await page.query_selector(LOGIN_STATUS_SELECTOR)
        if elem is not None:
            return True
        await asyncio.sleep(poll_interval_sec)
    return False
