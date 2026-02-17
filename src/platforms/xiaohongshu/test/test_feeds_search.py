#!/usr/bin/env python3
"""简单脚本：测试 XiaohongshuPlatform 的 get_feeds 和 search，跑通即可."""
import asyncio
import sys
from pathlib import Path

# 把项目根目录加入 path，才能 import src
_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_root))

from src.core.browser_manager import BrowserManager
from src.platforms.xiaohongshu import XiaohongshuPlatform


def _make_platform(headless: bool):
    """创建 browser + platform，调用方负责 async with browser."""
    data_dir = _root / "data"
    cookies_path = data_dir / "cookies" / "xiaohongshu.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    browser = BrowserManager(headless=headless, cookies_path=cookies_path)
    platform = XiaohongshuPlatform(browser, cookies_path=cookies_path)
    return browser, platform


async def test_get_feeds(headless: bool = False, limit: int = 5) -> None:
    """只测试 get_feeds."""
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== get_feeds(limit=%d) ===" % limit)
        try:
            feeds = await platform.get_feeds(limit=limit)
            print("拿到 %d 条 feed" % len(feeds))
            for i, p in enumerate(feeds, 1):
                print("  [%d] %s | 作者:%s | 赞:%s" % (i, p.title or "(无标题)", p.author, p.likes))
        except Exception as e:
            print("get_feeds 出错:", e)
    print("get_feeds 跑完.\n")


async def test_search(headless: bool = False, keyword: str = "美食", limit: int = 5) -> None:
    """只测试 search."""
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== search(%r, limit=%d) ===" % (keyword, limit))
        try:
            results = await platform.search(keyword, limit=limit)
            print("搜索到 %d 条" % len(results))
            for i, p in enumerate(results, 1):
                print("  [%d] %s | 作者:%s | 赞:%s" % (i, p.title or "(无标题)", p.author, p.likes))
                print("Xtoekn", p.xsec_token)
        except Exception as e:
            print("search 出错:", e)
    print("search 跑完.\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["get_feeds", "search"], default=None,
                        help="只跑 get_feeds 或 search；不传则两个都跑")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--limit", type=int, default=5, help="条数，默认 5")
    parser.add_argument("--keyword", type=str, default="美食", help="search 关键词，默认 美食")
    args = parser.parse_args()

    async def run():
        if args.test is None or args.test == "get_feeds":
            await test_get_feeds(headless=args.headless, limit=args.limit)
        if args.test is None or args.test == "search":
            await test_search(headless=args.headless, keyword=args.keyword, limit=args.limit)

    asyncio.run(run())
