"""会话初始化节点 —— 读取跨会话记忆与历史画像"""

from __future__ import annotations

from graph.state import OverallState, PartialState


async def session_context(state: OverallState) -> PartialState:
    """从 Redis / DB 加载历史会话上下文

    TODO MVP 阶段: 内存实现；第三阶段接入 Redis
    """
    updates: PartialState = {}

    # ---- 语言兜底 ----
    if not state.language:
        updates["language"] = "zh"

    # ---- 会话 ID 兜底 ----
    if not state.session_id:
        import uuid
        updates["session_id"] = str(uuid.uuid4())

    # ---- 修订次数重置 (新会话) ----
    # (首次进入时已为 0，此处保留扩展点)

    return updates
