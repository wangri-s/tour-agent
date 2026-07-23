"""旅游定制 Agent —— 完整工具调用链 + 结构化行程生成 (RAG 增强版)

流程:
    1. 意图识别 → 获取用户需求 (目的地/天数/日期/人数/预算)
    2. 并行查询天气 (get_weather) + 日历 (query_calendar)
    3. RAG 语义检索知识库 (rag_search) → 城市指南/美食/交通/文化
    4. 查询库存 (query_inventory) → 酒店/门票/车辆
    5. 综合生成 Markdown 行程草案 (qwen-max)

与旧版区别: 知识检索从关键词匹配(search_faq)升级为 RAG 语义搜索(rag_search),
    Milvus 不可用时自动回退到关键词匹配。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import BaseAgent
from prompts.trip_planner import TRIP_PLANNER_PROMPT
from graph.state import OverallState, TripDraft, TripNeed
from tools.get_weather import get_weather
from tools.query_calendar import query_calendar
from tools.query_inventory import query_inventory
from tools.rag_search import rag_search
from services.llm_gateway import gateway_planner, gateway_router

logger = logging.getLogger(__name__)


class TripPlannerAgent(BaseAgent):
    """旅游定制核心 Agent

    使用 qwen-max 做复杂推理 + 多工具编排，
    生成包含每日行程、费用预估、天气提醒、实用贴士的完整草案。
    """

    def __init__(self):
        super().__init__(name="trip_planner")
        # 使用旗舰模型
        self.llm = gateway_planner
        self.tools = [get_weather, query_calendar, query_inventory, rag_search]

    def system_prompt(self) -> str:
        return TRIP_PLANNER_PROMPT

    async def plan(self, state: OverallState | dict) -> dict[str, Any]:
        """主规划流程 —— 六步生成完整行程

        Step 1: 解析需求 (从 State 或最新消息中提取)
        Step 2: 并行查询天气 + 日历 + 知识库
        Step 3: 查询酒店/门票库存
        Step 4: 组装上下文，调用 qwen-max 生成行程
        Step 5: 解析输出为 TripDraft
        Step 6: 返回

        Returns:
            {"draft": TripDraft, "need": TripNeed, "reply": str, "messages": [...]}
        """

        # 标准化 state (支持 dict 和对象两种形式)
        s = self._normalize_state(state)

        # =====================================================================
        # Step 1: 提取 / 补全需求
        # =====================================================================
        raw_need = s["need"]
        need = raw_need if isinstance(raw_need, TripNeed) else TripNeed(**raw_need)
        raw_draft = s.get("draft", {})
        draft = raw_draft if isinstance(raw_draft, TripDraft) else TripDraft(**raw_draft)
        last_msg = s["messages"][-1].content if s["messages"] else ""

        # 如果必填项不完整，先做需求提取
        if not need.is_complete():
            logger.info("[TripPlanner] 必填项不完整，提取需求...")
            need = await self._extract_needs(last_msg, s["need"])
            if not need.is_complete():
                # 返回追问
                missing = need.missing_fields()
                reply = self._build_followup(need, missing)
                return {
                    "draft": s["draft"],
                    "need": need,
                    "reply": reply,
                    "messages": [],
                }

        logger.info(
            f"[TripPlanner] 开始规划: {need.destination} "
            f"{need.days}天 {need.pax}人 "
            f"¥{need.budget_per_person}/人 "
            f"{need.arrival_date}"
        )

        # =====================================================================
        # Step 2: 并行查询天气 + 日历 + RAG 知识库
        # =====================================================================
        weather_data = await get_weather.ainvoke({"city": need.destination, "date": need.arrival_date})
        calendar_data = await query_calendar.ainvoke({"date": need.arrival_date})
        faq_data = await rag_search.ainvoke({"query": f"{need.destination} 旅游指南 美食 景点 交通", "top_k": 3})

        logger.info(f"[TripPlanner] 天气: {weather_data[:200]}")
        logger.info(f"[TripPlanner] 日历: {calendar_data[:200]}")

        # =====================================================================
        # Step 3: 查询库存
        # =====================================================================
        budget_level = self._map_budget(need.budget_per_person)
        inventory_data = await query_inventory.ainvoke({
            "city": need.destination,
            "date": need.arrival_date,
            "pax": need.pax,
            "budget_level": budget_level,
        })

        logger.info(f"[TripPlanner] 库存: {inventory_data[:200]}")

        # =====================================================================
        # Step 4: 组装上下文 → qwen-max 生成行程
        # =====================================================================
        draft = s["draft"]
        context = {
            "destination": need.destination,
            "days": need.days,
            "arrival_date": need.arrival_date,
            "pax": need.pax,
            "budget_per_person": need.budget_per_person,
            "budget_level": budget_level,
            "theme": need.theme or "综合体验",
            "pace": need.pace or "适中",
            "language": s["language"],
            "special_requests": need.special_requests,
            "is_revision": draft.itinerary_md != "",
            "revision_feedback": last_msg if draft.itinerary_md else "",
            # 工具返回数据
            "weather": weather_data,
            "calendar": calendar_data,
            "faq": faq_data,
            "inventory": inventory_data,
        }

        prompt = self._build_generation_prompt(context)
        messages = [{"role": "user", "content": prompt}]

        # 调用旗舰模型 (qwen-max)
        result = await self.llm.chat(
            system=self.system_prompt(),
            messages=messages,
            temperature=0.8,
            max_tokens=8000,
        )

        itinerary_md = result.get("content", "")

        logger.info(f"[TripPlanner] 行程生成完成, 长度: {len(itinerary_md)} 字符")

        # =====================================================================
        # Step 5: 解析 TripDraft
        # =====================================================================
        draft = self._parse_draft(itinerary_md, weather_data, need, s)

        # 生成回复摘要
        reply = self._build_reply(draft, need, weather_data, calendar_data)

        return {
            "draft": draft,
            "need": need,
            "reply": reply,
            "messages": [],
        }

    # =========================================================================
    # 辅助方法
    # =========================================================================

    @staticmethod
    def _normalize_state(state: OverallState | dict) -> dict:
        """标准化 state — 支持 dict 和 LangGraph State 对象，补全默认值"""
        # 补全默认值
        defaults = {
            "need": TripNeed(),
            "draft": TripDraft(),
            "language": "zh",
            "session_id": "",
            "customer_id": "",
            "channel": "web",
            "current_branch": "",
            "revision_count": 0,
            "intent_level": "",
            "need_human": False,
            "next_action": "",
            "final_reply": "",
        }
        if isinstance(state, dict):
            result = {**defaults, **state}
            return result
        # LangGraph 可能传入代理对象，尝试 dict 化，然后合并默认值
        try:
            raw = dict(state)
            return {**defaults, **raw}
        except Exception:
            raw = {k: getattr(state, k) for k in dir(state) if not k.startswith("_")}
            return {**defaults, **raw}

    async def _extract_needs(self, user_msg: str, existing: TripNeed) -> TripNeed:
        """用轻量模型从用户消息中提取结构化需求"""
        from datetime import date as dt_date
        today = dt_date.today().strftime("%Y-%m-%d")
        prompt = f"""从用户消息中提取旅游需求，返回 JSON。

今天是 {today}。用户只给了月份和日期(如10月20日)时，默认使用当年。如用户说"下个月"则推算到当月之后。

已有信息: {existing.model_dump_json()}

用户消息: {user_msg}

返回 JSON (只填能从消息中确定的字段):
{{
    "destination": "城市名(中文)",
    "days": 天数或0,
    "arrival_date": "YYYY-MM-DD格式，缺少年份时默认今年{today[:4]}年",
    "pax": 人数或0,
    "budget_per_person": 人均预算CNY或0,
    "theme": "主题偏好(历史文化/自然风光/美食/摄影/综合)或空",
    "pace": "节奏(轻松/适中/紧凑)或空",
    "special_requests": "特殊需求或空"
}}
"""

        try:
            result = await gateway_router.chat("", [{"role": "user", "content": prompt}], temperature=0.3)
            raw = result.get("content", "{}")
            # 提取 JSON
            if "{" in raw and "}" in raw:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                data = json.loads(raw[start:end])
                # 合并到已有 need
                updated = existing.model_dump()
                for key in ["destination", "arrival_date", "theme", "pace", "special_requests"]:
                    if data.get(key):
                        updated[key] = data[key]
                for key in ["days", "pax", "budget_per_person"]:
                    if data.get(key, 0) > 0:
                        updated[key] = data[key]
                return TripNeed(**updated)
        except Exception as e:
            logger.warning(f"[TripPlanner] 需求提取失败: {e}")

        return existing

    def _build_followup(self, need: TripNeed, missing: list[str]) -> str:
        """构建追问信息"""
        known_info = []
        if need.destination:
            known_info.append(f"目的地：{need.destination}")
        if need.days:
            known_info.append(f"天数：{need.days}天")
        if need.arrival_date:
            known_info.append(f"出发日期：{need.arrival_date}")
        if need.pax:
            known_info.append(f"人数：{need.pax}人")
        if need.budget_per_person:
            known_info.append(f"人均预算：¥{need.budget_per_person}")

        parts = []
        if known_info:
            parts.append(f"好的！已了解到：{'，'.join(known_info)}。")
        parts.append(f"还需要确认以下信息：{'、'.join(missing)}。")
        parts.append("请告诉我这些细节，我就能为您定制行程啦！✈️")

        return "\n".join(parts)

    def _map_budget(self, amount: float) -> str:
        if amount <= 0:
            return "舒适"
        if amount < 1500:
            return "经济"
        elif amount < 3500:
            return "舒适"
        else:
            return "奢华"

    def _build_generation_prompt(self, ctx: dict) -> str:
        """构建行程生成提示"""
        return f"""请基于以下信息生成一份完整的 {ctx['destination']} {ctx['days']}日深度游行程：

## 客户需求
- 目的地: {ctx['destination']}
- 天数: {ctx['days']}天
- 日期: {ctx['arrival_date']}
- 人数: {ctx['pax']}人
- 人均预算: ¥{ctx['budget_per_person']} ({ctx['budget_level']}档)
- 主题偏好: {ctx['theme']}
- 节奏偏好: {ctx['pace']}
- 特殊需求: {ctx['special_requests'] or '无'}
{'⚠️ 这是修订请求，客户反馈: ' + ctx['revision_feedback'] if ctx['is_revision'] else ''}

## 目的地信息 (知识库)
{ctx['faq'][:2000]}

## 天气信息
{ctx['weather'][:1000]}

## 日历/拥挤度
{ctx['calendar'][:800]}

## 可用资源 (酒店/门票/车辆)
{ctx['inventory'][:1500]}

---

## 生成要求

请用 Markdown 格式生成行程，包含以下部分：

### 1. 行程概览
简短引言 + 本次旅行亮点总结(3-5条)

### 2. 每日详细行程 (Day 1 ~ Day N)
每天包含：
- **主题** (如"古都探秘")
- **上午** (1-2个景点 + 时间安排，8:00-12:00)
- **午餐推荐** (具体餐厅名或美食街)
- **下午** (1-2个景点 + 时间安排，13:00-17:00)
- **晚餐推荐**
- **住宿建议**
- **交通提示** (景点间距离/车程)
- **小贴士** (注意事项/拍照点/预约提醒)

### 3. 费用预估
| 项目 | 单价 | 天数/次数 | 小计 |
|------|------|-----------|------|
| 🏨 酒店 | ¥X/晚 | X晚 | ¥X |
| ✈️ 机票(国际段) | ¥X | 往返 | ¥X |
| 🚗 交通(市内) | ¥X/天 | X天 | ¥X |
| 🎫 门票 | ¥X | 全部 | ¥X |
| 🍜 餐饮 | ¥X/天 | X天 | ¥X |
| 👨‍💼 导游(如需) | ¥X/天 | X天 | ¥X |
| **💰 总计/人** | | | **¥X** |

### 4. 天气与穿衣建议
基于查询到的实际天气数据

### 5. 实用贴士
- 预约提醒 (哪些景点需提前预约，提前几天)
- 交通攻略 (如何到达各景点)
- 美食清单 (必吃推荐 Top 5)
- 文化礼仪提醒
- 应急信息

## 约束
- 每天景点间交通 ≤ 2.5 小时
- 上午安排体力消耗大的景点
- 每2天安排一段自由活动时间
- 预算与{ctx['budget_level']}档匹配
- 输出为纯 Markdown，便于直接发送给客户"""

    def _parse_draft(self, md: str, weather_data: str, need: TripNeed, state: dict) -> TripDraft:
        """从 LLM 输出解析 TripDraft，提取费用和摘要"""
        import re

        # 提取总费用
        estimated_cost = 0.0
        total_match = re.search(r"(?:总计|总费用|人均总).*?[¥￥]\s*([\d,]+)", md)
        if not total_match:
            total_match = re.search(r"\*\*.*?[¥￥]\s*([\d,]+)\*\*", md)
        if total_match:
            try:
                estimated_cost = float(total_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 提取每日亮点 (Day X: xxx)
        highlights = re.findall(r"Day\s*\d+.*?[:：]\s*(.+?)(?:\n|$)", md)

        # 提取天气摘要
        weather_summary = ""
        try:
            import json as _json
            w = _json.loads(weather_data)
            weather_summary = f"{w.get('suitable', '')}，{w.get('temp_low', '')}~{w.get('temp_high', '')}°C，{w.get('advice', '')}"
        except Exception:
            weather_summary = "见行程详情"

        draft_obj = state.get("draft", TripDraft())
        version = draft_obj.version + (1 if not draft_obj.itinerary_md else 0)

        return TripDraft(
            version=version,
            itinerary_md=md,
            estimated_cost=estimated_cost,
            weather_summary=weather_summary,
            highlights=highlights[:need.days] if highlights else [],
            daily_notes=[f"Day {i+1}" for i in range(need.days)],
        )

    def _build_reply(
        self, draft: TripDraft, need: TripNeed,
        weather_data: str, calendar_data: str,
    ) -> str:
        """生成发送给客户的简短摘要"""
        parts = [f"为您定制了 **{need.destination} {need.days}日游** 行程 ✨\n"]

        # 天气提醒
        try:
            w = json.loads(weather_data)
            if w.get("rain_days_monthly", 0) >= 12:
                parts.append(f"🌧️ **天气提醒**：{need.destination}此时多雨，建议备好雨具。")
            elif w.get("temp_high", 20) >= 32:
                parts.append(f"☀️ **高温提醒**：气温达{w['temp_high']}°C，注意防晒补水。")
        except Exception:
            pass

        # 拥挤提醒
        try:
            c = json.loads(calendar_data)
            if c.get("is_holiday"):
                parts.append(f"⚠️ **节假日提醒**：{c.get('holiday_name')}期间出行，建议提前预订！")
        except Exception:
            pass

        if draft.estimated_cost > 0:
            parts.append(f"💰 预估人均费用：**¥{draft.estimated_cost:,.0f}**")

        parts.append(f"\n📋 行程已生成，包含{need.days}天详细安排。您可以：")
        parts.append('- ✅ **满意** → 回复「好的/可以/满意」，我为您生成报价单')
        parts.append('- 🔄 **修改** → 告诉我哪里需要调整（如「多加点美食」、「节奏太赶了」）')
        parts.append('- 📞 **人工** → 回复「转人工」，由旅行顾问接洽')

        return "\n".join(parts)
