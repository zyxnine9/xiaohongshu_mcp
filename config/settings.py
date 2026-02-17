"""Application settings."""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App settings loaded from .env."""

    # LLM
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"

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
