"""运营 Agent 节点 —— 商家入驻、订单履约、售后工单、平台规则"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from agents.operations_agent import OperationsAgent

_agent = OperationsAgent()


async def operations_agent_node(state: OverallState) -> PartialState:
    """调用运营 Agent 处理后端运营诉求"""

    result = await _agent.handle(state)

    return {
        "final_reply": result.get("reply", ""),
        "need_human": result.get("need_human", False),
        "messages": result.get("messages", []),
    }
