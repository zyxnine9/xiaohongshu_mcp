#!/usr/bin/env python3
"""Main entry - 运行社交媒体运营机器人."""
import asyncio
import argparse
from pathlib import Path

sys_path = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(sys_path))

from dotenv import load_dotenv
load_dotenv(sys_path / ".env")

from src.core.browser_manager import BrowserManager
from src.platforms.xiaohongshu import XiaohongshuPlatform


async def run_demo(platform_name: str, headless: bool = True) -> None:
    """运行演示：检查登录、获取 Feed、搜索."""
    data_dir = sys_path / "data"
    cookies_path = data_dir / "cookies" / f"{platform_name}.json"
    data_dir.mkdir(parents=True, exist_ok=True)

    browser = BrowserManager(
        headless=headless,
        cookies_path=cookies_path,
    )
    platform = XiaohongshuPlatform(browser, cookies_path=cookies_path)

    async with browser:
        # 1. 检查登录
        logged_in = await platform.check_login()
        print("登录状态:", "已登录" if logged_in else "未登录")
        if not logged_in:
            print("请先运行: python scripts/login.py --platform xiaohongshu")
            return

        # 2. 获取 Feed
        feeds = await platform.get_feeds(limit=5)
        print(f"\n获取到 {len(feeds)} 条 Feed:")
        for f in feeds:
            print(f"  - {f.id}: {f.title[:50] if f.title else '(无标题)'}...")

        # 3. 搜索
        results = await platform.search("美食", limit=3)
        print(f"\n搜索「美食」结果 {len(results)} 条:")
        for r in results:
            print(f"  - {r.id}: {r.title[:50] if r.title else '(无标题)'}...")


def main():
    parser = argparse.ArgumentParser(description="社交媒体运营机器人")
    parser.add_argument(
        "--platform",
        choices=["xiaohongshu"],
        default="xiaohongshu",
        help="平台",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="无头模式",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="显示浏览器窗口",
    )
    args = parser.parse_args()

    headless = args.headless and not args.no_headless
    asyncio.run(run_demo(args.platform, headless=headless))


if __name__ == "__main__":
    main()
