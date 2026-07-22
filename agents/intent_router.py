"""意图路由器 Agent —— 轻量模型做结构化输出"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from prompts.intent_router import INTENT_ROUTER_PROMPT


class IntentRouterAgent(BaseAgent):
    """用 GPT-4o-mini / 本地 7B 做意图分类

    输出四类意图概率 + 是否需要人工。
    """

    def __init__(self):
        super().__init__(name="intent_router")

    def system_prompt(self) -> str:
        return INTENT_ROUTER_PROMPT

    async def classify(self, user_message: str) -> dict[str, Any]:
        """分类用户意图

        Returns:
            {
                "branch": "service" | "sales" | "operations" | "planner",
                "scores": {"service": 0.1, "sales": 0.05, "operations": 0.02, "planner": 0.83},
                "need_human": false
            }
        """

        messages = [{"role": "user", "content": user_message}]

        result = await self.call_llm(messages)

        # 解析 LLM 结构化输出
        try:
            import json
            parsed = json.loads(result.get("content", "{}"))
            return {
                "branch": parsed.get("branch", "service"),
                "scores": parsed.get("scores", {}),
                "need_human": parsed.get("need_human", False),
            }
        except Exception:
            return {
                "branch": "service",
                "scores": {},
                "need_human": False,
            }
