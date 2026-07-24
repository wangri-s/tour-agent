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
from services.memory.mid_term import MidTermMemory
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
        self.mid = MidTermMemory()
        self._ready = False
        self._llm = None  # 延迟注入，避免循环 import

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
    # 中期记忆 — 隔 5 轮压缩
    # =========================================================================

    COMPRESS_INTERVAL = 5  # 每 5 轮触发一次压缩

    async def inject_mid_term_context(self, session_id: str) -> str:
        """获取中期摘要，注入为 graph 上下文

        在 graph 调用前执行，返回 system 消息内容。
        """
        return await self.mid.get_recent_summaries(session_id, count=3)

    async def maybe_compress_mid_term(
        self,
        session_id: str,
        messages: list[dict[str, str]],
    ) -> str | None:
        """每 N 轮触发一次中期压缩

        触发逻辑:
          1. INCR 轮次计数器
          2. round == 1 且 MySQL 有旧历史 → 恢复
          3. round % 5 == 0 → 压缩最近 5 轮

        Returns:
            新生成的摘要文本 或 None (未触发)
        """
        # 延迟获取 LLM 网关 (避免循环 import)
        if self._llm is None:
            from services.llm_gateway import LLMGateway
            self._llm = LLMGateway(model="qwen-turbo")

        round_num = await self.short.increment_round(session_id)

        # ---- 场景 1: 计数器过期，首次访问 ----
        if round_num == 1:
            await self._recover_if_needed(session_id)

        # ---- 场景 2: 正常触发压缩 ----
        if round_num % self.COMPRESS_INTERVAL != 0:
            return None

        start_round = round_num - self.COMPRESS_INTERVAL + 1
        range_label = f"{start_round}-{round_num}"

        # 取最近 N 轮的消息 (N*2 条: user + assistant)
        recent = messages[-(self.COMPRESS_INTERVAL * 2):]

        # 获取上一段摘要用于合并
        prev_summary = await self.mid.get_latest_summary(session_id)

        # 调 LLM 生成摘要
        summary = await self._generate_round_summary(recent, prev_summary, range_label)
        if not summary:
            return None

        # 持久化到 Redis + MySQL
        await self.mid.save_summary(session_id, summary, range_label)
        await self.long.save_summary(session_id, range_label, summary, round_num)

        logger.info(
            "[MidTerm] 第%s轮压缩完成: %d条消息 → %d字摘要 (Redis+MySQL)",
            range_label, len(recent), len(summary),
        )
        return summary

    async def _generate_round_summary(
        self,
        messages: list[dict[str, str]],
        prev_summary: str,
        range_label: str,
    ) -> str:
        """调 LLM 压缩最近 N 轮对话，合并旧摘要"""
        history = "\n".join(
            f"[{m.get('role', '?')}]: {m.get('content', '')[:300]}"
            for m in messages
        )

        merge_hint = ""
        if prev_summary:
            merge_hint = (
                f"已有的前期摘要:\n{prev_summary}\n\n"
                "请将上述已有摘要与新的对话历史合并为一段新的完整摘要。\n"
            )

        prompt = (
            f"请将以下对话压缩为简洁摘要，保留关键信息:\n\n"
            f"{merge_hint}"
            f"最近{self.COMPRESS_INTERVAL}轮对话 ({range_label}):\n"
            f"{history[:3000]}\n\n"
            "关键信息类别:\n"
            "1. 客户需求: 目的地、日期、人数、预算、偏好\n"
            "2. 已确认信息 vs 待确认信息\n"
            "3. 行程变更: 客户要求过什么修改\n"
            "4. 情绪变化: 满意度趋势\n"
            "5. 关键决策: 用户确认了什么\n\n"
            "请用中文输出，总长度不超过 200 字。"
        )

        try:
            result = await self._llm.chat(
                system="你是一个专业的对话摘要助手，擅长提取关键信息。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            return result.get("content", "")[:300]
        except Exception as e:
            logger.warning("[MidTerm] LLM 摘要生成失败: %s", e)
            return ""

    async def _recover_if_needed(self, session_id: str) -> None:
        """计数器过期后，从 MySQL 联表查询真实轮数并恢复摘要"""
        if not mysql_store._pool:
            return

        # 先查 MySQL 有无该会话的持久化摘要 (过期前写入的)
        db_summaries = await self.long.get_summaries(session_id)
        if db_summaries:
            # 有 MySQL 持久化摘要 → 回填到 Redis
            for s in db_summaries:
                await self.mid.save_summary(
                    session_id, s["summary"],
                    s.get("round_range", "历史"),
                )
            logger.info(
                "[MidTerm] 从 MySQL 恢复 %d 段摘要 → Redis",
                len(db_summaries),
            )
            # 恢复轮次计数器
            actual_rounds = await self.long.count_rounds(session_id)
            if actual_rounds > 0:
                client = self.short._cache._client
                if client:
                    from services.redis_cache import KeyPrefix, TTL
                    key = f"{KeyPrefix.ROUND}{session_id}"
                    await client.set(key, actual_rounds)
                    await client.expire(key, TTL.ROUND)
                    logger.info(
                        "[MidTerm] 从 MySQL 恢复轮次: %d 轮",
                        actual_rounds,
                    )
            return

        # 无持久化摘要 → 检查是否有旧对话历史需要首次压缩
        old_msgs = await self.long.get_conversation(session_id, limit=100)
        if not old_msgs:
            return  # 真的是新会话

        # 有旧历史 → 生成初始摘要
        formatted = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in old_msgs
        ]
        summary = await self.mid.recover_from_history(session_id, formatted, self._llm)
        # 同步写入 MySQL
        if summary:
            await self.long.save_summary(session_id, "历史", summary, len(old_msgs))

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
