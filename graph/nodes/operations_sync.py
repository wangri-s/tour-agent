"""终态数据汇聚节点 —— 强制 CRM 写入 + CAPI 回传"""

from __future__ import annotations

from typing import Any
from graph.state import OverallState, PartialState
from tools.update_crm import update_crm
from tools.send_capi import send_capi


def _g(state: Any, key: str, default: Any = None) -> Any:
    """安全获取 State 字段"""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


async def operations_sync(state: OverallState) -> PartialState:
    """终态汇聚节点

    强制执行:
        1. update_crm: 写入客户画像与会话结果
        2. send_capi:  回传 session_completed 事件到广告平台
    """

    # CRM 写入
    try:
        need = _g(state, "need")
        draft = _g(state, "draft")
        await update_crm.ainvoke({
            "customer_id": _g(state, "customer_id", ""),
            "channel": _g(state, "channel", ""),
            "need": need.model_dump() if hasattr(need, "model_dump") else need,
            "draft": draft.model_dump() if hasattr(draft, "model_dump") else draft,
            "intent_level": _g(state, "intent_level", ""),
            "revision_count": _g(state, "revision_count", 0),
            "final_reply": _g(state, "final_reply", ""),
        })
    except Exception:
        pass  # 非阻断

    # CAPI 回传
    try:
        await send_capi.ainvoke({
            "event": "session_completed",
            "customer_id": _g(state, "customer_id", ""),
            "channel": _g(state, "channel", ""),
            "branch": _g(state, "current_branch", ""),
            "intent_level": _g(state, "intent_level", ""),
        })
    except Exception:
        pass  # 非阻断

    return {}
