"""CAPI 事件回传工具 —— Meta / Google / TikTok"""

from langchain_core.tools import tool


@tool
async def send_capi(
    event: str,
    customer_id: str = "",
    channel: str = "",
    branch: str = "",
    intent_level: str = "",
) -> str:
    """回传转化事件到广告平台 (Conversions API)

    Args:
        event: 事件名 (session_started | draft_generated | quote_viewed | session_completed)
        customer_id: 客户标识
        channel: 来源渠道
        branch: 当前分支
        intent_level: 意向等级

    Returns:
        "ok" 或错误信息
    """
    # TODO: 接入真实 CAPI (Meta CAPI / Google Ads / TikTok Events API)
    import json
    import logging

    logger = logging.getLogger(__name__)

    payload = {
        "event": event,
        "customer_id": customer_id,
        "channel": channel,
        "branch": branch,
        "intent_level": intent_level,
        "timestamp": "NOW()",
    }

    # 渠道映射
    capi_targets = {
        "whatsapp": "meta",
        "messenger": "meta",
        "tiktok": "tiktok",
        "web": "google",
    }
    target = capi_targets.get(channel, "meta")

    logger.info(f"[CAPI → {target}]: {json.dumps(payload, ensure_ascii=False)[:200]}...")
    return "ok"
