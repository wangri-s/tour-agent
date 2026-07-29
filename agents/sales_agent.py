"""销售 Agent —— 产品推介、报价、签约引导、意向评分、套餐推荐

销售漏斗五阶段:
  意向确认 → 方案推荐 → 打消顾虑 → 促成签单 → 支付引导
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent, _normalize_role
from prompts.sales_agent import SALES_AGENT_PROMPT
from graph.state import OverallState, IntentLevel
from tools.quote_price import quote_price
from tools.query_inventory import query_inventory
from tools.package_search import search_tour_packages


class SalesAgent(BaseAgent):
    """主动引导客户完成产品销售

    根据客户所处漏斗阶段调整策略:
      - 高意向(已认可行程/问付款) → 促成签单+支付引导
      - 中意向(有兴趣但犹豫) → 打消顾虑+价值展示
      - 低意向(随便看看) → 提供价值+长期培育
    """

    def __init__(self):
        super().__init__(name="sales_agent")
        self.tools = [quote_price, query_inventory, search_tour_packages]

    def system_prompt(self) -> str:
        return SALES_AGENT_PROMPT

    async def handle(self, state: OverallState) -> dict[str, Any]:
        """处理销售对话

        从 state 中提取已有行程/报价信息，让 LLM 能基于上下文精准推荐。
        """

        msgs = state.get("messages", []) if isinstance(state, dict) else state.messages

        # 拼接上下文给 LLM：已有行程 + 报价 + 套餐
        enhanced_messages = list(msgs)

        # 1. 注入已有行程信息 (如果 trip_planner 已生成)
        need = state.get("need") if isinstance(state, dict) else getattr(state, "need", None)
        draft = state.get("draft") if isinstance(state, dict) else getattr(state, "draft", None)
        quote = state.get("quote") if isinstance(state, dict) else getattr(state, "quote", None)

        ctx_parts = []
        if need:
            need_dict = need if isinstance(need, dict) else (need.model_dump() if hasattr(need, "model_dump") else {})
            ctx_parts.append(
                f"[客户行程需求] "
                f"目的地={need_dict.get('destination','')}, "
                f"天数={need_dict.get('days',0)}天, "
                f"人数={need_dict.get('pax',0)}人, "
                f"预算={need_dict.get('budget_per_person',0)}元/人, "
                f"日期={need_dict.get('arrival_date','')}, "
                f"主题={need_dict.get('theme','未指定')}"
            )

        if draft:
            draft_dict = draft if isinstance(draft, dict) else (draft.model_dump() if hasattr(draft, "model_dump") else {})
            cost = draft_dict.get("estimated_cost", 0)
            ctx_parts.append(
                f"[已有行程草案] 预估费用=¥{cost}/人, "
                f"行程长度={len(draft_dict.get('itinerary_md',''))}字"
            )

        if quote:
            quote_dict = quote if isinstance(quote, dict) else (quote.model_dump() if hasattr(quote, "model_dump") else {})
            ctx_parts.append(f"[已有报价] 总价=¥{quote_dict.get('total',0)}/人")

        if ctx_parts:
            import json as _json
            ctx_msg = type('msg', (), {
                'type': 'system',
                'content': f"[销售上下文 — 已有客户数据]\n" + "\n".join(ctx_parts) +
                           "\n\n请基于以上信息进行个性化销售，优先推荐与客户需求匹配的套餐。"
            })()
            enhanced_messages = list(msgs[:-1]) + [ctx_msg, msgs[-1]] if len(msgs) > 1 else [ctx_msg] + list(msgs)

        # 构建消息列表
        recent = [
            {"role": _normalize_role(m), "content": m.content}
            for m in enhanced_messages[-15:]  # 多拿一些上下文
        ]

        result = await self.call_llm_stream(recent, tools=self.tools)
        content = result if isinstance(result, str) else result

        # 意向评分
        intent_level = self._score_intent(content)

        return {
            "reply": content,
            "intent_level": intent_level,
            "need_human": False,
            "messages": [],
        }

    def _score_intent(self, text: str) -> str:
        """基于客户消息+销售回复综合判断意向"""
        text_lower = text.lower()

        # 高意向：明确购买信号
        high_signals = [
            "签约", "支付", "定金", "确认预订", "就这个", "怎么付款",
            "下单", "锁定", "订了", "买了", "付了", "转了",
            "sign", "pay", "deposit", "book", "confirm",
        ]
        if any(kw in text_lower for kw in high_signals):
            return IntentLevel.HIGH.value

        # 中意向：有兴趣但犹豫
        mid_signals = [
            "考虑", "再看看", "优惠", "有点贵", "便宜", "对比",
            "能不能", "可以吗", "不错", "还行", "挺好的",
            "consider", "discount", "maybe", "later",
        ]
        if any(kw in text_lower for kw in mid_signals):
            return IntentLevel.MID.value

        # 低意向：随便看看
        return IntentLevel.LOW.value
