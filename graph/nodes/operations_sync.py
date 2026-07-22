"""终态数据汇聚节点 —— 强制 CRM 写入 + CAPI 回传"""

from __future__ import annotations

from graph.state import OverallState, PartialState
from tools.update_crm import update_crm
from tools.send_capi import send_capi


async def operations_sync(state: OverallState) -> PartialState:
    """终态汇聚节点

    强制执行:
        1. update_crm: 写入客户画像与会话结果
        2. send_capi:  回传 session_completed 事件到广告平台
    """

    # CRM 写入
    try:
        await update_crm.ainvoke({
            "customer_id": state.customer_id,
            "channel": state.channel,
            "need": state.need.model_dump(),
            "draft": state.draft.model_dump(),
            "intent_level": state.intent_level,
            "revision_count": state.revision_count,
            "final_reply": state.final_reply,
        })
    except Exception:
        pass  # 非阻断

    # CAPI 回传
    try:
        await send_capi.ainvoke({
            "event": "session_completed",
            "customer_id": state.customer_id,
            "channel": state.channel,
            "branch": state.current_branch,
            "intent_level": state.intent_level,
        })
    except Exception:
        pass  # 非阻断

    return {}
