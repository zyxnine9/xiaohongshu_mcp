"""Application settings."""
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App settings loaded from .env."""

    # Browser
    headless: bool = True
    data_dir: Path = Path("data")
    cookies_dir: Path = Path("data/cookies")

    # Platforms
    xiaohongshu_enabled: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
