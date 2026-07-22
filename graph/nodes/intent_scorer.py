"""意向评分节点 —— 评估客户对草案的反馈"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from agents.intent_scorer import IntentScorerAgent

_agent = IntentScorerAgent()


async def intent_scorer(state: OverallState) -> PartialState:
    """独立评分节点，输出 intent_level 与 next_action

    调用时机: 行程草案生成后，客户给出反馈时
    """

    result = await _agent.score(state)

    return {
        "intent_level": result.get("intent_level", ""),
        "next_action": result.get("next_action", ""),
        "need_human": result.get("need_human", False),
        "final_reply": result.get("reply", ""),
        "messages": result.get("messages", []),
    }
