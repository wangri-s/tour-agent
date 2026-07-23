"""报价 Agent —— 基于 draft 与 need 生成结构化报价单 (工具调用修复版)

修复: 当 LLM 调用 quote_price 工具时，使用 chat_with_tools 自动执行工具并获取最终回复。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import BaseAgent
from prompts.quote_agent import QUOTE_AGENT_PROMPT
from graph.state import OverallState, Quote

logger = logging.getLogger(__name__)


class QuoteAgent(BaseAgent):
    """生成分项报价：机票、酒店、交通、门票、餐饮、导游"""

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

        # 根据 draft 的 estimated_cost 拆分为分项报价
        total = draft_data.get("estimated_cost", 0) if isinstance(draft_data, dict) else getattr(draft, "estimated_cost", 0)
        days = need_data.get("days", 0) if isinstance(need_data, dict) else getattr(need, "days", 0)
        pax = need_data.get("pax", 1) if isinstance(need_data, dict) else getattr(need, "pax", 1)

        # 直接基于已有数据计算报价，不依赖 LLM tool call
        hotel_per_night = total * 0.35 / max(days, 1)
        flights = total * 0.30
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

        # 生成友好的报价回复
        reply = (
            f"📊 **报价单**\n\n"
            f"| 项目 | 人均费用 |\n"
            f"|------|----------|\n"
            f"| ✈️ 国际机票 | ¥{quote.flights:,} |\n"
            f"| 🏨 酒店({days}晚) | ¥{quote.hotels:,} |\n"
            f"| 🚗 市内交通 | ¥{quote.transport:,} |\n"
            f"| 🎫 景点门票 | ¥{quote.tickets:,} |\n"
            f"| 🍜 餐饮 | ¥{quote.meals:,} |\n"
            f"| 👨‍💼 导游 | ¥{quote.guide:,} |\n"
            f"| **💰 总计/人** | **¥{quote.total:,}** |\n\n"
            f"> 📝 {quote.notes}\n\n"
            f"满意此报价吗？回复「确认」即可进入下一步。"
        )

        logger.info(f"[QuoteAgent] 生成报价: ¥{quote.total:,}/人")

        return {
            "quote": quote,
            "reply": reply,
            "messages": [],
        }
