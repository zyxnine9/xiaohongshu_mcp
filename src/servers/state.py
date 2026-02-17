"""Shared state for HTTP and MCP servers (single browser + platform instance)."""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.platforms.base import PlatformBase

# Global platform instance, set by server lifespan
_platform: Optional["PlatformBase"] = None


def get_platform() -> "PlatformBase":
    if _platform is None:
        raise RuntimeError("Platform not initialized. Start the server first.")
    return _platform


def set_platform(platform: Optional["PlatformBase"]) -> None:
    global _platform
    _platform = platform
