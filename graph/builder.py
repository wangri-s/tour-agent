"""Graph Builder —— 组装 LangGraph 有向图

节点编排顺序:
    input_guard → session_context → intent_router
                                        ↓
                      ┌─────────────────┼─────────────────┬─────────────────┐
                      ↓                 ↓                  ↓                  ↓
              customer_service    sales_agent      operations_agent    trip_planner
                      ↓                 ↓                  ↓                  ↓
                after_service    intent_score      operations_sync    requirements
                      ↓                 ↓                              complete?
                END / human    quote / ops                              ↓
                                / human                          trip_planner
                                                                      ↓
                                                                intent_scorer
                                                                      ↓
                                                              revision_decision
                                                              ↓       ↓       ↓
                                                          revise   accept  give_up
"""

from __future__ import annotations

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import OverallState
from graph.nodes.input_guard import input_guard
from graph.nodes.session_context import session_context
from graph.nodes.intent_router import intent_router
from graph.nodes.customer_service import customer_service
from graph.nodes.sales_agent import sales_agent_node
from graph.nodes.operations_agent import operations_agent_node
from graph.nodes.trip_planner import trip_planner
from graph.nodes.intent_scorer import intent_scorer
from graph.nodes.revision_loop import revision_loop
from graph.nodes.quote_agent import quote_agent_node
from graph.nodes.human_handoff import human_handoff
from graph.nodes.operations_sync import operations_sync
from graph.routing import (
    route_after_intent,
    route_after_service,
    route_after_sales,
    route_requirements,
    route_revision,
)

logger = logging.getLogger(__name__)


def _get_checkpointer():
    """获取 Checkpointer: PostgresSaver 优先 → MemorySaver 降级"""
    try:
        from services.checkpoint_store import create_postgres_saver_sync
        saver = create_postgres_saver_sync()
        if saver:
            return saver
    except Exception as e:
        logger.info(f"[Graph] PostgresSaver 不可用: {e}，使用 MemorySaver")
    return MemorySaver()


def build_graph(checkpointer=None) -> StateGraph:
    """构建并返回编译后的 LangGraph 实例"""

    builder = StateGraph(OverallState)

    # =========================================================================
    # 添加节点
    # =========================================================================

    builder.add_node("input_guard", input_guard)
    builder.add_node("session_context", session_context)
    builder.add_node("intent_router", intent_router)
    builder.add_node("customer_service", customer_service)
    builder.add_node("sales_agent", sales_agent_node)
    builder.add_node("operations_agent", operations_agent_node)
    builder.add_node("trip_planner", trip_planner)
    builder.add_node("intent_scorer", intent_scorer)
    builder.add_node("revision_loop", revision_loop)
    builder.add_node("quote_agent", quote_agent_node)
    builder.add_node("human_handoff", human_handoff)
    builder.add_node("operations_sync", operations_sync)

    # =========================================================================
    # 添加边
    # =========================================================================

    # 入口
    builder.set_entry_point("input_guard")
    builder.add_edge("input_guard", "session_context")
    builder.add_edge("session_context", "intent_router")

    # 意图路由器 → 条件分发到四类分支
    builder.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "customer_service": "customer_service",
            "sales_agent": "sales_agent",
            "operations_agent": "operations_agent",
            "trip_planner": "trip_planner",
            "human_handoff": "human_handoff",
        },
    )

    # 客服 → 条件边
    builder.add_conditional_edges(
        "customer_service",
        route_after_service,
        {
            "human_handoff": "human_handoff",
            "END": END,
            "intent_router": "intent_router",
        },
    )

    # 销售 → 条件边（意向评分决定去向）
    builder.add_conditional_edges(
        "sales_agent",
        route_after_sales,
        {
            "quote_agent": "quote_agent",
            "operations_agent": "operations_agent",
            "human_handoff": "human_handoff",
        },
    )

    # 运营 → operations_sync → END
    builder.add_edge("operations_agent", "operations_sync")
    builder.add_edge("operations_sync", END)

    # 旅游定制 → 条件边（必填项检查 / 追问结束 / 进入评分）
    builder.add_conditional_edges(
        "trip_planner",
        route_requirements,
        {
            "trip_planner": "trip_planner",       # 必填未补齐 → 继续追问
            "intent_scorer": "intent_scorer",     # 已补齐 → 评分
            "END": END,                           # 追问/草稿已回复 → 等待用户
        },
    )

    # 意向评分 → 条件边（修订决策）
    builder.add_conditional_edges(
        "intent_scorer",
        route_revision,
        {
            "revision_loop": "revision_loop",     # revise 且次数 <3
            "quote_agent": "quote_agent",         # accept
            "operations_agent": "operations_agent",  # give_up 或超次
            "human_handoff": "human_handoff",     # give_up → 人工
        },
    )

    # 修订循环 → trip_planner 重新生成
    builder.add_edge("revision_loop", "trip_planner")

    # 报价 → operations_sync → END
    builder.add_edge("quote_agent", "operations_sync")

    # 人工接管 → 兜底 → END
    builder.add_edge("human_handoff", "operations_sync")

    # =========================================================================
    # 编译
    # =========================================================================

    if checkpointer is None:
        checkpointer = _get_checkpointer()
    return builder.compile(checkpointer=checkpointer)
