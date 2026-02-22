"""Common data models across platforms (Pydantic)."""
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Supported social media platforms."""
    XIAOHONGSHU = "xiaohongshu"


class Comment(BaseModel):
    id: str
    noteId: str
    createTime: int
    likeCount: int           # 自动将 "1" 转为 1
    liked: bool
    subCommentCount: int     # 自动将 "0" 转为 0
    showTags: List[str] = []

class Post(BaseModel):
    """A social media post."""
    id: str
    title: str = ""
    content: str = ""
    author: str = ""
    author_id: str = ""
    xsec_token: str = ""  # Platform-specific token (e.g., xiaohongshu)
    likes: int = 0
    comments_count: int = 0
    shares: int = 0
    images: list[str] = Field(default_factory=list)
    comments: List[Comment] = Field(default_factory=list)
    raw: Optional[Any] = None  # 原始数据，用于获取评论等


class UserProfile(BaseModel):
    """User profile info."""
    user_id: str
    nickname: str
    bio: str = ""
    followers: int = 0
    following: int = 0
    likes_count: int = 0


class PublishContent(BaseModel):
    """Content to publish."""
    title: str = ""
    content: str = ""
    images: list[str] = Field(default_factory=list)
    video: str = ""
    tags: list[str] = Field(default_factory=list)
