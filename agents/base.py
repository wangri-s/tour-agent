"""业务 Agent 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.llm_gateway import LLMGateway


def _normalize_role(msg) -> str:
    """将 LangChain 消息类型映射为 API role (human→user, ai→assistant)"""
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool", "function": "tool"}
    if isinstance(msg, dict):
        raw = msg.get("role", "?")
    elif hasattr(msg, "type"):
        raw = msg.type
    else:
        raw = "assistant"
    return role_map.get(raw, raw)


class BaseAgent(ABC):
    """所有业务 Agent 的基类

    封装 LLM 调用、工具绑定、错误处理等公共逻辑。
    """

    def __init__(self, name: str = "base"):
        self.name = name
        self.llm = LLMGateway()

    @abstractmethod
    def system_prompt(self) -> str:
        """返回该 Agent 的 system prompt"""
        ...

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """封装 LLM 调用"""
        return await self.llm.chat(
            system=self.system_prompt(),
            messages=messages,
            tools=tools,
        )

    async def call_llm_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """流式 LLM 调用 — 边生成边推送到 stream queue，返回完整文本

        如果当前上下文存在 stream queue，每个 token 会被推送为 ("token", text) 事件。
        否则退化为普通流式调用（仅返回完整文本）。
        """
        from services.stream_context import get_stream_queue

        queue = get_stream_queue()
        full_text = ""

        async for token in self.llm.chat_stream(
            system=self.system_prompt(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            full_text += token
            if queue:
                await queue.put(("token", token))

        return full_text
