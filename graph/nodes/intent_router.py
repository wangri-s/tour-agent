"""意图路由器节点 —— 结构化输出四类意图概率 + 转人工判断"""

from __future__ import annotations

import re
from typing import Any, cast

from graph.state import OverallState, PartialState, Branch
from agents.intent_router import IntentRouterAgent

# 转人工触发关键词 — 仅限明确要求人工介入的场景
HUMAN_HANDOFF_KEYWORDS: list[str] = [
    "投诉", "差评", "人工", "真人", "叫你们经理",
    "complaint", "dissatisfied",
]

# 补全参数模式 — 用户正在回答 agent 的追问，应路由回原分支
# 例: "三天"/"5天" → planner, "2人"/"3个人" → planner, "预算5000" → planner
TRIP_PARAM_PATTERNS: list[str] = [
    r"^\d+\s*天$",           # "三天", "5天", "3 天"
    r"^\d+\s*日$",           # "5日"
    r"^\d+\s*个?\s*人$",     # "2人", "3个人", "2 人"
    r"^预算\s*\d+",          # "预算5000", "预算 3000"
    r"^\d+\s*[块元]$",       # "5000块", "3000元"
    r"^\d+\s*[kKwW]$",       # "5k", "8K"
]

_router = IntentRouterAgent()


def _is_trip_param(text: str) -> bool:
    """检测消息是否为行程参数补全 (回答追问)"""
    for pat in TRIP_PARAM_PATTERNS:
        if re.match(pat, text.strip()):
            return True
    return False


def _has_trip_context(state: OverallState) -> bool:
    """检测会话上下文中是否已有行程规划进行中"""
    need = state.get("need") if isinstance(state, dict) else getattr(state, "need", None)
    if need is None:
        return False
    if isinstance(need, dict):
        return bool(need.get("destination"))
    return bool(getattr(need, "destination", ""))


async def intent_router(state: OverallState) -> PartialState:
    """意图识别 + 转人工前置判断

    1. 关键词命中 → need_human=True, 跳过模型调用
    2. 行程参数补全 (数字+单位) → 直接路由到 planner
    3. 否则调用轻量模型输出四类概率
    4. 最高概率 < 0.3 → 兜底进入客服
    """

    msgs: list[Any] = state.get("messages", []) if isinstance(state, dict) else state.messages
    last_msg = msgs[-1] if msgs else None
    if last_msg is None:
        return cast(PartialState, {"current_branch": Branch.SERVICE.value})

    text: str = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # ---- 关键词拦截: 投诉转人工 ----
    if any(kw in text.lower() for kw in HUMAN_HANDOFF_KEYWORDS):
        return cast(PartialState, {
            "need_human": True,
            "current_branch": Branch.SERVICE.value,
        })

    # ---- 行程参数补全: 用户正在回答规划师的追问 ----
    if _is_trip_param(text) or _has_trip_context(state):
        # 如果是明显的参数补全 OR 会话已有规划上下文 → 直接走 planner
        return cast(PartialState, {
            "current_branch": Branch.PLANNER.value,
            "intent_scores": {"planner": 0.9, "service": 0.05, "sales": 0.03, "operations": 0.02},
        })

    # ---- 模型路由 ----
    result: dict[str, Any] = await _router.classify(text)

    branch: str = result.get("branch", Branch.SERVICE.value)
    raw_scores: dict[str, Any] = result.get("scores", {})
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
