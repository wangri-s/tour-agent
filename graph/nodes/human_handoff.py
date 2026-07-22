"""人工接管节点 —— 生成交接摘要，兜底转人工"""

from __future__ import annotations

from graph.state import OverallState, PartialState


async def human_handoff(state: OverallState) -> PartialState:
    """生成人工交接摘要并置 need_human = True"""

    summary_parts = [
        f"## 人工交接摘要",
        f"- 客户 ID: {state.customer_id}",
        f"- 来源渠道: {state.channel}",
        f"- 当前分支: {state.current_branch}",
        f"- 语言: {state.language}",
        f"",
        f"### 需求画像",
        f"- 目的地: {state.need.destination}",
        f"- 天数: {state.need.days}",
        f"- 抵达日期: {state.need.arrival_date}",
        f"- 人数: {state.need.pax}",
        f"- 人均预算: ¥{state.need.budget_per_person}",
        f"- 主题偏好: {state.need.theme}",
        f"- 节奏偏好: {state.need.pace}",
        f"",
        f"### 草案状态",
        f"- 版本: v{state.draft.version}",
        f"- 修订次数: {state.revision_count}",
        f"- 意向等级: {state.intent_level}",
        f"",
        f"### 最后消息",
        f"> {state.messages[-1].content if state.messages else '无'}",
        f"",
        f"### 跟进建议",
        f"- 意向 {state.intent_level}: " +
        ("建议销售立即跟进签约" if state.intent_level == "high" else "建议运营进行培育"),
    ]

    return {
        "need_human": True,
        "final_reply": "\n".join(summary_parts),
    }
