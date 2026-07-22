"""报价 Agent 节点 —— 基于 draft 与 need 生成结构化报价单"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from agents.quote_agent import QuoteAgent

_agent = QuoteAgent()


async def quote_agent_node(state: OverallState) -> PartialState:
    """调用报价 Agent 生成分项报价

    分项: 机票、酒店、交通、门票、餐饮、导游
    """

    result = await _agent.generate(state)

    return {
        "quote": result.get("quote"),
        "final_reply": result.get("reply", ""),
        "messages": result.get("messages", []),
    }
