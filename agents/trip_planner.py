"""旅游定制 Agent —— 根据需求生成可执行行程草案"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from prompts.trip_planner import TRIP_PLANNER_PROMPT
from graph.state import OverallState, TripDraft, TripNeed
from tools.get_weather import get_weather
from tools.query_calendar import query_calendar
from tools.query_inventory import query_inventory


class TripPlannerAgent(BaseAgent):
    """根据客户需求生成 Markdown 行程 + 预估费用

    生成约束:
        - 先查天气 + 日历
        - 每日景点间交通 ≤2.5 小时
        - 输出结构化 TripDraft
    """

    def __init__(self):
        super().__init__(name="trip_planner")
        self.tools = [get_weather, query_calendar, query_inventory]

    def system_prompt(self) -> str:
        return TRIP_PLANNER_PROMPT

    async def plan(self, state: OverallState) -> dict[str, Any]:
        """生成或修订行程

        Returns:
            {
                "draft": TripDraft,
                "need": TripNeed,
                "reply": str,
                "messages": [...],
            }
        """

        # 组装上下文
        context = {
            "need": state.need.model_dump(),
            "draft": state.draft.model_dump() if state.draft.itinerary_md else None,
            "language": state.language,
            "is_revision": state.draft.itinerary_md != "",
        }

        messages = [
            {"role": "user", "content": f"以下是客户需求与当前上下文，请生成行程：\n{context}"}
        ]

        result = await self.call_llm(messages, tools=self.tools)
        content = result.get("content", "")

        # 解析 LLM 输出为 TripDraft
        draft = self._parse_draft(content, state)

        return {
            "draft": draft,
            "need": state.need,
            "reply": content,
            "messages": [],
        }

    def _parse_draft(self, content: str, state: OverallState) -> TripDraft:
        """从 LLM 输出解析 TripDraft

        TODO MVP: 用结构化输出；此处先占位
        """
        return TripDraft(
            version=state.draft.version,
            itinerary_md=content,
            estimated_cost=0,
            weather_summary="",
        )
