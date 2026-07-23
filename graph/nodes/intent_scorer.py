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

    reply = result.get("reply", "")
    ret = {
        "intent_level": result.get("intent_level", ""),
        "next_action": result.get("next_action", ""),
        "need_human": result.get("need_human", False),
        "messages": result.get("messages", []),
    }
    # 只有 scorer 明确返回 reply 时才覆盖 (避免空字符串覆盖 trip_planner 回复)
    if reply:
        ret["final_reply"] = reply
    return ret
