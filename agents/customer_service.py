"""智能客服 Agent —— FAQ / 订单查询 / 退改政策 / 签证须知"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent, _normalize_role
from prompts.customer_service import CUSTOMER_SERVICE_PROMPT
from graph.state import OverallState
from tools.search_faq import search_faq
from tools.check_handoff import check_handoff


class CustomerServiceAgent(BaseAgent):
    """多语言客服，专注 FAQ 答疑、政策解释、订单查询"""

    def __init__(self):
        super().__init__(name="customer_service")
        self.tools = [search_faq, check_handoff]

    def system_prompt(self) -> str:
        return CUSTOMER_SERVICE_PROMPT

    async def handle(self, state: OverallState) -> dict[str, Any]:
        """处理客服对话

        Returns:
            {
                "reply": str,       # 回复内容
                "need_human": bool,
                "messages": [...],
            }
        """

        msgs = state.get("messages", []) if isinstance(state, dict) else state.messages
        recent = [
            {"role": _normalize_role(m), "content": m.content}
            for m in msgs[-10:]
        ]

        result = await self.call_llm_stream(recent, tools=self.tools)

        return {
            "reply": result,  # call_llm_stream 返回完整文本
            "need_human": "转人工" in result or "人工客服" in result,
            "messages": [],
        }
