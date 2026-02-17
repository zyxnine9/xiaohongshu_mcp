"""小红书固定流程：登录、Feed 列表、搜索、发布、Feed 详情、Feed 评论、用户资料等."""
from . import (
    feed_comments_workflow,
    feed_detail_workflow,
    feeds_workflow,
    login_workflow,
    publish_workflow,
    search_workflow,
    user_profile_workflow,
)

__all__ = [
    "feed_comments_workflow",
    "feed_detail_workflow",
    "login_workflow",
    "feeds_workflow",
    "publish_workflow",
    "search_workflow",
    "user_profile_workflow",
]
