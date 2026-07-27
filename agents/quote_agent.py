"""报价 Agent —— 基于 draft 与 need 生成结构化报价单 (v2: 国内/入境自适应)"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import BaseAgent
from prompts.quote_agent import QUOTE_AGENT_PROMPT
from graph.state import OverallState, Quote

logger = logging.getLogger(__name__)


class QuoteAgent(BaseAgent):
    """生成分项报价：大交通、酒店、交通、门票、餐饮、导游"""

    def __init__(self):
        super().__init__(name="quote_agent")
        self.tools = []

    def system_prompt(self) -> str:
        return QUOTE_AGENT_PROMPT

    async def generate(self, state: OverallState) -> dict[str, Any]:
        """生成报价单

        Returns:
            {"quote": Quote | None, "reply": str, "messages": [...]}
        """
        s = state if isinstance(state, dict) else state.__dict__ if hasattr(state, '__dict__') else {}
        need = s.get("need") if isinstance(s, dict) else state.need
        draft = s.get("draft") if isinstance(s, dict) else state.draft

        need_data = need.model_dump() if hasattr(need, "model_dump") else (need.dict() if hasattr(need, "dict") else need)
        draft_data = draft.model_dump() if hasattr(draft, "model_dump") else (draft.dict() if hasattr(draft, "dict") else draft)

        total = draft_data.get("estimated_cost", 0) if isinstance(draft_data, dict) else getattr(draft, "estimated_cost", 0)
        days = need_data.get("days", 0) if isinstance(need_data, dict) else getattr(need, "days", 0)
        pax = need_data.get("pax", 1) if isinstance(need_data, dict) else getattr(need, "pax", 1)

        # 检测入境/国内：查找费用表中大交通那一行的内容
        itinerary = draft_data.get("itinerary_md", "") if isinstance(draft_data, dict) else getattr(draft, "itinerary_md", "")
        is_international = False
        for raw_line in itinerary.split("\n"):
            s = raw_line.strip()
            # 大交通行都在表格中，以 | 开头且含「大交通」
            if s.startswith("|") and "大交通" in s:
                is_international = "国际机票" in s or "国际航班" in s
                logger.info(f"[QuoteAgent] 大交通行: {s[:120]} → international={is_international}")
                break

        # 默认国内游：大交通 15%，酒店 50%
        # 入境游：国际机票 30%，酒店 35%
        flight_ratio = 0.30 if is_international else 0.15
        hotel_ratio = 0.35 if is_international else 0.50

        # 入境游：尝试获取实时/参考机票价格
        real_flight_price = None
        flight_price_source = ""
        if is_international:
            try:
                dest = need_data.get("destination", "") if isinstance(need_data, dict) else getattr(need, "destination", "")
                arrival = need_data.get("arrival_date", "") if isinstance(need_data, dict) else getattr(need, "arrival_date", "")

                # 1. 先查 Amadeus 实时 API (从主流出发城市)
                from mcp_servers.flight import get_flight_price, FALLBACK_FLIGHTS, get_airport_code

                dest_code = get_airport_code(dest) or ""
                # 尝试最可能的出发城市: 纽约→北京, 伦敦→北京, 东京→上海 等
                test_origins = ["纽约", "伦敦", "东京", "新加坡"]
                for origin_city in test_origins:
                    if get_airport_code(origin_city):
                        result = await get_flight_price(
                            origin=origin_city, destination=dest,
                            departure_date=arrival, adults=1,
                        )
                        if "flights" in result and result["flights"]:
                            real_flight_price = result["flights"][0]["price"]
                            flight_price_source = f"Amadeus实时 ({origin_city}→{dest})"
                            break
                        if "fallback" in result and "reference_price" in result["fallback"]:
                            if not real_flight_price:
                                real_flight_price = result["fallback"]["reference_price"]
                                flight_price_source = f"参考均价 ({origin_city}→{dest})"
                            break

                # 2. 没找到具体航线 → 取所有航线的中位数
                if not real_flight_price and dest_code:
                    prices = [v["price"] for k, v in FALLBACK_FLIGHTS.items() if dest_code in k]
                    if prices:
                        real_flight_price = sum(prices) / len(prices)
                        flight_price_source = f"航线均价 (飞{dest})"

                if real_flight_price:
                    logger.info(f"[QuoteAgent] 机票价: ¥{real_flight_price:.0f} ({flight_price_source})")

            except Exception as e:
                logger.debug(f"[QuoteAgent] 机票查询跳过: {e}")

        hotel_per_night = total * hotel_ratio / max(days, 1)
        flights = real_flight_price if real_flight_price else (total * flight_ratio)
        transport = total * 0.10
        tickets = total * 0.10
        meals = total * 0.10
        guide = total * 0.05
        calc_total = hotel_per_night * days + flights + transport + tickets + meals + guide

        quote = Quote(
            flights=round(flights),
            hotels=round(hotel_per_night * days),
            transport=round(transport),
            tickets=round(tickets),
            meals=round(meals),
            guide=round(guide),
            total=round(calc_total),
            notes="基于行程草案的预估报价，实际价格以预订时为准。4人以上可享团购优惠。",
        )

        transport_label = "✈️ 国际机票" if is_international else "🚄 高铁/动车"
        flight_note = ""
        if is_international and flight_price_source:
            flight_note = f" ({flight_price_source})"

        reply = (
            f"📊 **报价单**\n\n"
            f"| 项目 | 人均费用 |\n"
            f"|------|----------|\n"
            f"| {transport_label} | ¥{quote.flights:,}{flight_note} |\n"
            f"| 🏨 酒店({days}晚) | ¥{quote.hotels:,} |\n"
            f"| 🚗 市内交通 | ¥{quote.transport:,} |\n"
            f"| 🎫 景点门票 | ¥{quote.tickets:,} |\n"
            f"| 🍜 餐饮 | ¥{quote.meals:,} |\n"
            f"| 👨‍💼 导游 | ¥{quote.guide:,} |\n"
            f"| **💰 总计/人** | **¥{quote.total:,}** |\n\n"
            f"> 📝 {quote.notes}\n\n"
            f"满意此报价吗？回复「确认」即可进入下一步。"
        )

        print(f"[QUOTE-V2] international={is_international} flights={quote.flights} hotels={quote.hotels} total={quote.total}", flush=True)
        logger.info(f"[QuoteAgent] 生成报价: ¥{quote.total:,}/人 (international={is_international})")

        return {
            "quote": quote,
            "reply": reply,
            "messages": [],
        }
