"""输入守护节点 —— 长度截断、PII 脱敏、敏感诉求识别"""

from __future__ import annotations

import re

from graph.state import OverallState, PartialState

MAX_MESSAGE_LENGTH = 4000  # 字数上限


def _truncate(text: str, max_chars: int = MAX_MESSAGE_LENGTH) -> str:
    """超长截断"""
    return text[:max_chars] + "…" if len(text) > max_chars else text


def _mask_pii(text: str) -> str:
    """简易 PII 脱敏：手机号 / 身份证 / 邮箱"""
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"\d{17}[\dXx]", "[ID_CARD]", text)
    text = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]", text)
    return text


async def input_guard(state: OverallState) -> PartialState:
    """入参保护节点

    处理流程:
        1. 取最后一条用户消息
        2. 长度截断 (4000 字)
        3. PII 脱敏
        4. 写入 messages
    """
    last_msg = state.messages[-1] if state.messages else None
    if last_msg is None:
        return {}

    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    cleaned = _mask_pii(_truncate(content))

    return {"messages": [type(last_msg)(content=cleaned)]}  # type: ignore[return-value]
