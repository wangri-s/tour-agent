"""长时记忆层 (Long-Term Memory) — MySQL 驱动

负责:
- 会话消息归档 (永久)
- 客户画像持久化 (永久)
- 行程记录 CRUD
- Agent 事件持久备份
- RAG 质量反馈收集
- 知识库元数据

数据生命周期: 永久 (可归档/备份)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.mysql_store import mysql_store

logger = logging.getLogger(__name__)


class LongTermMemory:
    """长时记忆 — 持久化存储"""

    def __init__(self):
        self._store = mysql_store

    # =========================================================================
    # 会话消息
    # =========================================================================

    async def save_message(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        channel: str = "web",
        language: str = "zh",
        branch: str = "",
        intent_scores: dict | None = None,
        metadata: dict | None = None,
    ) -> int:
        """归档单条消息"""
        return await self._store.save_message(
            session_id, customer_id, role, content,
            channel, language, branch, intent_scores, metadata,
        )

    async def get_conversation(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取会话历史"""
        return await self._store.get_conversation(session_id, limit)

    async def get_customer_sessions(
        self,
        customer_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取客户所有会话摘要"""
        return await self._store.get_customer_sessions(customer_id, limit)

    # =========================================================================
    # 客户画像
    # =========================================================================

    async def save_profile(
        self,
        customer_id: str,
        name: str = "",
        nationality: str = "",
        preferred_language: str = "zh",
        contact_email: str = "",
        contact_phone: str = "",
        preferences: dict | None = None,
        tags: list[str] | None = None,
        notes: str = "",
    ) -> int:
        """保存/更新客户画像"""
        return await self._store.upsert_customer_profile(
            customer_id=customer_id,
            name=name,
            nationality=nationality,
            preferred_language=preferred_language,
            contact_email=contact_email,
            contact_phone=contact_phone,
            preferences=preferences,
            tags=tags,
            notes=notes,
        )

    async def get_profile(self, customer_id: str) -> dict[str, Any] | None:
        """获取客户画像"""
        return await self._store.get_customer_profile(customer_id)

    async def update_activity(self, customer_id: str) -> None:
        """更新客户最后活动时间"""
        await self._store.update_customer_activity(customer_id)

    # =========================================================================
    # 行程
    # =========================================================================

    async def save_trip(self, trip: dict[str, Any]) -> int:
        """保存/更新行程"""
        return await self._store.save_trip(trip)

    async def get_trip(self, trip_uid: str) -> dict[str, Any] | None:
        """获取行程"""
        return await self._store.get_trip(trip_uid)

    async def get_customer_trips(
        self,
        customer_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取客户的所有行程"""
        return await self._store.get_customer_trips(customer_id, status, limit)

    async def update_trip_status(self, trip_uid: str, status: str) -> None:
        """更新行程状态"""
        await self._store.update_trip_status(trip_uid, status)

    # =========================================================================
    # 事件持久
    # =========================================================================

    async def save_event(
        self,
        event_id: str,
        event_type: str,
        session_id: str,
        customer_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> int:
        """持久化 Agent 事件"""
        return await self._store.save_event(
            event_id, event_type, session_id, customer_id, agent_name, payload
        )

    async def get_session_events(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取会话事件流"""
        return await self._store.get_session_events(session_id, limit)

    # =========================================================================
    # RAG 反馈
    # =========================================================================

    async def save_rag_feedback(
        self,
        query: str,
        retrieved_docs: list[dict],
        was_helpful: bool | None = None,
        user_feedback: str = "",
        session_id: str = "",
    ) -> int:
        """保存 RAG 检索反馈 (用于质量评估)"""
        return await self._store.save_faq_feedback(
            query, retrieved_docs, was_helpful, user_feedback, session_id
        )

    async def get_rag_stats(self, days: int = 7) -> dict[str, Any]:
        """获取 RAG 质量统计"""
        return await self._store.get_rag_stats(days)

    # =========================================================================
    # 中期记忆摘要持久化
    # =========================================================================

    async def save_summary(
        self, session_id: str, round_range: str, summary: str, round_count: int = 0
    ) -> int:
        """持久化中期摘要到 MySQL"""
        if not self._store._pool:
            return 0
        return await self._store._execute(
            "INSERT INTO session_summaries (session_id, round_range, summary, round_count) "
            "VALUES (%s, %s, %s, %s)",
            (session_id, round_range, summary, round_count),
        )

    async def get_summaries(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的中期摘要列表"""
        if not self._store._pool:
            return []
        return await self._store._fetch(
            "SELECT round_range, summary, round_count, created_at "
            "FROM session_summaries WHERE session_id = %s ORDER BY id",
            (session_id,),
        )

    async def count_rounds(self, session_id: str) -> int:
        """从 conversations 表计算实际对话轮数 (user 消息数)"""
        if not self._store._pool:
            return 0
        rows = await self._store._fetch(
            "SELECT COUNT(*) AS cnt FROM conversations "
            "WHERE session_id = %s AND role = 'user'",
            (session_id,),
        )
        return rows[0]["cnt"] if rows else 0

    # =========================================================================
    # 统计
    # =========================================================================

    async def get_dashboard(self) -> dict[str, Any]:
        """仪表盘统计"""
        return await self._store.get_dashboard_stats()
