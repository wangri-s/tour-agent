"""意向评分 Agent —— 评估客户对草案的反馈"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import BaseAgent
from prompts.intent_scorer import INTENT_SCORER_PROMPT
from graph.state import OverallState

logger = logging.getLogger(__name__)

# 客户接受/满意关键词
ACCEPT_KEYWORDS = [
    "好的", "可以", "满意", "不错", "很棒", "完美", "行", "ok", "yes",
    "great", "good", "perfect", "book", "confirm", "接受", "没问题",
    "就这个", "这个就行", "挺好的", "很满意", "下单", "预订",
]


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
        revision_count = s.get("revision_count", 0) if isinstance(s, dict) else state.revision_count

        # =====================================================================
        # 快速路径1: 首次生成 (revision_count == 0)，客户还没回复草案 → 直接 accept
        # 不返回 reply，保留 trip_planner 生成的回复
        # =====================================================================
        if revision_count == 0:
            logger.info("[IntentScorer] 首次生成草案，自动通过 → accept")
            return {
                "intent_level": "high",
                "next_action": "accept",
                "need_human": False,
                "messages": [],
            }

        # =====================================================================
        # 快速路径2: 关键词匹配 → 客户明确说好/要修改
        # =====================================================================
        msgs = s.get("messages", []) if isinstance(s, dict) else state.messages
        last_msg = msgs[-1].content.lower() if msgs else ""
        if last_msg:
            for kw in ACCEPT_KEYWORDS:
                if kw in last_msg:
                    logger.info(f"[IntentScorer] 关键词匹配 '{kw}' → accept")
                    return {
                        "intent_level": "high",
                        "next_action": "accept",
                        "need_human": False,
                        "reply": "很高兴您满意！让我为您生成报价单。",
                        "messages": [],
                    }

        # =====================================================================
        # 慢路径: 调用 LLM 评分 (仅用于复杂的修订反馈)
        # =====================================================================
        need = s.get("need") if isinstance(s, dict) else state.need
        draft = s.get("draft") if isinstance(s, dict) else state.draft
        context = {
            "need": need.model_dump() if hasattr(need, "model_dump") else (need.dict() if hasattr(need, "dict") else need),
            "draft": {"revision_count": revision_count, "cost": draft.estimated_cost if hasattr(draft, "estimated_cost") else draft.get("estimated_cost", 0)},
            "revision_count": revision_count,
            "last_message": last_msg,
        }

        messages = [{"role": "user", "content": f"请评分：\n{context}"}]
        result = await self.call_llm(messages)

        try:
            import json
            raw = result.get("content", "{}")
            if "{" in raw and "}" in raw:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                parsed = json.loads(raw[start:end])
            else:
                parsed = {}
            logger.info(
                f"[IntentScorer] LLM评分: intent={parsed.get('intent_level')} "
                f"action={parsed.get('next_action')}"
            )
            return {
                "intent_level": parsed.get("intent_level", "high"),
                "next_action": parsed.get("next_action", "accept"),
                "need_human": parsed.get("need_human", False),
                "reply": parsed.get("reply", ""),
                "messages": [],
            }
        except Exception:
            logger.warning("[IntentScorer] 解析失败 → 默认 accept")
            return {
                "intent_level": "high",
                "next_action": "accept",
                "need_human": False,
                "reply": "",
                "messages": [],
            }
