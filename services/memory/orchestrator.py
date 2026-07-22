"""三层记忆编排器 — MemoryOrchestrator

统一对外接口，管理三层记忆的读写策略:

读取策略:
  1. 先查 Redis (短时记忆) → 命中直接返回
  2. miss → 查 MySQL (长时记忆)
  3. MySQL 有 → 回填 Redis 热缓存
  4. MySQL 无 → 返回空/默认值

写入策略:
  1. 立即写 Redis (短时记忆, 设置 TTL)
  2. 发布 Kafka 事件 (工作记忆, 异步处理)
  3. Kafka Consumer → 写入 MySQL (长时记忆, 持久化)

事件桥接:
  Kafka Consumer 订阅 agent-events → 自动持久化到 MySQL agent_events 表
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.memory.short_term import ShortTermMemory
from services.memory.working import WorkingMemory
from services.memory.long_term import LongTermMemory
from services.redis_cache import redis_cache
from services.kafka_broker import kafka_broker
from services.mysql_store import mysql_store

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    """三层记忆统一编排

    用法:
        memory = MemoryOrchestrator()

        # 启动 (连接所有服务)
        await memory.startup()

        # 保存会话消息 (全程自动三层分发)
        await memory.remember_message(session_id, customer_id, "user", "我想去北京")

        # 加载会话上下文 (Redis → MySQL 自动)
        ctx = await memory.recall_context(session_id)

        # 关闭
        await memory.shutdown()
    """

    def __init__(self):
        self.short = ShortTermMemory()
        self.working = WorkingMemory()
        self.long = LongTermMemory()
        self._ready = False

    # =========================================================================
    # 生命周期
    # =========================================================================

    async def startup(self) -> dict[str, bool]:
        """启动所有记忆层连接

        Returns:
            {"redis": True/False, "kafka": True/False, "mysql": True/False}
        """
        results = {
            "redis": False,
            "kafka": False,
            "mysql": False,
        }

        # Redis (非阻断)
        results["redis"] = await redis_cache.connect()

        # Kafka (非阻断)
        results["kafka"] = await kafka_broker.connect()

        # MySQL (非阻断)
        results["mysql"] = await mysql_store.connect()

        self._ready = any(results.values())

        connected = sum(1 for v in results.values() if v)
        logger.info(
            f"[Memory] 启动完成: {connected}/3 层可用 "
            f"(Redis={results['redis']}, Kafka={results['kafka']}, MySQL={results['mysql']})"
        )

        # 注册 Kafka → MySQL 桥接 (事件持久化)
        if results["kafka"] and results["mysql"]:
            await self._setup_event_bridge()

        return results

    async def shutdown(self) -> None:
        """关闭所有连接"""
        await redis_cache.close()
        await kafka_broker.close()
        await mysql_store.close()
        self._ready = False
        logger.info("[Memory] 已关闭")

    @property
    def is_ready(self) -> bool:
        return self._ready

    # =========================================================================
    # 核心内存操作
    # =========================================================================

    # --- 会话消息 ---

    async def remember_message(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        channel: str = "web",
        language: str = "zh",
        branch: str = "",
        intent_scores: dict | None = None,
    ) -> None:
        """记住一条消息 — 三层同步写入"""
        # L1: Redis 短时记忆 (热数据)
        await self.short.add_message(session_id, role, content)

        # L2: Kafka 工作记忆 (事件流)
        await self.working.record_event(
            event_type="message_received",
            session_id=session_id,
            customer_id=customer_id,
            agent_name=branch,
            payload={
                "role": role,
                "content": content[:200],  # 事件只存摘要
                "channel": channel,
                "language": language,
            },
        )

        # L3: MySQL 长时记忆 (归档) — 通过 Kafka 异步写入或直接写
        if mysql_store._pool:
            await self.long.save_message(
                session_id, customer_id, role, content,
                channel, language, branch, intent_scores,
            )

    async def recall_context(self, session_id: str) -> dict[str, Any]:
        """回忆会话上下文 — 两层读取 + 回填"""
        # L1: Redis
        ctx = await self.short.load_context(session_id)
        if ctx.get("messages"):
            return ctx

        # L2: MySQL fallback
        if mysql_store._pool:
            messages = await self.long.get_conversation(session_id, limit=10)
            if messages:
                # 回填 Redis
                for msg in reversed(messages):
                    await self.short.add_message(
                        session_id,
                        msg.get("role", "user"),
                        msg.get("content", ""),
                    )
                ctx["messages"] = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in reversed(messages)
                ]

        return ctx

    # --- 客户画像 ---

    async def remember_customer(
        self,
        customer_id: str,
        profile: dict[str, Any],
    ) -> None:
        """记住客户信息"""
        # L1: Redis 热缓存
        await self.short.cache_profile(customer_id, profile)

        # L2: 事件
        await self.working.record_event(
            event_type="profile_updated",
            session_id="",
            customer_id=customer_id,
            agent_name="memory",
            payload={"action": "upsert"},
        )

        # L3: MySQL 持久化
        if mysql_store._pool:
            await self.long.save_profile(
                customer_id=customer_id,
                name=profile.get("name", ""),
                nationality=profile.get("nationality", ""),
                preferred_language=profile.get("preferred_language", "zh"),
                contact_email=profile.get("contact_email", ""),
                contact_phone=profile.get("contact_phone", ""),
                preferences=profile.get("preferences"),
                tags=profile.get("tags"),
            )

    async def recall_customer(self, customer_id: str) -> dict[str, Any] | None:
        """回忆客户信息 — 两层读取"""
        # L1: Redis
        profile = await self.short.get_profile(customer_id)
        if profile:
            return profile

        # L2: MySQL
        if mysql_store._pool:
            profile = await self.long.get_profile(customer_id)
            if profile:
                # 回填 Redis
                await self.short.cache_profile(customer_id, profile)
            return profile

        return None

    # --- 行程 ---

    async def remember_trip(
        self,
        session_id: str,
        customer_id: str,
        trip: dict[str, Any],
    ) -> None:
        """记住行程"""
        # L1: Redis 草稿缓存
        await self.short.save_draft(session_id, trip)

        # L2: 事件
        await self.working.record_trip_generated(
            session_id,
            customer_id,
            trip.get("destination", ""),
            trip.get("days", 0),
            trip.get("estimated_cost", 0),
        )

        # L3: MySQL 持久化
        if mysql_store._pool:
            await self.long.save_trip({
                **trip,
                "customer_id": customer_id,
                "session_id": session_id,
            })

    async def recall_trip_draft(self, session_id: str) -> dict[str, Any]:
        """回忆行程草稿"""
        return await self.short.get_draft(session_id)

    # --- 通用事件 ---

    async def remember_event(
        self,
        event_type: str,
        session_id: str,
        customer_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> None:
        """记录 Agent 事件"""
        await self.working.record_event(
            event_type, session_id, customer_id, agent_name, payload
        )

    # --- RAG 反馈 ---

    async def remember_rag_feedback(
        self,
        query: str,
        docs: list[dict],
        was_helpful: bool | None = None,
        feedback: str = "",
        session_id: str = "",
    ) -> None:
        """记录 RAG 检索反馈"""
        if mysql_store._pool:
            await self.long.save_rag_feedback(
                query, docs, was_helpful, feedback, session_id
            )

    # =========================================================================
    # Kafka → MySQL 事件桥接
    # =========================================================================

    async def _setup_event_bridge(self) -> None:
        """注册 Kafka Consumer: agent-events → MySQL agent_events 表"""
        from services.kafka_broker import Topic

        async def persist_event(event: dict[str, Any]) -> None:
            """Kafka 事件 → MySQL 持久化"""
            try:
                await self.long.save_event(
                    event_id=event.get("event_id", ""),
                    event_type=event.get("event_type", ""),
                    session_id=event.get("session_id", ""),
                    customer_id=event.get("customer_id", ""),
                    agent_name=event.get("agent_name", ""),
                    payload=event.get("payload", {}),
                )
            except Exception as e:
                logger.error(f"[EventBridge] 持久化失败: {e}")

        # 注册 Kafka 消费
        success = await self.working.subscribe(
            Topic.AGENT_EVENTS,
            persist_event,
            group_id="tour-agent-memory",
        )
        if success:
            logger.info("[EventBridge] agent-events → MySQL 桥接已注册")

    # =========================================================================
    # 统计
    # =========================================================================

    async def get_stats(self) -> dict[str, Any]:
        """获取记忆系统统计"""
        stats = {
            "short_term": {
                "type": "redis",
                "connected": redis_cache._client is not None,
            },
            "working": {
                "type": "kafka",
                "connected": kafka_broker._producer is not None,
            },
            "long_term": {
                "type": "mysql",
                "connected": mysql_store._pool is not None,
            },
        }
        if mysql_store._pool:
            stats["dashboard"] = await self.long.get_dashboard()
        return stats


# =============================================================================
# 全局实例
# =============================================================================

memory = MemoryOrchestrator()
