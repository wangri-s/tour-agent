"""智能客服节点 —— FAQ 答疑、政策解释、订单查询、投诉转人工"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from agents.customer_service import CustomerServiceAgent

_agent = CustomerServiceAgent()


async def customer_service(state: OverallState) -> PartialState:
    """调用客服 Agent 处理 FAQ / 订单 / 政策类问题

    返回:
        final_reply   — 简单问答直接返回
        need_human    — 复杂问题转人工
    """

    result = await _agent.handle(state)

    return {
        "final_reply": result.get("reply", ""),
        "need_human": result.get("need_human", False),
        "messages": result.get("messages", []),
    }
