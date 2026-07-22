"""销售 Agent 节点 —— 产品推介、报价、签约引导"""

from __future__ import annotations

from graph.state import OverallState, PartialState, IntentLevel
from agents.sales_agent import SalesAgent

_agent = SalesAgent()


async def sales_agent_node(state: OverallState) -> PartialState:
    """调用销售 Agent

    返回:
        intent_level  — 高 / 中 / 低
        final_reply    — 销售话术回复
        need_human     — 触发转人工
    """

    result = await _agent.handle(state)

    return {
        "final_reply": result.get("reply", ""),
        "intent_level": result.get("intent_level", IntentLevel.MID.value),
        "need_human": result.get("need_human", False),
        "messages": result.get("messages", []),
    }
