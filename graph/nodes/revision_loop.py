"""修订循环节点 —— 计数器 +1"""

from __future__ import annotations

from graph.state import OverallState, PartialState


async def revision_loop(state: OverallState) -> PartialState:
    """修订计数器，每次进入 revision_count += 1

    硬上限 3 次，由 routing.revision_decision 条件边控制。
    """

    return {"revision_count": state.revision_count + 1}
