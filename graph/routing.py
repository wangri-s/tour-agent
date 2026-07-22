"""条件边路由函数

每个函数接收当前 State，返回目标节点名。
"""

from __future__ import annotations

from graph.state import Branch, IntentLevel, NextAction, OverallState

# ---------------------------------------------------------------------------
# intent_router 出口
# ---------------------------------------------------------------------------

def route_after_intent(state: OverallState) -> str:
    """意图路由后分发到四类分支或人工"""
    if state.need_human:
        return "human_handoff"
    branch = state.current_branch
    if branch == Branch.SERVICE.value:
        return "customer_service"
    elif branch == Branch.SALES.value:
        return "sales_agent"
    elif branch == Branch.OPERATIONS.value:
        return "operations_agent"
    elif branch == Branch.PLANNER.value:
        return "trip_planner"
    # fallback
    return "customer_service"


# ---------------------------------------------------------------------------
# customer_service 出口
# ---------------------------------------------------------------------------

def route_after_service(state: OverallState) -> str:
    """客服完成后：人工 / 结束 / 重新分类"""
    if state.need_human:
        return "human_handoff"
    if state.final_reply:
        return "END"
    return "intent_router"


# ---------------------------------------------------------------------------
# sales_agent 出口
# ---------------------------------------------------------------------------

def route_after_sales(state: OverallState) -> str:
    """销售完成后：报价 / 运营培育 / 人工"""
    if state.need_human:
        return "human_handoff"
    if state.intent_level == IntentLevel.HIGH.value:
        return "quote_agent"
    # mid / low → 运营培育
    return "operations_agent"


# ---------------------------------------------------------------------------
# trip_planner 出口
# ---------------------------------------------------------------------------

def route_requirements(state: OverallState) -> str:
    """必填项检查：未补齐继续追问，已补齐进入评分"""
    if state.need.is_complete() and state.draft.itinerary_md:
        return "intent_scorer"
    return "trip_planner"


# ---------------------------------------------------------------------------
# intent_scorer 出口
# ---------------------------------------------------------------------------

def route_revision(state: OverallState) -> str:
    """修订决策：revise / accept / give_up"""
    if state.next_action == NextAction.REVISE.value and state.revision_count < 3:
        return "revision_loop"
    if state.next_action == NextAction.ACCEPT.value:
        return "quote_agent"
    # give_up 或超次
    if state.need_human:
        return "human_handoff"
    return "operations_agent"
