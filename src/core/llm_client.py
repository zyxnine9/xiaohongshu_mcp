"""LLM client for generating contextual replies."""
from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    """Abstract LLM client for generating replies."""

    @abstractmethod
    async def generate_reply(
        self,
        context: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str:
        """Generate contextual reply based on post/comment context."""
        pass


class OpenAIClient(LLMClient):
    """OpenAI-compatible API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def generate_reply(
        self,
        context: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str:
        """Generate reply using OpenAI API."""
        from openai import AsyncOpenAI
        import os

        client = AsyncOpenAI(
            api_key=self.api_key or os.getenv("OPENAI_API_KEY"),
            base_url=self.base_url or os.getenv("OPENAI_BASE_URL"),
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个友好的社交媒体运营助手。根据给定的帖子/评论内容，"
                        "生成自然、有温度的回复。回复要简洁，符合平台调性，避免营销感过重。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"【上下文】\n{context}\n\n【回复要求】\n{prompt}",
                },
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()


def get_llm_client(
    provider: str = "openai",
    **kwargs,
) -> LLMClient:
    """Factory for LLM clients."""
    if provider == "openai":
        return OpenAIClient(**kwargs)
    raise ValueError(f"Unknown LLM provider: {provider}")
