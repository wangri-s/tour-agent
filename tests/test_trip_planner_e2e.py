"""端到端测试 —— 旅游定制 Agent 完整链路验证

运行方式:
    cd e:\Desktop\ai\旅游多agent
    python tests/test_trip_planner_e2e.py

测试流程:
    1. 意图识别 (qwen-turbo)
    2. 需求提取
    3. 天气查询
    4. 日历查询
    5. 库存查询
    6. 知识库检索
    7. 行程生成 (qwen-max)
    8. 结构化输出 TripDraft
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging

# 把项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("e2e-test")

# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "北京5日经典游",
        "message": "我想去北京玩5天，2个人，9月15号出发，人均预算8000，喜欢历史文化",
        "expected_branch": "planner",
        "expected_destination": "北京",
        "expected_days": 5,
    },
    {
        "name": "成都美食+熊猫3日",
        "message": "想去成都看熊猫和吃火锅，3天，1个人，10月20号，预算3000",
        "expected_branch": "planner",
        "expected_destination": "成都",
        "expected_days": 3,
    },
    {
        "name": "西安兵马俑+华山4日",
        "message": "西安4日游，2人，11月8日出发，人均6000，想去兵马俑和华山",
        "expected_branch": "planner",
        "expected_destination": "西安",
        "expected_days": 4,
    },
    {
        "name": "FAQ客服测试",
        "message": "中国签证怎么办理？需要什么材料？",
        "expected_branch": "service",
    },
    {
        "name": "桂林山水4日",
        "message": "桂林阳朔4天，2人，9月20号，人均5000，喜欢自然风光",
        "expected_branch": "planner",
        "expected_destination": "桂林",
        "expected_days": 4,
    },
]


async def test_intent_router():
    """测试意图路由器"""
    from agents.intent_router import IntentRouterAgent

    router = IntentRouterAgent()
    logger.info("=" * 60)
    logger.info("🧭 测试意图路由器 (qwen-turbo)")
    logger.info("=" * 60)

    for tc in TEST_CASES:
        result = await router.classify(tc["message"])
        branch = result["branch"]
        scores = result.get("scores", {})
        status = "✅" if branch == tc["expected_branch"] else "⚠️"
        logger.info(
            f"{status} [{tc['name']}] → {branch} "
            f"(expected: {tc['expected_branch']}) "
            f"scores={json.dumps(scores, ensure_ascii=False)}"
        )


async def test_trip_planner_full():
    """测试旅游定制完整链路"""
    from graph.state import OverallState, TripNeed
    from agents.trip_planner import TripPlannerAgent
    from langchain_core.messages import HumanMessage

    agent = TripPlannerAgent()
    logger.info("=" * 60)
    logger.info("🗺️  测试旅游定制 Agent (qwen-max)")
    logger.info("=" * 60)

    for tc in TEST_CASES:
        if tc["expected_branch"] != "planner":
            continue

        logger.info(f"\n{'─' * 50}")
        logger.info(f"📋 [{tc['name']}]")
        logger.info(f"   消息: {tc['message']}")

        state = OverallState(
            session_id=f"test-{tc['name']}",
            customer_id="test-customer",
            channel="web",
            language="zh",
            messages=[HumanMessage(content=tc["message"])],
        )

        try:
            result = await agent.plan(state)
        except Exception as e:
            logger.error(f"❌ 规划失败: {e}")
            continue

        draft = result.get("draft")
        reply = result.get("reply", "")
        need = result.get("need")

        # 验证
        checks = []
        if need:
            if need.destination == tc.get("expected_destination", need.destination):
                checks.append(f"目的地={need.destination} ✅")
            else:
                checks.append(f"目的地={need.destination} ⚠️ (expected {tc.get('expected_destination')})")

            if need.days == tc.get("expected_days"):
                checks.append(f"天数={need.days} ✅")
            else:
                checks.append(f"天数={need.days} ⚠️ (expected {tc.get('expected_days')})")

        if draft and draft.itinerary_md:
            md_len = len(draft.itinerary_md)
            checks.append(f"行程长度={md_len}字 ✅" if md_len > 500 else f"行程长度={md_len}字 ⚠️ (偏短)")
            if draft.estimated_cost > 0:
                checks.append(f"预估费用=¥{draft.estimated_cost:,.0f} ✅")

        logger.info(f"   Reply 预览: {reply[:200]}...")
        for c in checks:
            logger.info(f"   {c}")

        # 保存行程到文件
        if draft and draft.itinerary_md:
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.join(output_dir, f"{tc['name']}.md")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(draft.itinerary_md)
            logger.info(f"   💾 行程已保存: {filename}")


async def test_tools():
    """测试各工具独立运行"""
    from tools.get_weather import get_weather
    from tools.query_calendar import query_calendar
    from tools.query_inventory import query_inventory
    from tools.search_faq import search_faq

    logger.info("=" * 60)
    logger.info("🔧 测试工具层")
    logger.info("=" * 60)

    # 天气
    weather = await get_weather.ainvoke({"city": "北京", "date": "2026-09-15"})
    w = json.loads(weather)
    logger.info(f"🌤️  北京 9月: {w['temp_low']}~{w['temp_high']}°C, {w['suitable']}, {w['clothes']}")

    # 日历
    cal = await query_calendar.ainvoke({"date": "2026-09-15"})
    c = json.loads(cal)
    logger.info(f"📅 2026-09-15: 节假日={c['is_holiday']}, 周末={c['is_weekend']}, {c['travel_advice'][:60]}")

    cal_oct = await query_calendar.ainvoke({"date": "2026-10-01"})
    co = json.loads(cal_oct)
    logger.info(f"📅 2026-10-01: {co['holiday_name']}, {co['crowd_level'][:60]}")

    # 库存
    inv = await query_inventory.ainvoke({"city": "成都", "date": "2026-10-20", "pax": 2, "budget_level": "舒适"})
    i = json.loads(inv)
    logger.info(f"🏨 成都酒店: {len(i['hotels'])}家, 均价¥{i['summary']['avg_hotel_per_night']}/晚")
    logger.info(f"🎫 门票: {len(i['tickets'])}个, 均价¥{i['summary']['avg_ticket_per_attraction']}")
    logger.info(f"🚗 推荐车辆: {i['summary']['vehicle_recommended']} ¥{i['summary']['vehicle_price_per_day']}/天")

    # FAQ (关键词)
    faq = await search_faq.ainvoke({"query": "北京 故宫 预约", "top_k": 3})
    f = json.loads(faq)
    logger.info(f"📚 FAQ(关键词): {len(f)}条结果, Top: {f[0]['title'] if f else '无'}")

    # RAG (语义检索) — 自动降级到关键词
    from tools.rag_search import rag_search
    rag = await rag_search.ainvoke({"query": "北京有什么好玩的", "top_k": 3})
    r = json.loads(rag)
    rag_titles = [d.get("title", "") for d in r]
    logger.info(f"🔍 RAG: {len(r)}条结果, Titles: {rag_titles}")


async def main():
    logger.info("🚀 tour-agent 端到端测试开始")
    logger.info(f"Model Router: qwen-turbo")
    logger.info(f"Model Planner: qwen-max")

    # Step 1: 工具测试
    await test_tools()

    # Step 2: 意图路由测试
    await test_intent_router()

    # Step 3: 行程规划测试
    await test_trip_planner_full()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 端到端测试完成！")
    logger.info("📁 生成的行程已保存到 tests/output/")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
