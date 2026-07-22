"""Kafka 消息队列 —— 工作记忆层 (Working Memory)

三层记忆中的「工作记忆」:
- Agent 事件流     (intent_detected / trip_generated / quote_created / human_handoff)
- 异步任务分发     (trip_generation / crm_sync / capi_send)
- 跨 Agent 通信    (planner → sales: 客户接受行程后传递)
- 数据分析管道     (analytics / user_behavior)

Topic 设计:
┌─────────────────────┬──────────┬──────────────────────────────────────┐
│ Topic               │ 分区数   │ 用途                                 │
├─────────────────────┼──────────┼──────────────────────────────────────┤
│ agent-events        │ 3        │ Agent 决策事件 (核心事件流)          │
│ trip-tasks          │ 3        │ 行程生成异步任务                     │
│ crm-sync            │ 1        │ CRM 同步 (Salesforce/HubSpot)       │
│ capi-send           │ 3        │ 广告转化回传 (Meta/Google/TikTok)   │
│ analytics           │ 3        │ 用户行为分析埋点                     │
│ notifications       │ 3        │ 邮件/短信/推送通知                   │
└─────────────────────┴──────────┴──────────────────────────────────────┘

架构位置: 协调层 — 连接短时记忆(Redis)和长时记忆(MySQL)
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
import uuid
from typing import Any, Callable, Awaitable
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# Topic 常量
# =============================================================================

class Topic:
    AGENT_EVENTS   = "agent-events"
    TRIP_TASKS     = "trip-tasks"
    CRM_SYNC       = "crm-sync"
    CAPI_SEND      = "capi-send"
    ANALYTICS      = "analytics"
    NOTIFICATIONS  = "notifications"


# =============================================================================
# 事件类型
# =============================================================================

class EventType:
    """Agent 事件类型枚举"""
    # 意图
    INTENT_DETECTED     = "intent_detected"
    INTENT_CONFIRMED    = "intent_confirmed"

    # 行程
    TRIP_REQUESTED      = "trip_requested"
    TRIP_GENERATED      = "trip_generated"
    TRIP_REVISED        = "trip_revised"
    TRIP_ACCEPTED       = "trip_accepted"

    # 报价
    QUOTE_CREATED       = "quote_created"
    QUOTE_ACCEPTED      = "quote_accepted"

    # 客服
    FAQ_SEARCHED        = "faq_searched"
    HUMAN_HANDOFF       = "human_handoff"

    # 会话
    SESSION_STARTED     = "session_started"
    SESSION_ENDED       = "session_ended"

    # 支付
    PAYMENT_INITIATED   = "payment_initiated"
    PAYMENT_COMPLETED   = "payment_completed"

    # 错误
    ERROR_OCCURRED      = "error_occurred"


class KafkaBroker:
    """Kafka 消息队列 — 工作记忆层

    使用 aiokafka 异步客户端，支持:
    - 生产者: 发布事件 / 异步任务
    - 消费者: 批量处理 + 手动提交 offset
    - 自动创建 topic
    """

    def __init__(self, bootstrap_servers: str | None = None):
        self.bootstrap = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self._producer: Any = None
        self._consumers: dict[str, Any] = {}
        self._running = False
        self._task_registry: dict[str, list[Callable]] = {}  # topic → handlers

    # =========================================================================
    # 连接管理
    # =========================================================================

    async def connect(self) -> bool:
        """建立 Kafka 连接"""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                compression_type="gzip",
                max_request_size=1048576,  # 1MB
            )
            await self._producer.start()
            logger.info(f"[Kafka] 连接成功 → {self.bootstrap}")
            return True

        except ImportError:
            logger.warning("[Kafka] aiokafka 未安装，工作记忆降级为同步模式")
            return False
        except Exception as e:
            logger.error(f"[Kafka] 连接失败: {e}")
            self._producer = None
            return False

    async def close(self) -> None:
        """关闭所有连接"""
        self._running = False

        # 停止消费者
        for topic, consumer in self._consumers.items():
            try:
                await consumer.stop()
                logger.info(f"[Kafka] Consumer 停止: {topic}")
            except Exception:
                pass
        self._consumers.clear()

        # 停止生产者
        if self._producer:
            try:
                await self._producer.stop()
                logger.info("[Kafka] Producer 停止")
            except Exception:
                pass
        self._producer = None

    # =========================================================================
    # 事件发布 (Producer)
    # =========================================================================

    async def publish_event(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str = "",
        customer_id: str = "",
        agent_name: str = "",
        key: str | None = None,
    ) -> bool:
        """发布 Agent 事件

        Args:
            topic:      Topic 名
            event_type: 事件类型 (EventType)
            payload:    事件负载
            session_id: 关联会话
            customer_id: 关联客户
            agent_name: 触发 Agent
            key:        分区键 (默认 session_id)

        Returns:
            是否发送成功
        """
        if not self._producer:
            logger.debug(f"[Kafka] Producer 不可用，跳过事件 {event_type}")
            return False

        event = {
            "event_id": uuid.uuid4().hex[:16],
            "event_type": event_type,
            "session_id": session_id,
            "customer_id": customer_id,
            "agent_name": agent_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }

        try:
            partition_key = key or session_id or event["event_id"]
            await self._producer.send_and_wait(topic, key=partition_key, value=event)
            logger.debug(f"[Kafka] 事件发布: {event_type} → {topic}")
            return True
        except Exception as e:
            logger.error(f"[Kafka] 事件发布失败 [{event_type}]: {e}")
            return False

    async def enqueue_task(
        self,
        topic: str,
        task_type: str,
        payload: dict[str, Any],
        session_id: str = "",
    ) -> bool:
        """异步任务入队 (发后即忘模式)"""
        if not self._producer:
            return False

        task = {
            "task_id": uuid.uuid4().hex[:16],
            "task_type": task_type,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }

        try:
            await self._producer.send(topic, key=session_id or task["task_id"], value=task)
            logger.debug(f"[Kafka] 任务入队: {task_type} → {topic}")
            return True
        except Exception as e:
            logger.error(f"[Kafka] 任务入队失败 [{task_type}]: {e}")
            return False

    # =========================================================================
    # 事件消费 (Consumer)
    # =========================================================================

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        group_id: str = "tour-agent",
    ) -> bool:
        """订阅 Topic 并注册处理器

        Args:
            topic:    Topic 名
            handler:  异步处理函数，接收事件 dict
            group_id: 消费组 ID
        """
        try:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap,
                group_id=group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                max_poll_records=50,
            )
            await consumer.start()
            self._consumers[topic] = consumer

            # 注册到 registry (用于统一启动)
            if topic not in self._task_registry:
                self._task_registry[topic] = []
            self._task_registry[topic].append(handler)

            logger.info(f"[Kafka] 订阅 {topic} (group={group_id})")
            return True

        except Exception as e:
            logger.error(f"[Kafka] 订阅失败 [{topic}]: {e}")
            return False

    async def start_consuming(self, topics: list[str] | None = None) -> None:
        """启动消费循环 (后台任务)"""
        if not self._consumers:
            logger.warning("[Kafka] 无消费者，跳过消费循环")
            return

        self._running = True
        consume_topics = topics or list(self._consumers.keys())

        logger.info(f"[Kafka] 开始消费: {consume_topics}")

        async def _consume_loop(topic: str, consumer: Any):
            handlers = self._task_registry.get(topic, [])
            while self._running:
                try:
                    async for msg in consumer:
                        if not self._running:
                            break
                        for handler in handlers:
                            try:
                                await handler(msg.value)
                            except Exception as e:
                                logger.error(f"[Kafka] Handler 异常 [{topic}]: {e}")
                        # 手动提交 offset
                        await consumer.commit()
                except Exception as e:
                    logger.error(f"[Kafka] 消费异常 [{topic}]: {e}, 3s 后重试")
                    await asyncio.sleep(3)

        tasks = []
        for topic in consume_topics:
            if topic in self._consumers:
                tasks.append(asyncio.create_task(
                    _consume_loop(topic, self._consumers[topic])
                ))

        if tasks:
            await asyncio.gather(*tasks)

    # =========================================================================
    # 便捷方法 — 常用事件发布
    # =========================================================================

    async def emit_intent_detected(
        self,
        session_id: str,
        customer_id: str,
        intent_scores: dict[str, float],
        branch: str,
    ) -> None:
        """意图识别完成"""
        await self.publish_event(
            Topic.AGENT_EVENTS,
            EventType.INTENT_DETECTED,
            payload={"intent_scores": intent_scores, "routed_to": branch},
            session_id=session_id,
            customer_id=customer_id,
            agent_name="intent_router",
        )

    async def emit_trip_generated(
        self,
        session_id: str,
        customer_id: str,
        destination: str,
        days: int,
        estimated_cost: float,
    ) -> None:
        """行程生成完成"""
        await self.publish_event(
            Topic.AGENT_EVENTS,
            EventType.TRIP_GENERATED,
            payload={
                "destination": destination,
                "days": days,
                "estimated_cost": estimated_cost,
            },
            session_id=session_id,
            customer_id=customer_id,
            agent_name="trip_planner",
        )

    async def emit_human_handoff(
        self,
        session_id: str,
        customer_id: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """转人工"""
        await self.publish_event(
            Topic.AGENT_EVENTS,
            EventType.HUMAN_HANDOFF,
            payload={"reason": reason, "context": context or {}},
            session_id=session_id,
            customer_id=customer_id,
            agent_name="human_handoff",
        )

    async def emit_error(
        self,
        session_id: str,
        agent_name: str,
        error_msg: str,
        error_detail: str = "",
    ) -> None:
        """错误事件"""
        await self.publish_event(
            Topic.AGENT_EVENTS,
            EventType.ERROR_OCCURRED,
            payload={"error": error_msg, "detail": error_detail},
            session_id=session_id,
            agent_name=agent_name,
        )

    async def enqueue_crm_sync(
        self,
        customer_id: str,
        action: str,
        data: dict[str, Any],
    ) -> None:
        """CRM 同步任务入队"""
        await self.enqueue_task(
            Topic.CRM_SYNC,
            f"crm.{action}",
            payload={"customer_id": customer_id, "action": action, "data": data},
        )

    async def enqueue_capi_send(
        self,
        customer_id: str,
        event_name: str,
        event_data: dict[str, Any],
    ) -> None:
        """CAPI 转化回传入队"""
        await self.enqueue_task(
            Topic.CAPI_SEND,
            f"capi.{event_name}",
            payload={"customer_id": customer_id, "event_name": event_name, "event_data": event_data},
        )

    async def enqueue_trip_generation(
        self,
        session_id: str,
        customer_id: str,
        trip_params: dict[str, Any],
    ) -> None:
        """异步行程生成任务"""
        await self.enqueue_task(
            Topic.TRIP_TASKS,
            "trip.generate",
            payload={"session_id": session_id, "customer_id": customer_id, "trip_params": trip_params},
            session_id=session_id,
        )

    async def track_analytics(
        self,
        event_name: str,
        properties: dict[str, Any],
        session_id: str = "",
        customer_id: str = "",
    ) -> None:
        """埋点事件"""
        await self.publish_event(
            Topic.ANALYTICS,
            event_name,
            payload=properties,
            session_id=session_id,
            customer_id=customer_id,
        )


# =============================================================================
# 预置实例
# =============================================================================

kafka_broker = KafkaBroker()
