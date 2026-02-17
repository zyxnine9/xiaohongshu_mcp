"""Common data types across platforms."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Platform(str, Enum):
    """Supported social media platforms."""
    XIAOHONGSHU = "xiaohongshu"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"


@dataclass
class Post:
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
    images: list[str] = field(default_factory=list)
    video_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Comment:
    """A comment on a post."""
    id: str
    content: str
    author: str
    author_id: str
    likes: int = 0
    parent_id: str = ""


@dataclass
class UserProfile:
    """User profile info."""
    user_id: str
    nickname: str
    bio: str = ""
    followers: int = 0
    following: int = 0
    likes_count: int = 0


@dataclass
class PublishContent:
    """Content to publish."""
    title: str = ""
    content: str = ""
    images: list[str] = field(default_factory=list)
    video: str = ""
    tags: list[str] = field(default_factory=list)
