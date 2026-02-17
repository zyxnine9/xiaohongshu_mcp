#!/usr/bin/env python3
"""简单脚本：测试 XiaohongshuPlatform 的 get_feeds 和 search，跑通即可."""
import asyncio
import sys
from pathlib import Path

# 把项目根目录加入 path，才能 import src
_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_root))

from src.core.browser_manager import BrowserManager
from src.core.models import PublishContent
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
                print("  xsec_token:", p.xsec_token)
                print("  post_id:", p.id)
                print("  author id", p.author_id)
        except Exception as e:
            print("search 出错:", e)
    print("search 跑完.\n")


async def test_get_post_detail(
    headless: bool = False,
    post_id: str = "",
    xsec_token: str = "",
    load_all_comments: bool = False,
) -> None:
    """测试 get_post_detail：直接传入 post_id 和 xsec_token 拉详情."""
    if not post_id or not xsec_token:
        print("请提供 --post-id 和 --xsec-token，跳过 get_post_detail")
        return
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== get_post_detail(post_id=%s, load_all_comments=%s) ===" % (post_id, load_all_comments))
        try:
            post = await platform.get_post_detail(
                post_id, xsec_token, load_all_comments=load_all_comments
            )
            if post:
                print("详情: title=%s | 作者=%s | 赞=%s | 评论数=%s" % (
                    (post.title or "(无标题)")[:50], post.author, post.likes, post.comments_count
                ))
                if post.content:
                    print("  content 前 80 字:", (post.content or "")[:80])
            else:
                print("get_post_detail 返回 None")
        except Exception as e:
            print("get_post_detail 出错:", e)
    print("get_post_detail 跑完.\n")


async def test_comment(
    headless: bool = False,
    post_id: str = "",
    xsec_token: str = "",
    content: str = "测试评论，请忽略",
) -> None:
    """测试 comment：发表评论到指定笔记."""
    if not post_id or not xsec_token:
        print("请提供 --post-id 和 --xsec-token，跳过 comment")
        return
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== comment(post_id=%s, content=%r) ===" % (post_id, content))
        try:
            ok = await platform.comment(post_id, content, xsec_token=xsec_token)
            print("comment 结果: %s" % ("成功" if ok else "失败"))
        except Exception as e:
            print("comment 出错:", e)
    print("comment 跑完.\n")


async def test_reply(
    headless: bool = False,
    post_id: str = "",
    xsec_token: str = "",
    comment_id: str = "",
    content: str = "测试回复，请忽略",
) -> None:
    """测试 reply：回复指定评论."""
    if not post_id or not xsec_token or not comment_id:
        print("请提供 --post-id、--xsec-token 和 --comment-id，跳过 reply")
        return
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== reply(post_id=%s, comment_id=%s, content=%r) ===" % (post_id, comment_id, content))
        try:
            ok = await platform.reply(post_id, comment_id, content, xsec_token=xsec_token)
            print("reply 结果: %s" % ("成功" if ok else "失败"))
        except Exception as e:
            print("reply 出错:", e)
    print("reply 跑完.\n")


async def test_get_user_profile(
    headless: bool = False,
    user_id: str = "",
    xsec_token: str = "",
) -> None:
    """测试 get_user_profile：获取用户主页信息，需要 user_id 和 xsec_token（可从 search 结果中的 author 对应帖子获取）."""
    if not user_id or not xsec_token:
        print("请提供 --user-id 和 --xsec-token，跳过 get_user_profile")
        return
    browser, platform = _make_platform(headless)
    async with browser:
        print("=== get_user_profile(user_id=%s) ===" % user_id)
        try:
            profile = await platform.get_user_profile(user_id, xsec_token=xsec_token)
            if profile:
                print("用户: nickname=%s | bio=%s | 粉丝=%s | 关注=%s | 获赞=%s" % (
                    profile.nickname,
                    (profile.bio or "")[:50],
                    profile.followers,
                    profile.following,
                    profile.likes_count,
                ))
            else:
                print("get_user_profile 返回 None")
        except Exception as e:
            print("get_user_profile 出错:", e)
    print("get_user_profile 跑完.\n")


async def test_publish(
    headless: bool = False,
    title: str = "测试发布",
    content: str = "这是一条测试笔记，请忽略",
    images: list[str] | None = None,
    tags: list[str] | None = None,
) -> None:
    """测试 publish：发布图文笔记."""
    images = images or []
    tags = tags or ["测试"]
    if not images:
        print("请提供 --images（至少一张图片路径），跳过 publish")
        return
    browser, platform = _make_platform(headless)
    async with browser:
        pub = PublishContent(title=title, content=content, images=images, tags=tags)
        print("=== publish(title=%r, images=%s) ===" % (title, images))
        try:
            result = await platform.publish(pub)
            print("publish 结果: %s" % (result if result else "失败"))
        except Exception as e:
            print("publish 出错:", e)
    print("publish 跑完.\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test",
        choices=["get_feeds", "search", "get_post_detail", "get_user_profile", "comment", "reply", "publish"],
        default=None,
        help="只跑 get_feeds / search / get_post_detail / get_user_profile / comment / reply / publish；不传则全跑",
    )
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--limit", type=int, default=5, help="条数，默认 5")
    parser.add_argument("--keyword", type=str, default="美食", help="search 关键词，默认 美食")
    parser.add_argument("--post-id", type=str, default="", help="get_post_detail / comment / reply 用的笔记 id")
    parser.add_argument("--xsec-token", type=str, default="", help="get_post_detail / get_user_profile / comment / reply 用的 xsec_token")
    parser.add_argument("--user-id", type=str, default="", help="get_user_profile 用的用户 id")
    parser.add_argument(
        "--load-all-comments",
        action="store_true",
        help="get_post_detail 时是否滚动加载全部评论（较慢）",
    )
    parser.add_argument("--comment-id", type=str, default="", help="reply 用的目标评论 id")
    parser.add_argument("--content", type=str, default="测试评论，请忽略", help="comment / reply 用的内容")
    parser.add_argument(
        "--images",
        type=str,
        nargs="+",
        default=[],
        help="publish 用的图片路径列表，如 --images /path/to/img1.jpg /path/to/img2.png",
    )
    parser.add_argument("--title", type=str, default="测试发布", help="publish 用的标题")
    args = parser.parse_args()

    async def run():
        if args.test is None or args.test == "get_feeds":
            await test_get_feeds(headless=args.headless, limit=args.limit)
        if args.test is None or args.test == "search":
            await test_search(headless=args.headless, keyword=args.keyword, limit=args.limit)
        if args.test is None or args.test == "get_post_detail":
            await test_get_post_detail(
                headless=args.headless,
                post_id=args.post_id,
                xsec_token=args.xsec_token,
                load_all_comments=args.load_all_comments,
            )
        if args.test is None or args.test == "get_user_profile":
            await test_get_user_profile(
                headless=args.headless,
                user_id=args.user_id,
                xsec_token=args.xsec_token,
            )
        if args.test is None or args.test == "comment":
            await test_comment(
                headless=args.headless,
                post_id=args.post_id,
                xsec_token=args.xsec_token,
                content=args.content,
            )
        if args.test is None or args.test == "reply":
            await test_reply(
                headless=args.headless,
                post_id=args.post_id,
                xsec_token=args.xsec_token,
                comment_id=args.comment_id,
                content=args.content,
            )
        if args.test is None or args.test == "publish":
            await test_publish(
                headless=args.headless,
                title=args.title,
                content=args.content,
                images=args.images,
            )

    asyncio.run(run())
