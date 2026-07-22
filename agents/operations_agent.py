"""运营 Agent —— 商家入驻、订单履约、平台规则、售后工单"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from prompts.operations_agent import OPERATIONS_AGENT_PROMPT
from graph.state import OverallState
from tools.update_crm import update_crm
from tools.send_capi import send_capi


class OperationsAgent(BaseAgent):
    """处理商家入驻、订单履约、售后工单、平台规则"""

    def __init__(self):
        super().__init__(name="operations_agent")
        self.tools = [update_crm, send_capi]

    def system_prompt(self) -> str:
        return OPERATIONS_AGENT_PROMPT

    async def handle(self, state: OverallState) -> dict[str, Any]:
        """处理运营诉求

        Returns:
            {
                "reply": str,
                "need_human": bool,
                "messages": [...],
            }
        """

        recent = [
            {"role": m.type if hasattr(m, "type") else "assistant", "content": m.content}
            for m in state.messages[-10:]
        ]

        result = await self.call_llm(recent, tools=self.tools)

        return {
            "reply": result.get("content", ""),
            "need_human": result.get("need_human", False),
            "messages": [],
        }
