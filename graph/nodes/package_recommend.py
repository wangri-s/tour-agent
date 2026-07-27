"""套餐推荐节点 — 行程生成后自动匹配推荐套餐

在 quote_agent 之后、operations_sync 之前执行。
从 draft/need 提取特征 → RAG语义搜套餐 → MySQL查详情 → 生成推荐文案
"""

from __future__ import annotations

from typing import Any

from graph.state import OverallState, PartialState
from agents.base import BaseAgent

_RECOMMEND_PROMPT = """你是一个旅游套餐推荐专家。根据客户的行程需求和检索到的套餐列表，推荐最合适的套餐。

## 推荐规则
1. 优先推荐与客户目的地完全匹配的套餐
2. 预算要匹配：推荐套餐的人均预算应在客户预算的 ±30% 范围内
3. 天数相近：推荐天数与客户行程差异不超过2天
4. 主题匹配：根据客户偏好推荐相应主题的套餐
5. 至少推荐2个套餐，最多推荐3个
6. 如果套餐库中没有完全匹配的，推荐最接近的并说明差异
7. 推荐时说明为什么适合客户

## 输出格式
以 Markdown 格式推荐，每条套餐包含：
- 套餐名称 + 编号
- 推荐理由（一句话）
- 价格区间 + 天数
- 核心亮点
- 与客户需求的匹配度说明
"""


class PackageRecommendAgent(BaseAgent):
    """套餐推荐 Agent — 基于行程特征推荐套餐"""

    def __init__(self):
        super().__init__(name="package_recommend")

    def system_prompt(self) -> str:
        return _RECOMMEND_PROMPT

    async def recommend(self, need: dict, draft: dict, packages_json: str) -> str:
        """基于行程需求推荐套餐

        Args:
            need: 客户行程需求
            draft: 行程草案
            packages_json: 检索到的套餐 JSON

        Returns:
            推荐文案
        """
        need_str = ""
        if isinstance(need, dict):
            need_str = (
                f"目的地: {need.get('destination','')}, "
                f"天数: {need.get('days',0)}天, "
                f"人数: {need.get('pax',0)}人, "
                f"人均预算: ¥{need.get('budget_per_person',0)}, "
                f"主题: {need.get('theme','未指定')}, "
                f"节奏: {need.get('pace','未指定')}"
            )

        prompt = f"""客户行程需求:
{need_str}

可选套餐列表:
{packages_json[:3000]}

请从上述套餐中推荐2-3个最合适的给客户。"""

        messages = [{"role": "user", "content": prompt}]
        result = await self.call_llm(messages, system=self.system_prompt())
        return result


_agent = PackageRecommendAgent()


async def package_recommend(state: OverallState) -> PartialState:
    """从行程草案中提取特征，搜索匹配套餐并生成推荐"""

    need = state.get("need") if isinstance(state, dict) else getattr(state, "need", None)
    draft = state.get("draft") if isinstance(state, dict) else getattr(state, "draft", None)
    final_reply = state.get("final_reply", "")

    if not need or not draft:
        return {"messages": []}

    # 提取特征
    dest = need.get("destination", "") if isinstance(need, dict) else getattr(need, "destination", "")
    days = need.get("days", 0) if isinstance(need, dict) else getattr(need, "days", 0)
    budget = need.get("budget_per_person", 0) if isinstance(need, dict) else getattr(need, "budget_per_person", 0)
    theme = need.get("theme", "") if isinstance(need, dict) else getattr(need, "theme", "")

    try:
        from tools.package_search import search_tour_packages

        # RAG + MySQL 联合查询
        packages_json = await search_tour_packages.ainvoke({
            "query": f"{dest} {theme}旅游",
            "city": dest,
            "days": days,
            "budget": budget,
            "top_k": 5,
        })

        if not packages_json or packages_json == "[]":
            return {"messages": []}

        # 解析套餐
        import json
        try:
            data = json.loads(packages_json)
            pkg_count = data.get("count", 0)
        except Exception:
            pkg_count = 0

        if pkg_count == 0:
            return {"messages": []}

        # 生成推荐文案
        rec_text = await _agent.recommend(need, draft, packages_json)

        # 追加到 final_reply
        sep = "\n\n---\n\n"
        new_reply = final_reply + sep + "📦 **为您匹配的精选套餐**\n\n" + rec_text

        return {
            "final_reply": new_reply,
            "messages": [],
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PackageRecommend] 推荐失败: {e}")
        return {"messages": []}
