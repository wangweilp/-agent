"""DeepSeek API 适配器 — 实现 ChatModel 协议。"""
import logging
from typing import Any

from openai import APIError, APIConnectionError, OpenAI, RateLimitError

from src.adapters.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用通用错误。"""


class RateLimitExceededError(LLMError):
    """API 速率限制。"""


class DeepSeekAdapter:
    """通过 OpenAI 兼容接口调用 DeepSeek API。"""

    def __init__(self, config: Settings) -> None:
        self._model = config.deepseek_model
        self._client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        try:
            return self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                stream=stream,
                **kwargs,
            )
        except RateLimitError as e:
            raise RateLimitExceededError(str(e)) from e
        except APIConnectionError as e:
            raise LLMError(f"无法连接到 DeepSeek API，请检查网络和 base_url: {e}") from e
        except APIError as e:
            raise LLMError(f"DeepSeek API 错误: {e}") from e

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DeepSeekAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
