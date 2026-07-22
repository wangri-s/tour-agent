"""意向评分 Agent —— 评估客户对草案的反馈"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from prompts.intent_scorer import INTENT_SCORER_PROMPT
from graph.state import OverallState


class IntentScorerAgent(BaseAgent):
    """独立评分，输出 intent_level 和 next_action"""

    def __init__(self):
        super().__init__(name="intent_scorer")

    def system_prompt(self) -> str:
        return INTENT_SCORER_PROMPT

    async def score(self, state: OverallState) -> dict[str, Any]:
        """对客户最新反馈进行意向评分

        Returns:
            {
                "intent_level": "high" | "mid" | "low",
                "next_action": "revise" | "accept" | "give_up",
                "need_human": bool,
                "reply": str,
            }
        """

        context = {
            "need": state.need.model_dump(),
            "draft": state.draft.model_dump(),
            "revision_count": state.revision_count,
            "last_message": state.messages[-1].content if state.messages else "",
        }

        messages = [
            {"role": "user", "content": f"请评分：\n{context}"}
        ]

        result = await self.call_llm(messages)

        # 简易解析
        try:
            import json
            parsed = json.loads(result.get("content", "{}"))
            return {
                "intent_level": parsed.get("intent_level", "mid"),
                "next_action": parsed.get("next_action", "give_up"),
                "need_human": parsed.get("need_human", False),
                "reply": parsed.get("reply", ""),
                "messages": [],
            }
        except Exception:
            return {
                "intent_level": "mid",
                "next_action": "give_up",
                "need_human": False,
                "reply": "",
                "messages": [],
            }
