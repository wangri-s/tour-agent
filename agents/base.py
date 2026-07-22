"""业务 Agent 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.llm_gateway import LLMGateway


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
