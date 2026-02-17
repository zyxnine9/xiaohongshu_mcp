"""Common data models across platforms (Pydantic)."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Supported social media platforms."""
    XIAOHONGSHU = "xiaohongshu"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"


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
    video_url: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class Comment(BaseModel):
    """A comment on a post."""
    id: str
    content: str
    author: str
    author_id: str
    likes: int = 0
    parent_id: str = ""


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
