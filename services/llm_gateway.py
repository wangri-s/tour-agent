"""LLM 网关 —— 统一封装模型调用"""

from __future__ import annotations

import os
from typing import Any


class LLMGateway:
    """LLM 调用网关

    封装模型切换、重试、超时、结构化输出等能力。
    MVP 阶段直连 OpenAI 兼容 API；第三阶段可切 Langfuse 追踪。
    """

    def __init__(self):
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """发起 Chat Completion 调用

        Args:
            system: system prompt
            messages: 对话历史
            tools: LangChain tool 列表（可选）
            temperature: 温度参数

        Returns:
            {"content": str, "tool_calls": [...]}  或 {"content": str}
        """

        # TODO MVP: 用 openai SDK 直连
        # 第三阶段：加 Langfuse callback、重试、fallback

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

            formatted = [{"role": "system", "content": system}] + messages

            params: dict[str, Any] = {
                "model": self.model,
                "messages": formatted,
                "temperature": temperature,
            }

            if tools:
                params["tools"] = self._format_tools(tools)
                params["tool_choice"] = "auto"

            response = await client.chat.completions.create(**params)

            choice = response.choices[0]
            msg = choice.message

            result: dict[str, Any] = {"content": msg.content or ""}

            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in msg.tool_calls
                ]

            return result

        except Exception as e:
            return {"content": f"[LLM Error]: {str(e)}"}

    def _format_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """将 LangChain Tool 转为 OpenAI function schema"""
        formatted = []
        for t in tools:
            if hasattr(t, "name") and hasattr(t, "description"):
                params = {}
                if hasattr(t, "args_schema") and t.args_schema:
                    params = t.args_schema.schema() if callable(getattr(t.args_schema, "schema", None)) else {}
                formatted.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": params,
                    },
                })
        return formatted
