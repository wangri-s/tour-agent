"""人工接管节点 —— 生成交接摘要，兜底转人工"""

from __future__ import annotations

from graph.state import OverallState, PartialState


async def human_handoff(state: OverallState) -> PartialState:
    """生成人工交接摘要并置 need_human = True"""

    # 兼容 dict 和对象两种 State 形式
    s = state if isinstance(state, dict) else dict(state)

    msgs = s.get("messages", [])
    need = s.get("need", {})
    draft = s.get("draft", {})

    summary_parts = [
        f"## 人工交接摘要",
        f"- 客户 ID: {s.get('customer_id', '')}",
        f"- 来源渠道: {s.get('channel', '')}",
        f"- 当前分支: {s.get('current_branch', '')}",
        f"- 语言: {s.get('language', 'zh')}",
        f"",
        f"### 需求画像",
        f"- 目的地: {need.destination if hasattr(need, 'destination') else need.get('destination', '')}",
        f"- 天数: {need.days if hasattr(need, 'days') else need.get('days', 0)}",
        f"- 抵达日期: {need.arrival_date if hasattr(need, 'arrival_date') else need.get('arrival_date', '')}",
        f"- 人数: {need.pax if hasattr(need, 'pax') else need.get('pax', 0)}",
        f"- 人均预算: ¥{need.budget_per_person if hasattr(need, 'budget_per_person') else need.get('budget_per_person', 0)}",
        f"- 主题偏好: {need.theme if hasattr(need, 'theme') else need.get('theme', '')}",
        f"- 节奏偏好: {need.pace if hasattr(need, 'pace') else need.get('pace', '')}",
        f"",
        f"### 草案状态",
        f"- 版本: v{draft.version if hasattr(draft, 'version') else draft.get('version', 0)}",
        f"- 修订次数: {s.get('revision_count', 0)}",
        f"- 意向等级: {s.get('intent_level', '')}",
        f"",
        f"### 最后消息",
        f"> {msgs[-1].content if msgs else '无'}",
        f"",
        f"### 跟进建议",
        f"- 意向 {s.get('intent_level', '')}: " +
        ("建议销售立即跟进签约" if s.get('intent_level') == "high" else "建议运营进行培育"),
    ]

    return {
        "need_human": True,
        "final_reply": "\n".join(summary_parts),
    }
