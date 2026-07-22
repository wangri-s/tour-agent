"""旅游定制 Agent 节点 —— 根据需求生成行程草案"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from agents.trip_planner import TripPlannerAgent

_agent = TripPlannerAgent()


async def trip_planner(state: OverallState) -> PartialState:
    """调用旅游定制 Agent 生成 / 修订行程草案

    生成约束:
        - 先查询天气与日历
        - 每日景点间交通 ≤ 2.5 小时
        - 输出 Markdown 行程 + 预估费用
        - 首次生成 version += 1
    """

    result = await _agent.plan(state)

    # 更新 draft
    draft = result.get("draft")
    if draft is not None:
        # 首次生成 version += 1
        if not state.draft.itinerary_md:
            draft.version = state.draft.version + 1
        else:
            draft.version = state.draft.version  # 追问不增加版本

    return {
        "draft": draft,
        "need": result.get("need", state.need),
        "final_reply": result.get("reply", ""),
        "messages": result.get("messages", []),
    }
