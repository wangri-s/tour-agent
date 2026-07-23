"""销售 Agent —— 产品推介、报价、签约引导、意向评分"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent, _normalize_role
from prompts.sales_agent import SALES_AGENT_PROMPT
from graph.state import OverallState, IntentLevel
from tools.quote_price import quote_price
from tools.query_inventory import query_inventory


class SalesAgent(BaseAgent):
    """主动引导客户完成产品销售

    确认预算与决策人，高意向推送签约链接，中低意向推送案例与优惠。
    """

    def __init__(self):
        super().__init__(name="sales_agent")
        self.tools = [quote_price, query_inventory]

    def system_prompt(self) -> str:
        return SALES_AGENT_PROMPT

    async def handle(self, state: OverallState) -> dict[str, Any]:
        """处理销售对话

        Returns:
            {
                "reply": str,
                "intent_level": "high" | "mid" | "low",
                "need_human": bool,
                "messages": [...],
            }
        """

        recent = [
            {"role": _normalize_role(m), "content": m.content}
            for m in (state.get("messages", []) if isinstance(state, dict) else state.messages)[-10:]
        ]

        result = await self.call_llm_stream(recent, tools=self.tools)
        content = result  # call_llm_stream 返回完整文本

        # ---- 简易意向评分 ----
        intent_level = self._score_intent(content)

        return {
            "reply": content,
            "intent_level": intent_level,
            "need_human": False,
            "messages": [],
        }

    def _score_intent(self, text: str) -> str:
        """关键词简易评分"""
        high_keywords = ["签约", "支付", "定金", "sign", "pay", "deposit"]
        mid_keywords = ["考虑", "再看看", "优惠", "consider", "discount"]

        text_lower = text.lower()
        if any(kw in text_lower for kw in high_keywords):
            return IntentLevel.HIGH.value
        if any(kw in text_lower for kw in mid_keywords):
            return IntentLevel.MID.value
        return IntentLevel.LOW.value
