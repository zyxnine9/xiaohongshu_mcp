"""Xiaohongshu URLs and constants."""
BASE_URL = "https://www.xiaohongshu.com"
EXPLORE_URL = f"{BASE_URL}/explore"
SEARCH_URL = f"{BASE_URL}/search_result"
PUBLISH_URL = f"{BASE_URL}/publish"

# DOM selectors - 需要根据实际页面结构调整，这里是常见模式
# 小红书使用 React/SPA，DOM 结构会变，建议用 data-* 或较稳定的选择器
SELECTORS = {
    # Login check
    "login_indicator": '[data-v-*]',  # 登录后出现的元素
    "user_avatar": "img[alt*='头像']",  # 用户头像

    # Feed list
    "feed_item": "section.note-item",  # Feed 卡片
    "feed_link": "a[href*='/explore/']",
    "feed_title": ".title",
    "feed_author": ".author-name",
    "feed_likes": ".like-count",
    "feed_comment_count": ".comment-count",

    # Search
    "search_input": "input[placeholder*='搜索']",
    "search_result_item": "section.note-item",

    # Post detail
    "post_title": ".detail-title",
    "post_content": ".detail-desc",
    "post_author": ".author-name",
    "post_likes": ".like-count",
    "comment_item": ".comment-item",
    "comment_content": ".comment-text",
    "comment_input": "textarea[placeholder*='评论']",
    "comment_submit": "button:has-text('发送')",

    # Publish
    "publish_title": "input[placeholder*='标题']",
    "publish_content": "textarea[placeholder*='正文']",
    "publish_image_upload": "input[type='file'][accept*='image']",
    "publish_submit": "button:has-text('发布')",
}
