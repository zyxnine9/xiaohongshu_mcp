"""Xiaohongshu platform adapter - 小红书平台适配器."""
from pathlib import Path
from typing import Optional

from src.core.browser_manager import BrowserManager
from src.core.models import Comment, Post, PublishContent, UserProfile
from src.platforms.base import PlatformBase


class XiaohongshuPlatform(PlatformBase):
    """Xiaohongshu (小红书) platform with fixed workflows."""

    name = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com/explore"

