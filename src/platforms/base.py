"""Abstract base for platform adapters."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from src.core.browser_manager import BrowserManager
from src.core.llm_client import LLMClient
from src.core.models import Comment, Post, PublishContent, UserProfile


class PlatformBase(ABC):
    """Abstract base for all social media platforms."""

    name: str = ""
    base_url: str = ""

    def __init__(
        self,
        browser: BrowserManager,
        llm: Optional[LLMClient] = None,
        cookies_path: Optional[Path] = None,
    ):
        self.browser = browser
        self.llm = llm
        self.cookies_path = cookies_path or Path("data") / "cookies" / f"{self.name}.json"

    # --- Auth ---
    @abstractmethod
    async def login(self, headless: bool = False) -> bool:
        """Perform login. Returns True if successful."""
        pass

    @abstractmethod
    async def check_login(self) -> bool:
        """Check if currently logged in."""
        pass

    # --- Read operations (DOM-based, fast) ---
    @abstractmethod
    async def get_feeds(self, limit: int = 20) -> list[Post]:
        """Get feed/recommended list."""
        pass

    @abstractmethod
    async def search(self, keyword: str, limit: int = 20) -> list[Post]:
        """Search content by keyword."""
        pass

    @abstractmethod
    async def get_post_detail(self, post_id: str, xsec_token: str = "") -> Optional[Post]:
        """Get post detail including comments."""
        pass

    async def get_user_profile(self, user_id: str, xsec_token: str = "") -> Optional[UserProfile]:
        """Get user profile. Default: not implemented."""
        return None

    # --- Write operations (fixed workflows / browser-use) ---
    @abstractmethod
    async def publish(self, content: PublishContent) -> Optional[str]:
        """Publish post. Returns post_id or None."""
        pass

    @abstractmethod
    async def comment(self, post_id: str, content: str, xsec_token: str = "") -> bool:
        """Post comment on a post."""
        pass

    async def reply(
        self,
        post_id: str,
        comment_id: str,
        content: str,
        xsec_token: str = "",
        use_llm: bool = False,
        context: str = "",
    ) -> bool:
        """Reply to a comment. Can use LLM for contextual content if use_llm=True."""
        if use_llm and self.llm and context:
            content = await self.llm.generate_reply(context, f"针对这条评论回复：{content}")
        return await self._reply_impl(post_id, comment_id, content, xsec_token)

    async def _reply_impl(
        self,
        post_id: str,
        comment_id: str,
        content: str,
        xsec_token: str = "",
    ) -> bool:
        """Platform-specific reply implementation. Default: same as comment."""
        return await self.comment(post_id, content, xsec_token)
