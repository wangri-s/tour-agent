"""CRM 写入工具 —— 同步客户画像与会话结果"""

from langchain_core.tools import tool


@tool
async def update_crm(
    customer_id: str,
    channel: str = "",
    need: dict | None = None,
    draft: dict | None = None,
    intent_level: str = "",
    revision_count: int = 0,
    final_reply: str = "",
) -> str:
    """写入客户画像与会话结果到 CRM

    Args:
        customer_id: 客户唯一标识
        channel: 来源渠道
        need: 行程需求 dict
        draft: 行程草案 dict
        intent_level: 意向等级
        revision_count: 修订次数
        final_reply: 最终回复

    Returns:
        "ok" 或错误信息
    """
    # TODO: 接入真实 CRM API (Salesforce / HubSpot / 自建 CRM)
    import json
    import logging

    logger = logging.getLogger(__name__)

    payload = {
        "customer_id": customer_id,
        "channel": channel,
        "need": need,
        "draft": draft,
        "intent_level": intent_level,
        "revision_count": revision_count,
        "final_reply": final_reply[:500],  # 截断
    }

    logger.info(f"[CRM] write: {json.dumps(payload, ensure_ascii=False)[:200]}...")
    return "ok"
