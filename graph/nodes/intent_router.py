"""意图路由器节点 —— 结构化输出四类意图概率 + 转人工判断"""

from __future__ import annotations

from graph.state import OverallState, PartialState, Branch
from agents.intent_router import IntentRouterAgent

# 转人工触发关键词
HUMAN_HANDOFF_KEYWORDS = [
    "投诉", "退款", "差评", "人工", "真人",
    "complaint", "refund", "dissatisfied",
]

_router = IntentRouterAgent()


async def intent_router(state: OverallState) -> PartialState:
    """意图识别 + 转人工前置判断

    1. 关键词命中 → need_human=True, 跳过模型调用
    2. 否则调用轻量模型输出四类概率
    3. 最高概率 < 0.3 → 兜底进入客服
    """

    last_msg = state.messages[-1] if state.messages else None
    if last_msg is None:
        return {"current_branch": Branch.SERVICE.value}

    text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # ---- 关键词拦截 ----
    if any(kw in text.lower() for kw in HUMAN_HANDOFF_KEYWORDS):
        return {
            "need_human": True,
            "current_branch": Branch.SERVICE.value,
        }

    # ---- 模型路由 ----
    result = await _router.classify(text)

    branch = result.get("branch", Branch.SERVICE.value)
    scores = result.get("scores", {})

    # 最高概率兜底
    if max(scores.values(), default=0) < 0.3:
        branch = Branch.SERVICE.value

    return {
        "current_branch": branch,
        "intent_scores": scores,
        "need_human": result.get("need_human", False),
    }
