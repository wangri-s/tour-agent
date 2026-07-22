"""转人工评估工具 —— 关键词 + 复杂度评分"""

from langchain_core.tools import tool


@tool
async def check_handoff(user_message: str, conversation_turns: int = 0) -> str:
    """评估是否需要转人工

    Args:
        user_message: 用户最新消息
        conversation_turns: 当前会话轮次

    Returns:
        JSON: {"need_handoff": bool, "reason": str, "priority": "urgent"|"normal"}
    """
    import json

    high_priority_keywords = ["投诉", "退款", "差评", "complaint", "refund", "urgent"]
    medium_keywords = ["签证", "visa", "退改", "修改订单", "取消", "cancel"]

    msg_lower = user_message.lower()

    need = False
    reason = ""
    priority = "normal"

    if any(kw in msg_lower for kw in high_priority_keywords):
        need = True
        reason = "高优先级关键词命中"
        priority = "urgent"
    elif any(kw in msg_lower for kw in medium_keywords):
        need = True
        reason = "中优先级关键词命中"
        priority = "normal"
    elif conversation_turns > 6:
        need = True
        reason = "会话轮次超限"
        priority = "normal"

    return json.dumps({
        "need_handoff": need,
        "reason": reason,
        "priority": priority,
    }, ensure_ascii=False)
