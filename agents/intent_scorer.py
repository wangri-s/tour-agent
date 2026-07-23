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

        s = state if isinstance(state, dict) else state.__dict__ if hasattr(state, '__dict__') else {}
        need = s.get("need") if isinstance(s, dict) else state.need
        draft = s.get("draft") if isinstance(s, dict) else state.draft
        msgs = s.get("messages", []) if isinstance(s, dict) else state.messages
        context = {
            "need": need.model_dump() if hasattr(need, "model_dump") else need,
            "draft": draft.model_dump() if hasattr(draft, "model_dump") else draft,
            "revision_count": s.get("revision_count", 0) if isinstance(s, dict) else state.revision_count,
            "last_message": msgs[-1].content if msgs else "",
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
