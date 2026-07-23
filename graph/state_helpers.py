"""State 访问辅助 —— 兼容 LangGraph TypedDict (dict) 和对象两种形式"""

from __future__ import annotations
from typing import Any


def sget(state: Any, key: str, default: Any = None) -> Any:
    """安全获取 State 字段，兼容 dict 和对象"""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def smsgs(state: Any) -> list:
    """获取 messages 列表"""
    return sget(state, "messages", [])


def sneed(state: Any):
    """获取 TripNeed"""
    return sget(state, "need")


def sdraft(state: Any):
    """获取 TripDraft"""
    return sget(state, "draft")
