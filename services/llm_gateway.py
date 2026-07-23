"""LLM 网关 —— 统一封装模型调用 (千问 + OpenAI 兼容)"""

from __future__ import annotations

import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMGateway:
    """LLM 调用网关

    默认使用阿里云 DashScope 千问模型 (OpenAI 兼容协议)。
    支持切换 OpenAI / 本地模型。
    """

    # 模型配置
    DEFAULT_MODEL = "qwen-plus"           # 千问主力模型 (性价比最优)
    PLANNER_MODEL = "qwen-max"            # 千问旗舰模型 (旅游定制复杂推理)
    ROUTER_MODEL = "qwen-turbo"           # 千问轻量模型 (意图路由)

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self.api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = os.getenv(
            "DASHSCOPE_BASE_URL",
            os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """发起 Chat Completion 调用

        Args:
            system:   system prompt
            messages: 对话历史 [{"role": "user"|"assistant", "content": "..."}]
            tools:    LangChain tool 列表（可选）
            temperature: 温度参数 (0-2)
            max_tokens:  最大输出 token

        Returns:
            {"content": str, "tool_calls": [...]}  或 {"content": str}
        """

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

            formatted: list[dict[str, Any]] = [{"role": "system", "content": system}]
            formatted.extend(messages)

            params: dict[str, Any] = {
                "model": self.model,
                "messages": formatted,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if tools:
                params["tools"] = self._format_tools(tools)
                params["tool_choice"] = "auto"

            logger.info(f"[LLM] calling {self.model} ({len(formatted)} messages, {len(tools or [])} tools)")
            response = await client.chat.completions.create(**params)

            choice = response.choices[0]
            msg = choice.message

            result: dict[str, Any] = {"content": msg.content or ""}

            # 处理 Tool Calls（千问支持 OpenAI function calling 格式）
            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in msg.tool_calls
                ]

            # 记录使用量
            if hasattr(response, "usage") and response.usage:
                logger.info(
                    f"[LLM] tokens: {response.usage.prompt_tokens} in / "
                    f"{response.usage.completion_tokens} out"
                )

            return result

        except Exception as e:
            import traceback
            logger.error(f"[LLM Error]: {type(e).__name__}: {str(e)[:300]}")
            logger.debug(traceback.format_exc())
            return {"content": f"[AI 服务暂时不可用，请稍后重试]", "error": str(e)[:300]}

    async def chat_with_tools(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[Any],
        temperature: float = 0.7,
        max_turns: int = 5,
    ) -> dict[str, Any]:
        """带工具调用的多轮对话循环

        自动处理 tool_calls → 执行工具 → 回传结果 → 继续对话。

        Args:
            system:    system prompt
            messages:  对话历史
            tools:     LangChain tool 列表
            temperature: 温度
            max_turns:   最大工具调用轮次

        Returns:
            {"content": str, "tool_calls_made": [...]}
        """

        tool_map = {t.name: t for t in tools}
        tool_calls_made: list[dict] = []

        current_msgs: list[dict[str, Any]] = list(messages)

        for turn in range(max_turns):
            result = await self.chat(system, current_msgs, tools=tools, temperature=temperature)

            if "error" in result:
                return result

            # 没有 tool_calls → 最终回复
            if not result.get("tool_calls"):
                return {
                    "content": result["content"],
                    "tool_calls_made": tool_calls_made,
                }

            # 处理 tool_calls
            tool_msgs: list[dict[str, Any]] = []
            for tc in result["tool_calls"]:
                tool_name = tc["name"]
                tool = tool_map.get(tool_name)

                if tool is None:
                    logger.warning(f"[LLM] unknown tool: {tool_name}")
                    continue

                try:
                    args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                except json.JSONDecodeError:
                    args = {}

                logger.info(f"[LLM] tool call: {tool_name}({json.dumps(args, ensure_ascii=False)[:200]})")

                try:
                    tool_result = await tool.ainvoke(args)
                    tool_result_str = str(tool_result)
                except Exception as e:
                    tool_result_str = f"Tool error: {str(e)}"
                    logger.error(f"[LLM] tool {tool_name} failed: {e}")

                tool_calls_made.append({
                    "name": tool_name,
                    "arguments": args,
                    "result": tool_result_str[:500],
                })

                tool_msgs.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tc["arguments"]},
                    }],
                })
                tool_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result_str,
                })

            current_msgs.extend(tool_msgs)

        # 超过最大轮次，用最后一轮结果
        final = await self.chat(system, current_msgs, temperature=temperature)
        return {
            "content": final.get("content", ""),
            "tool_calls_made": tool_calls_made,
        }

    def _format_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """将 LangChain Tool 转为 OpenAI function schema"""
        formatted = []
        for t in tools:
            name = getattr(t, "name", None)
            desc = getattr(t, "description", None)
            if not name or not desc:
                continue

            params_schema = {"type": "object", "properties": {}, "required": []}

            if hasattr(t, "args_schema") and t.args_schema:
                try:
                    raw = t.args_schema.model_json_schema()
                    params_schema = {
                        "type": "object",
                        "properties": raw.get("properties", {}),
                        "required": raw.get("required", []),
                    }
                except Exception:
                    pass

            formatted.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params_schema,
                },
            })
        return formatted


# 预置实例
gateway_default = LLMGateway()                      # qwen-plus (默认)
gateway_router = LLMGateway(model="qwen-turbo")     # 轻量路由
gateway_planner = LLMGateway(model="qwen-max")      # 旗舰定制
