"""意图路由器节点 —— 结构化输出四类意图概率 + 转人工判断"""

from __future__ import annotations

from typing import Any, cast

from graph.state import OverallState, PartialState, Branch
from agents.intent_router import IntentRouterAgent

# 转人工触发关键词 — 仅限明确要求人工介入的场景
# 注意："退款"已移除，退款走 operations agent 处理，不是直接转人工
HUMAN_HANDOFF_KEYWORDS: list[str] = [
    "投诉", "差评", "人工", "真人", "叫你们经理",
    "complaint", "dissatisfied",
]

_router = IntentRouterAgent()


async def intent_router(state: OverallState) -> PartialState:
    """意图识别 + 转人工前置判断

    1. 关键词命中 → need_human=True, 跳过模型调用
    2. 否则调用轻量模型输出四类概率
    3. 最高概率 < 0.3 → 兜底进入客服
    """

    msgs: list[Any] = state.get("messages", []) if isinstance(state, dict) else state.messages
    last_msg = msgs[-1] if msgs else None
    if last_msg is None:
        return cast(PartialState, {"current_branch": Branch.SERVICE.value})

    text: str = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # ---- 关键词拦截 ----
    if any(kw in text.lower() for kw in HUMAN_HANDOFF_KEYWORDS):
        return cast(PartialState, {
            "need_human": True,
            "current_branch": Branch.SERVICE.value,
        })

    # ---- 模型路由 ----
    result: dict[str, Any] = await _router.classify(text)

    branch: str = result.get("branch", Branch.SERVICE.value)
    raw_scores: dict[str, Any] = result.get("scores", {})
    # 只保留四类有效分支的浮点分值
    valid_branches = {"service", "sales", "operations", "planner"}
    scores: dict[str, float] = {
        k: float(v) for k, v in raw_scores.items()
        if k in valid_branches and isinstance(v, (int, float))
    }

    # 最高概率兜底
    if scores and max(scores.values()) < 0.3:
        branch = Branch.SERVICE.value

    return cast(PartialState, {
        "current_branch": branch,
        "intent_scores": scores,
        "need_human": bool(result.get("need_human", False)),
    })
