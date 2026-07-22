"""意图路由器 Agent —— 使用千问 qwen-turbo 做结构化输出"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import BaseAgent
from prompts.intent_router import INTENT_ROUTER_PROMPT
from services.llm_gateway import gateway_router

logger = logging.getLogger(__name__)


class IntentRouterAgent(BaseAgent):
    """用 qwen-turbo (轻量模型) 做意图分类

    输出四类意图概率 + 是否需要人工。
    轻量模型降低延迟和成本，复杂场景可升级 qwen-max。
    """

    def __init__(self):
        super().__init__(name="intent_router")
        self.llm = gateway_router  # 专门的路由模型实例

    def system_prompt(self) -> str:
        return INTENT_ROUTER_PROMPT

    async def classify(self, user_message: str) -> dict[str, Any]:
        """分类用户意图

        Args:
            user_message: 用户消息文本

        Returns:
            {
                "branch": "service" | "sales" | "operations" | "planner",
                "scores": {"service": 0.1, "sales": 0.05, "operations": 0.02, "planner": 0.83},
                "need_human": false
            }
        """

        messages = [{"role": "user", "content": user_message}]

        try:
            result = await self.llm.chat(
                system=self.system_prompt(),
                messages=messages,
                temperature=0.1,  # 低温度，保证一致性
                max_tokens=512,
            )

            raw = result.get("content", "{}")

            # 提取 JSON (可能被 markdown 包裹)
            if "```" in raw:
                # 提取 code block
                start = raw.index("```") + 3
                end = raw.index("```", start)
                raw = raw[start:end].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            if "{" in raw and "}" in raw:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                parsed = json.loads(raw[start:end])
            else:
                parsed = {}

            branch = parsed.get("branch", "service")
            scores = parsed.get("scores", {})

            # 验证 scores
            valid_branches = {"service", "sales", "operations", "planner"}
            scores = {k: float(v) for k, v in scores.items() if k in valid_branches and isinstance(v, (int, float))}

            logger.info(
                f"[IntentRouter] → {branch} "
                f"scores={json.dumps(scores, ensure_ascii=False)}"
            )

            return {
                "branch": branch,
                "scores": scores,
                "need_human": parsed.get("need_human", False),
            }

        except Exception as e:
            logger.error(f"[IntentRouter] 分类失败: {e}")
            return {
                "branch": "service",
                "scores": {},
                "need_human": False,
            }
