#!/usr/bin/env python3
"""小红书平台功能测试脚本 - 测试登录、搜索、评论读取."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.browser_manager import BrowserManager
from src.platforms.xiaohongshu import XiaohongshuPlatform


def _get_platform(headless: bool = True) -> tuple[BrowserManager, XiaohongshuPlatform]:
    """创建 BrowserManager 和 XiaohongshuPlatform 实例."""
    root = Path(__file__).resolve().parent.parent
    cookies_path = root / "data" / "cookies" / "xiaohongshu.json"
    browser = BrowserManager(headless=headless, cookies_path=cookies_path)
    platform = XiaohongshuPlatform(browser, cookies_path=cookies_path)
    return browser, platform


async def test_login_status(headless: bool = True) -> bool:
    """1. 测试是否已登录."""
    print("\n========== 测试 1: 登录状态 ==========")
    browser, platform = _get_platform(headless)
    try:
        async with browser:
            is_logged_in = await platform.check_login()
            if is_logged_in:
                print("✅ 已登录")
            else:
                print("❌ 未登录（请先运行 scripts/login.py 完成登录）")
            return is_logged_in
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_search_notes(keyword: str = "美食", limit: int = 5, headless: bool = True) -> bool:
    """2. 测试搜索笔记功能."""
    print(f"\n========== 测试 2: 搜索笔记 (关键词: {keyword}, 数量: {limit}) ==========")
    browser, platform = _get_platform(headless)
    try:
        async with browser:
            posts = await platform.search(keyword=keyword, limit=limit)
            if posts:
                print(f"✅ 搜索成功，共获取 {len(posts)} 条笔记:")
                for i, p in enumerate(posts, 1):
                    print(f"   {i}. [{p.id}] {p.title[:50]}{'...' if len(p.title) > 50 else ''}")
                return True
            else:
                print("⚠️ 未获取到笔记（可能未登录或页面结构变化）")
                return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_read_post_comments(
    post_id: str = "",
    xsec_token: str = "",
    headless: bool = True,
) -> bool:
    """3. 测试读取笔记评论功能.

    若未提供 post_id，会先搜索一条笔记再读取其评论。
    """
    print("\n========== 测试 3: 读取笔记评论 ==========")
    browser, platform = _get_platform(headless)
    try:
        async with browser:
            if not post_id:
                # 先搜索获取一条笔记
                posts = await platform.search(keyword="美食", limit=1)
                if not posts:
                    print("⚠️ 无法获取笔记（先确保已登录）")
                    return False
                post_id = posts[0].id
                xsec_token = posts[0].xsec_token
                print('xsec_token', xsec_token)
                print(f"   未指定笔记 ID，使用搜索到的: {post_id}")
            else:
                print(f"   使用指定的笔记 ID: {post_id}")

            post = await platform.get_post_detail(post_id, xsec_token)
            if not post:
                print("❌ 无法获取笔记详情")
                return False

            print(f"✅ 笔记详情: {post.title[:60]}...")
            print(f"   作者: {post.author}, 点赞: {post.likes}, 评论数: {post.comments_count}")

            comments = post.raw.get("comments", [])
            if comments:
                print(f"   评论列表 (前 {min(5, len(comments))} 条):")
                for i, c in enumerate(comments[:5], 1):
                    content = c.get("content", str(c))[:80]
                    print(f"   {i}. {content}{'...' if len(str(c.get('content', ''))) > 80 else ''}")
            else:
                print("   （暂无评论或评论结构已变化）")
            return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="小红书平台功能测试")
    parser.add_argument(
        "--test",
        choices=["login", "search", "comments", "all"],
        default="all",
        help="要运行的测试: login(登录), search(搜索), comments(评论), all(全部)",
    )
    parser.add_argument(
        "--keyword",
        default="美食",
        help="搜索关键词 (search/comments 测试用)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="搜索返回数量",
    )
    parser.add_argument(
        "-p", "--post-id",
        default="",
        help="指定笔记 ID，仅用于 comments 测试；不填则从搜索自动获取一条",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="显示浏览器窗口",
    )
    args = parser.parse_args()

    headless = not args.no_headless

    async def run():
        results = []
        if args.test in ("login", "all"):
            results.append(("登录状态", await test_login_status(headless)))
        if args.test in ("search", "all"):
            results.append(("搜索笔记", await test_search_notes(args.keyword, args.limit, headless)))
        if args.test in ("comments", "all"):
            results.append(("读取评论", await test_read_post_comments(args.post_id, "", headless)))

        print("\n========== 测试结果汇总 ==========")
        for name, ok in results:
            status = "✅ 通过" if ok else "❌ 失败"
            print(f"  {name}: {status}")
        return all(r[1] for r in results)

    success = asyncio.run(run())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
