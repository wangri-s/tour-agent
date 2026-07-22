"""工作记忆层 (Working Memory) — Kafka 驱动

负责:
- Agent 事件发布/订阅
- 异步任务分发
- 跨 Agent 消息传递
- 分析埋点

数据生命周期: 实时流式，消息保留 7 天
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from services.kafka_broker import kafka_broker, Topic, EventType

logger = logging.getLogger(__name__)


class WorkingMemory:
    """工作记忆 — 事件流与异步协调"""

    def __init__(self):
        self._broker = kafka_broker

    # =========================================================================
    # Agent 事件
    # =========================================================================

    async def record_intent(
        self,
        session_id: str,
        customer_id: str,
        intent_scores: dict[str, float],
        routed_to: str,
    ) -> None:
        """记录意图识别结果"""
        await self._broker.emit_intent_detected(
            session_id, customer_id, intent_scores, routed_to
        )

    async def record_trip_generated(
        self,
        session_id: str,
        customer_id: str,
        destination: str,
        days: int,
        estimated_cost: float,
    ) -> None:
        """记录行程生成完成"""
        await self._broker.emit_trip_generated(
            session_id, customer_id, destination, days, estimated_cost
        )

    async def record_handoff(
        self,
        session_id: str,
        customer_id: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """记录转人工事件"""
        await self._broker.emit_human_handoff(
            session_id, customer_id, reason, context
        )

    async def record_error(
        self,
        session_id: str,
        agent_name: str,
        error_msg: str,
        detail: str = "",
    ) -> None:
        """记录错误事件"""
        await self._broker.emit_error(
            session_id, agent_name, error_msg, detail
        )

    async def record_event(
        self,
        event_type: str,
        session_id: str,
        customer_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> None:
        """记录通用事件"""
        await self._broker.publish_event(
            Topic.AGENT_EVENTS,
            event_type,
            payload=payload,
            session_id=session_id,
            customer_id=customer_id,
            agent_name=agent_name,
        )

    # =========================================================================
    # 异步任务
    # =========================================================================

    async def enqueue_crm_sync(
        self,
        customer_id: str,
        action: str,
        data: dict[str, Any],
    ) -> None:
        """CRM 同步任务 (写入 Salesforce/HubSpot)"""
        await self._broker.enqueue_crm_sync(customer_id, action, data)

    async def enqueue_capi_send(
        self,
        customer_id: str,
        event_name: str,
        event_data: dict[str, Any],
    ) -> None:
        """广告转化回传 (Meta CAPI / Google Ads / TikTok)"""
        await self._broker.enqueue_capi_send(customer_id, event_name, event_data)

    async def enqueue_notification(
        self,
        customer_id: str,
        channel: str,
        content: dict[str, Any],
    ) -> None:
        """通知发送任务 (邮件/短信/推送)"""
        await self._broker.enqueue_task(
            Topic.NOTIFICATIONS,
            f"notification.{channel}",
            payload={"customer_id": customer_id, "channel": channel, "content": content},
        )

    async def enqueue_analytics(
        self,
        event_name: str,
        properties: dict[str, Any],
        session_id: str = "",
        customer_id: str = "",
    ) -> None:
        """分析埋点"""
        await self._broker.track_analytics(
            event_name, properties, session_id, customer_id
        )

    # =========================================================================
    # 订阅
    # =========================================================================

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        group_id: str = "tour-agent",
    ) -> bool:
        """订阅事件 Topic"""
        return await self._broker.subscribe(topic, handler, group_id)

    async def start_workers(self, topics: list[str] | None = None) -> None:
        """启动工作线程 (消费循环)"""
        await self._broker.start_consuming(topics)
