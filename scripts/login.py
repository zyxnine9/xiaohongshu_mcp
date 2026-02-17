#!/usr/bin/env python3
"""Login script - 手动登录并保存 cookies."""
import asyncio
import argparse
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.browser_manager import BrowserManager
from src.platforms.xiaohongshu import XiaohongshuPlatform


async def login_xiaohongshu(headless: bool = False) -> None:
    """Open Xiaohongshu login page, wait for manual login, save cookies."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    cookies_path = data_dir / "cookies" / "xiaohongshu.json"
    data_dir.mkdir(parents=True, exist_ok=True)

    browser = BrowserManager(
        headless=headless,
        cookies_path=cookies_path,
    )
    platform = XiaohongshuPlatform(browser, cookies_path=cookies_path)

    async with browser:
        print("正在打开小红书首页... 未登录时将显示二维码，请扫码完成登录。")
        success = await platform.login(headless=headless)
        if success:
            print("登录成功！Cookies 已保存到:", cookies_path)
        else:
            print("登录超时或失败，请重试。")


def main():
    parser = argparse.ArgumentParser(description="社交媒体平台登录")
    parser.add_argument(
        "--platform",
        choices=["xiaohongshu"],
        default="xiaohongshu",
        help="要登录的平台",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式（登录建议不用，保持有界面）",
    )
    args = parser.parse_args()

    if args.platform == "xiaohongshu":
        asyncio.run(login_xiaohongshu(headless=args.headless))
    else:
        print("暂不支持该平台")


if __name__ == "__main__":
    main()
