"""MySQL 持久化存储 —— 长时记忆层 (Long-Term Memory)

三层记忆中的「长时记忆」:
- 会话消息归档     (conversations)
- 客户画像持久化   (customer_profiles)
- 行程记录         (trips)
- Agent 事件流     (agent_events, Kafka 的持久备份)
- RAG 反馈         (faq_feedback)
- 知识库元数据     (knowledge_docs)

与 Redis 短时记忆的配合:
- 写: Redis 先更新 → MySQL 异步写入 (Kafka 桥接)
- 读: Redis 命中直接返回 → miss 查 MySQL → 回填 Redis

架构: aiomysql 异步驱动 + 连接池 + 自动重连
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any
from datetime import datetime

try:
    import aiomysql
except ImportError:
    aiomysql = None  # type: ignore

logger = logging.getLogger(__name__)


class MySQLStore:
    """MySQL 长时记忆存储

    使用 aiomysql 异步驱动，连接池自动管理。
    所有 CRUD 方法自动处理 JSON 序列化。
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv(
            "MYSQL_URL",
            os.getenv("DATABASE_URL", "mysql://tourai:tourai123@localhost:3306/tourai"),
        )
        self._pool: Any = None

    # =========================================================================
    # 连接管理
    # =========================================================================

    async def connect(self) -> bool:
        """建立 MySQL 连接池"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(self.dsn)
            self._pool = await aiomysql.create_pool(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "tourai",
                password=parsed.password or "tourai123",
                db=(parsed.path[1:] if parsed.path else "tourai"),
                charset="utf8mb4",
                autocommit=True,
                minsize=2,
                maxsize=10,
                connect_timeout=5,
                pool_recycle=3600,
            )
            logger.info(f"[MySQL] 连接成功 → {parsed.hostname}:{parsed.port}")
            return True

        except ImportError:
            logger.warning("[MySQL] aiomysql 未安装，长时记忆降级")
            return False
        except Exception as e:
            logger.error(f"[MySQL] 连接失败: {e}")
            self._pool = None
            return False

    async def close(self) -> None:
        """关闭连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            logger.info("[MySQL] 连接池已关闭")
        self._pool = None

    async def _execute(self, sql: str, params: tuple | None = None) -> int:
        """执行写操作，返回 lastrowid"""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    return cur.lastrowid or 0
        except Exception as e:
            logger.error(f"[MySQL] 执行失败: {e}")
            return 0

    async def _fetch(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行查询，返回 dict 列表"""
        if not self._pool or aiomysql is None:
            return []
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, params)
                    return await cur.fetchall()
        except Exception as e:
            logger.error(f"[MySQL] 查询失败: {e}")
            return []

    async def _fetch_one(self, sql: str, params: tuple | None = None) -> dict[str, Any] | None:
        """执行查询，返回单行"""
        rows = await self._fetch(sql, params)
        return rows[0] if rows else None

    # =========================================================================
    # 会话消息 (Conversations)
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
        """保存单条消息"""
        return await self._execute(
            """INSERT INTO conversations
               (session_id, customer_id, channel, language, role, content, branch, intent_scores, metadata_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                session_id, customer_id, channel, language,
                role, content[:8000], branch or "",
                json.dumps(intent_scores, ensure_ascii=False) if intent_scores else None,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
            ),
        )

    async def get_conversation(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取会话历史"""
        return await self._fetch(
            """SELECT role, content, branch, created_at
               FROM conversations
               WHERE session_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (session_id, limit),
        )

    async def get_recent_messages(
        self,
        session_id: str,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """获取最近 N 条消息 (时间正序)"""
        rows = await self._fetch(
            """SELECT role, content, branch, created_at
               FROM conversations
               WHERE session_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (session_id, count),
        )
        return list(reversed(rows))

    async def get_customer_sessions(
        self,
        customer_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取客户的所有会话摘要"""
        return await self._fetch(
            """SELECT session_id, channel, language,
                    MIN(created_at) as started_at,
                    MAX(created_at) as last_active,
                    COUNT(*) as message_count
               FROM conversations
               WHERE customer_id = %s
               GROUP BY session_id, channel, language
               ORDER BY last_active DESC
               LIMIT %s""",
            (customer_id, limit),
        )

    # =========================================================================
    # 客户画像 (Customer Profiles)
    # =========================================================================

    async def upsert_customer_profile(
        self,
        customer_id: str,
        name: str = "",
        nationality: str = "",
        preferred_language: str = "zh",
        contact_email: str = "",
        contact_phone: str = "",
        preferences: dict | None = None,
        travel_history: dict | None = None,
        tags: list[str] | None = None,
        notes: str = "",
    ) -> int:
        """创建或更新客户画像"""
        return await self._execute(
            """INSERT INTO customer_profiles
               (customer_id, name, nationality, preferred_language,
                contact_email, contact_phone, preferences_json,
                travel_history_json, tags, notes, first_seen_at, last_seen_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
               ON DUPLICATE KEY UPDATE
                 name = VALUES(name),
                 nationality = VALUES(nationality),
                 preferred_language = VALUES(preferred_language),
                 contact_email = VALUES(contact_email),
                 contact_phone = VALUES(contact_phone),
                 preferences_json = VALUES(preferences_json),
                 travel_history_json = VALUES(travel_history_json),
                 tags = VALUES(tags),
                 notes = VALUES(notes),
                 last_seen_at = NOW()""",
            (
                customer_id, name, nationality, preferred_language,
                contact_email, contact_phone,
                json.dumps(preferences, ensure_ascii=False) if preferences else None,
                json.dumps(travel_history, ensure_ascii=False) if travel_history else None,
                json.dumps(tags, ensure_ascii=False) if tags else None,
                notes,
            ),
        )

    async def get_customer_profile(self, customer_id: str) -> dict[str, Any] | None:
        """获取客户画像"""
        row = await self._fetch_one(
            """SELECT * FROM customer_profiles WHERE customer_id = %s""",
            (customer_id,),
        )
        if not row:
            return None

        # 解析 JSON 字段
        for field in ["preferences_json", "travel_history_json", "tags"]:
            if row.get(field) and isinstance(row[field], str):
                try:
                    row[field] = json.loads(row[field])
                except json.JSONDecodeError:
                    pass

        # 时间字段转字符串
        for field in ["first_seen_at", "last_seen_at"]:
            if row.get(field) and hasattr(row[field], "isoformat"):
                row[field] = row[field].isoformat()

        return row

    async def update_customer_activity(self, customer_id: str) -> None:
        """更新客户最后活动时间"""
        await self._execute(
            """UPDATE customer_profiles SET last_seen_at = NOW() WHERE customer_id = %s""",
            (customer_id,),
        )

    # =========================================================================
    # 行程记录 (Trips)
    # =========================================================================

    async def save_trip(self, trip: dict[str, Any]) -> int:
        """保存/更新行程"""
        import uuid

        trip_uid = trip.get("trip_uid") or uuid.uuid4().hex[:16]
        return await self._execute(
            """INSERT INTO trips
               (trip_uid, customer_id, session_id, status, version,
                destination, days, arrival_date, pax, budget_per_person,
                theme, pace, special_requests, itinerary_md, estimated_cost,
                weather_summary, highlights_json, quote_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 status = VALUES(status),
                 version = VALUES(version),
                 itinerary_md = VALUES(itinerary_md),
                 estimated_cost = VALUES(estimated_cost),
                 weather_summary = VALUES(weather_summary),
                 highlights_json = VALUES(highlights_json),
                 quote_json = VALUES(quote_json),
                 updated_at = NOW()""",
            (
                trip_uid,
                trip.get("customer_id", ""),
                trip.get("session_id", ""),
                trip.get("status", "draft"),
                trip.get("version", 1),
                trip.get("destination", ""),
                trip.get("days", 0),
                trip.get("arrival_date"),
                trip.get("pax", 1),
                trip.get("budget_per_person", 0),
                trip.get("theme", ""),
                trip.get("pace", ""),
                trip.get("special_requests", ""),
                trip.get("itinerary_md", ""),
                trip.get("estimated_cost", 0),
                trip.get("weather_summary", ""),
                json.dumps(trip.get("highlights", []), ensure_ascii=False),
                json.dumps(trip.get("quote", {}), ensure_ascii=False),
            ),
        )

    async def get_trip(self, trip_uid: str) -> dict[str, Any] | None:
        """获取行程"""
        return await self._fetch_one(
            """SELECT * FROM trips WHERE trip_uid = %s""",
            (trip_uid,),
        )

    async def get_customer_trips(
        self,
        customer_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取客户的所有行程"""
        if status:
            return await self._fetch(
                """SELECT trip_uid, destination, days, status, version,
                          estimated_cost, created_at, updated_at
                   FROM trips
                   WHERE customer_id = %s AND status = %s
                   ORDER BY updated_at DESC
                   LIMIT %s""",
                (customer_id, status, limit),
            )
        return await self._fetch(
            """SELECT trip_uid, destination, days, status, version,
                      estimated_cost, created_at, updated_at
               FROM trips
               WHERE customer_id = %s
               ORDER BY updated_at DESC
               LIMIT %s""",
            (customer_id, limit),
        )

    async def update_trip_status(self, trip_uid: str, status: str) -> None:
        """更新行程状态"""
        await self._execute(
            """UPDATE trips SET status = %s, updated_at = NOW() WHERE trip_uid = %s""",
            (status, trip_uid),
        )

    # =========================================================================
    # Agent 事件 (Agent Events)
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
        """保存 Agent 事件"""
        return await self._execute(
            """INSERT INTO agent_events
               (event_id, event_type, session_id, customer_id, agent_name, payload_json)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE payload_json = VALUES(payload_json)""",
            (
                event_id, event_type, session_id, customer_id,
                agent_name,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

    async def get_session_events(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取会话的所有事件"""
        return await self._fetch(
            """SELECT event_type, agent_name, payload_json, created_at
               FROM agent_events
               WHERE session_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (session_id, limit),
        )

    # =========================================================================
    # FAQ / RAG 反馈
    # =========================================================================

    async def save_faq_feedback(
        self,
        query: str,
        retrieved_docs: list[dict],
        was_helpful: bool | None = None,
        user_feedback: str = "",
        session_id: str = "",
    ) -> int:
        """保存 RAG 检索反馈"""
        return await self._execute(
            """INSERT INTO faq_feedback
               (query, retrieved_docs, was_helpful, user_feedback, session_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                query,
                json.dumps(retrieved_docs, ensure_ascii=False),
                was_helpful,
                user_feedback,
                session_id,
            ),
        )

    async def get_rag_stats(self, days: int = 7) -> dict[str, Any]:
        """获取 RAG 质量统计"""
        row = await self._fetch_one(
            """SELECT
                 COUNT(*) as total_queries,
                 SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful,
                 SUM(CASE WHEN was_helpful = 0 THEN 1 ELSE 0 END) as not_helpful
               FROM faq_feedback
               WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)""",
            (days,),
        )
        if row:
            total = row["total_queries"] or 0
            helpful = row["helpful"] or 0
            return {
                "total_queries": total,
                "helpful": helpful,
                "not_helpful": row["not_helpful"] or 0,
                "helpful_rate": round(helpful / total, 2) if total > 0 else 0,
            }
        return {"total_queries": 0, "helpful": 0, "not_helpful": 0, "helpful_rate": 0}

    # =========================================================================
    # 知识库文档
    # =========================================================================

    async def save_knowledge_doc(
        self,
        doc_uid: str,
        title: str,
        category: str = "",
        source_file: str = "",
        chunk_count: int = 0,
        status: str = "active",
    ) -> int:
        """记录知识库文档"""
        return await self._execute(
            """INSERT INTO knowledge_docs
               (doc_uid, title, category, source_file, chunk_count, status)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 title = VALUES(title),
                 chunk_count = VALUES(chunk_count),
                 status = VALUES(status),
                 updated_at = NOW()""",
            (doc_uid, title, category, source_file, chunk_count, status),
        )

    async def list_knowledge_docs(
        self,
        category: str | None = None,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        """列出知识库文档"""
        if category:
            return await self._fetch(
                """SELECT * FROM knowledge_docs
                   WHERE category = %s AND status = %s
                   ORDER BY updated_at DESC""",
                (category, status),
            )
        return await self._fetch(
            """SELECT * FROM knowledge_docs
               WHERE status = %s
               ORDER BY updated_at DESC""",
            (status,),
        )

    # =========================================================================
    # 统计 & 批量
    # =========================================================================

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """获取仪表盘统计"""
        result = {
            "total_conversations": 0,
            "total_customers": 0,
            "total_trips": 0,
            "trips_by_status": {},
        }

        row = await self._fetch_one(
            """SELECT COUNT(DISTINCT session_id) as cnt FROM conversations"""
        )
        if row:
            result["total_conversations"] = row["cnt"] or 0

        row = await self._fetch_one(
            """SELECT COUNT(*) as cnt FROM customer_profiles"""
        )
        if row:
            result["total_customers"] = row["cnt"] or 0

        rows = await self._fetch(
            """SELECT status, COUNT(*) as cnt FROM trips GROUP BY status"""
        )
        result["trips_by_status"] = {r["status"]: r["cnt"] for r in rows}
        result["total_trips"] = sum(result["trips_by_status"].values())

        return result


# =============================================================================
# 预置实例
# =============================================================================

mysql_store = MySQLStore()

