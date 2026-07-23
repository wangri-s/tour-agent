"""条件边路由函数

每个函数接收当前 State，返回目标节点名。
兼容 LangGraph TypedDict (dict) 和 Pydantic 对象两种 State 形式。
"""

from __future__ import annotations

from typing import Any
from graph.state import Branch, IntentLevel, NextAction, OverallState


def _s(state: Any, key: str, default: Any = None) -> Any:
    """安全获取 State 字段"""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


# ---------------------------------------------------------------------------
# intent_router 出口
# ---------------------------------------------------------------------------

def route_after_intent(state: OverallState) -> str:
    """意图路由后分发到四类分支或人工"""
    need_human = _s(state, "need_human")
    if need_human:
        return "human_handoff"
    branch = _s(state, "current_branch", "")
    if branch in (Branch.SERVICE.value, "customer_service"):
        return "customer_service"
    elif branch in (Branch.SALES.value, "sales_agent"):
        return "sales_agent"
    elif branch in (Branch.OPERATIONS.value, "operations_agent"):
        return "operations_agent"
    elif branch in (Branch.PLANNER.value, "trip_planner"):
        return "trip_planner"
    return "customer_service"


# ---------------------------------------------------------------------------
# customer_service 出口
# ---------------------------------------------------------------------------

def route_after_service(state: OverallState) -> str:
    """客服完成后：人工 / 结束 / 重新分类"""
    if _s(state, "need_human"):
        return "human_handoff"
    if _s(state, "final_reply"):
        return "END"
    return "intent_router"


# ---------------------------------------------------------------------------
# sales_agent 出口
# ---------------------------------------------------------------------------

def route_after_sales(state: OverallState) -> str:
    """销售完成后：报价 / 运营培育 / 人工"""
    if _s(state, "need_human"):
        return "human_handoff"
    if _s(state, "intent_level") == IntentLevel.HIGH.value:
        return "quote_agent"
    return "operations_agent"


# ---------------------------------------------------------------------------
# trip_planner 出口
# ---------------------------------------------------------------------------

def route_requirements(state: OverallState) -> str:
    """必填项检查：未补齐且无回复→继续追问；已回复→结束等用户反馈；已补齐→评分"""
    need = _s(state, "need")
    draft = _s(state, "draft")
    final_reply = _s(state, "final_reply", "")

    # LangGraph 将 TypedDict 存为普通 dict，需同时兼容两种形式
    if isinstance(need, dict):
        need_complete = all([
            need.get("destination"),
            need.get("days", 0) > 0,
            need.get("arrival_date"),
            need.get("pax", 0) > 0,
            need.get("budget_per_person", 0) > 0,
        ])
    elif hasattr(need, "is_complete"):
        need_complete = need.is_complete()
    else:
        need_complete = False

    if isinstance(draft, dict):
        draft_has_content = bool(draft.get("itinerary_md", ""))
    elif draft and hasattr(draft, "itinerary_md"):
        draft_has_content = bool(draft.itinerary_md)
    else:
        draft_has_content = False

    # 已补齐 + 已生成 → 进入评分
    if need_complete and draft_has_content:
        return "intent_scorer"
    # 已有回复(追问或草稿) → 结束等待用户输入
    if final_reply:
        return "END"
    return "trip_planner"


# ---------------------------------------------------------------------------
# intent_scorer 出口
# ---------------------------------------------------------------------------

def route_revision(state: OverallState) -> str:
    """修订决策：revise / accept / give_up"""
    next_action = _s(state, "next_action", "")
    revision_count = _s(state, "revision_count", 0)
    if next_action == NextAction.REVISE.value and revision_count < 3:
        return "revision_loop"
    if next_action == NextAction.ACCEPT.value:
        return "quote_agent"
    if _s(state, "need_human"):
        return "human_handoff"
    return "operations_agent"
