"""
BaseAgent — shared foundation for all 7 CMMS agents.

Every agent wraps an OpenAI ChatCompletion call with:
  - A fixed system prompt
  - Structured JSON output via response_format (when supported)
  - Retry logic with tenacity (3 attempts, exponential backoff)
  - Structured logging of every invocation
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog
from openai import AsyncOpenAI, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


class BaseAgent(ABC):
    """Abstract base — subclass and implement `system_prompt` + `run()`."""

    name: str = "BaseAgent"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The agent's static system persona and rules."""
        ...

    @retry(
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _chat(
        self,
        user_message: str,
        json_mode: bool = True,
        extra_messages: Optional[list[dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Core chat call.  Returns the raw assistant content string.
        Set json_mode=True to request a guaranteed JSON response.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            *(extra_messages or []),
            {"role": "user", "content": user_message},
        ]

        kwargs: dict[str, Any] = {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.openai_temperature,
            "max_tokens": max_tokens or settings.openai_max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        log.debug("agent_llm_call", agent=self.name, user_msg_len=len(user_message))
        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        log.debug("agent_llm_response", agent=self.name, response_len=len(content))
        return content

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse JSON, stripping markdown fences if the model included them."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        return json.loads(cleaned)

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Agent entry point — implemented by each subclass."""
        ...
