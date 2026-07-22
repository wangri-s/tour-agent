"""State 与路由单元测试"""

import pytest
from graph.state import TripNeed, TripDraft, OverallState, Quote, Branch, IntentLevel, NextAction
from graph.routing import route_after_intent, route_after_service, route_after_sales, route_requirements, route_revision


class TestTripNeed:
    """TripNeed 必填项检查"""

    def test_complete_need(self):
        need = TripNeed(
            destination="北京",
            days=5,
            arrival_date="2026-09-01",
            pax=2,
            budget_per_person=8000,
        )
        assert need.is_complete() is True
        assert need.missing_fields() == []

    def test_incomplete_need(self):
        need = TripNeed(destination="北京")
        assert need.is_complete() is False
        missing = need.missing_fields()
        assert "天数 (days)" in missing
        assert "抵达日期 (arrival_date)" in missing
        assert "人数 (pax)" in missing
        assert "人均预算 (budget_per_person)" in missing

    def test_partial_need(self):
        need = TripNeed(destination="上海", days=3)
        missing = need.missing_fields()
        assert len(missing) == 3
        assert "天数 (days)" not in missing
        assert "目的地 (destination)" not in missing


class TestRouting:
    """条件边路由逻辑"""

    def _state(self, **kwargs):
        """快捷构造 State"""
        defaults = {
            "messages": [],
            "session_id": "s1",
            "customer_id": "c1",
            "channel": "web",
            "language": "zh",
            "current_branch": "service",
            "need": TripNeed(),
            "draft": TripDraft(),
            "revision_count": 0,
            "intent_level": "",
            "need_human": False,
            "next_action": "",
            "final_reply": "",
        }
        defaults.update(kwargs)
        return OverallState(**defaults)

    def test_route_intent_to_planner(self):
        state = self._state(current_branch="planner")
        assert route_after_intent(state) == "trip_planner"

    def test_route_intent_human(self):
        state = self._state(need_human=True)
        assert route_after_intent(state) == "human_handoff"

    def test_route_service_end(self):
        state = self._state(final_reply="已回答")
        assert route_after_service(state) == "END"

    def test_route_service_human(self):
        state = self._state(need_human=True, current_branch="service")
        assert route_after_service(state) == "human_handoff"

    def test_route_sales_high(self):
        state = self._state(intent_level="high")
        assert route_after_sales(state) == "quote_agent"

    def test_route_sales_mid(self):
        state = self._state(intent_level="mid")
        assert route_after_sales(state) == "operations_agent"

    def test_route_requirements_incomplete(self):
        state = self._state()
        assert route_requirements(state) == "trip_planner"

    def test_route_requirements_complete(self):
        need = TripNeed(destination="北京", days=3, arrival_date="2026-09-01", pax=2, budget_per_person=5000)
        draft = TripDraft(itinerary_md="## 行程...")
        state = self._state(need=need, draft=draft)
        assert route_requirements(state) == "intent_scorer"

    def test_route_revision_revise(self):
        state = self._state(next_action="revise", revision_count=0)
        assert route_revision(state) == "revision_loop"

    def test_route_revision_max(self):
        state = self._state(next_action="revise", revision_count=3)
        assert route_revision(state) == "operations_agent"

    def test_route_revision_accept(self):
        state = self._state(next_action="accept")
        assert route_revision(state) == "quote_agent"


class TestGraphBuild:
    """Graph 编译测试"""

    def test_build_graph(self):
        from graph.builder import build_graph
        graph = build_graph()
        assert graph is not None
        # 验证节点存在
        nodes = graph.get_graph().nodes
        assert "input_guard" in nodes
        assert "intent_router" in nodes
        assert "trip_planner" in nodes
