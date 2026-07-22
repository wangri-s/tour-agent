"""三层记忆编排器测试 — MemoryOrchestrator

运行方式:
    python tests/test_memory_orchestrator.py
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("orchestrator-test")


# =============================================================================
# Mock 测试
# =============================================================================

class TestMemoryOrchestrator:
    """编排器逻辑测试 (mock 全部底层服务)"""

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_startup_all_down(self, mock_redis, mock_kafka, mock_mysql):
        """全部服务不可用 → 不抛异常，返回状态"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=False)
        mock_kafka.connect = AsyncMock(return_value=False)
        mock_mysql.connect = AsyncMock(return_value=False)

        orchestrator = MemoryOrchestrator()
        # 阻止真实 Kafka 消费
        orchestrator._setup_event_bridge = AsyncMock()
        status = await orchestrator.startup()

        assert status == {"redis": False, "kafka": False, "mysql": False}
        assert orchestrator.is_ready is False
        logger.info("✅ 全部不可用 → 正常降级")

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_recall_context_redis_hit(self, mock_redis, mock_kafka, mock_mysql):
        """Redis 命中 → 直接返回，不查 MySQL"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=True)
        mock_redis._client = True
        mock_kafka.connect = AsyncMock(return_value=False)
        mock_mysql.connect = AsyncMock(return_value=False)

        orchestrator = MemoryOrchestrator()
        orchestrator._setup_event_bridge = AsyncMock()
        await orchestrator.startup()

        # 模拟 Redis 有数据
        expected_ctx = {"need": "test", "messages": [
            {"role": "user", "content": "hello"}
        ]}
        orchestrator.short.load_context = AsyncMock(return_value=expected_ctx)

        ctx = await orchestrator.recall_context("sess-001")
        assert ctx["need"] == "test"
        assert len(ctx["messages"]) == 1
        logger.info("✅ Redis 命中 → 返回")

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_recall_context_redis_miss_mysql_hit(
        self, mock_redis, mock_kafka, mock_mysql
    ):
        """Redis miss → MySQL 命中 → 回填 Redis"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=True)
        mock_redis._client = True
        mock_kafka.connect = AsyncMock(return_value=False)
        mock_kafka._producer = None
        mock_kafka._consumers = {}
        mock_mysql.connect = AsyncMock(return_value=True)
        mock_mysql._pool = True

        orchestrator = MemoryOrchestrator()
        orchestrator._setup_event_bridge = AsyncMock()
        await orchestrator.startup()

        # Redis 空
        orchestrator.short.load_context = AsyncMock(return_value={})
        orchestrator.short.add_message = AsyncMock()

        # MySQL 有数据
        mysql_messages = [
            {"role": "user", "content": "北京攻略", "branch": "planner", "created_at": "..."},
            {"role": "assistant", "content": "为您推荐...", "branch": "planner", "created_at": "..."},
        ]
        orchestrator.long.get_conversation = AsyncMock(return_value=mysql_messages)

        ctx = await orchestrator.recall_context("sess-001")
        assert len(ctx.get("messages", [])) == 2
        # 应回填到 Redis
        assert orchestrator.short.add_message.call_count == 2
        logger.info("✅ Redis miss → MySQL → 回填 Redis")

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_remember_message_three_layer(self, mock_redis, mock_kafka, mock_mysql):
        """记住消息 → 三层同时写入"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=True)
        mock_redis._client = True
        mock_kafka.connect = AsyncMock(return_value=True)
        mock_kafka._producer = MagicMock()  # 非 None → connected
        mock_kafka._consumers = {}
        mock_mysql.connect = AsyncMock(return_value=True)
        mock_mysql._pool = True

        orchestrator = MemoryOrchestrator()
        orchestrator._setup_event_bridge = AsyncMock()
        await orchestrator.startup()

        orchestrator.short.add_message = AsyncMock()
        orchestrator.working.record_event = AsyncMock()
        orchestrator.long.save_message = AsyncMock(return_value=1)

        await orchestrator.remember_message(
            session_id="sess-001",
            customer_id="c1",
            role="user",
            content="我想去北京",
            channel="web",
            language="zh",
            branch="planner",
        )

        # 验证三层都被调用
        orchestrator.short.add_message.assert_called_once()
        orchestrator.working.record_event.assert_called_once()
        orchestrator.long.save_message.assert_called_once()
        logger.info("✅ 三层同时写入")

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_remember_customer_write_through(self, mock_redis, mock_kafka, mock_mysql):
        """记住客户 → Redis 缓存 + MySQL 持久化"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=True)
        mock_redis._client = True
        mock_kafka.connect = AsyncMock(return_value=False)
        mock_kafka._producer = None
        mock_kafka._consumers = {}
        mock_mysql.connect = AsyncMock(return_value=True)
        mock_mysql._pool = True

        orchestrator = MemoryOrchestrator()
        orchestrator._setup_event_bridge = AsyncMock()
        await orchestrator.startup()

        orchestrator.short.cache_profile = AsyncMock()
        orchestrator.long.save_profile = AsyncMock(return_value=1)

        profile = {"name": "张三", "nationality": "新加坡"}
        await orchestrator.remember_customer("c1", profile)

        orchestrator.short.cache_profile.assert_called_once()
        orchestrator.long.save_profile.assert_called_once()
        logger.info("✅ 客户画像写穿透")

    @patch("services.memory.orchestrator.mysql_store")
    @patch("services.memory.orchestrator.kafka_broker")
    @patch("services.memory.orchestrator.redis_cache")
    async def test_stats_when_mysql_up(self, mock_redis, mock_kafka, mock_mysql):
        """统计信息 — MySQL 可用时包含仪表盘数据"""
        from services.memory.orchestrator import MemoryOrchestrator

        mock_redis.connect = AsyncMock(return_value=True)
        mock_redis._client = True
        mock_kafka.connect = AsyncMock(return_value=False)
        mock_kafka._producer = None  # Mock 默认返回 MagicMock，需显式设为 None
        mock_kafka._consumers = {}
        mock_mysql.connect = AsyncMock(return_value=True)
        mock_mysql._pool = True

        orchestrator = MemoryOrchestrator()
        orchestrator._setup_event_bridge = AsyncMock()
        await orchestrator.startup()

        orchestrator.long.get_dashboard = AsyncMock(return_value={
            "total_conversations": 42,
            "total_customers": 10,
        })

        stats = await orchestrator.get_stats()
        assert stats["short_term"]["connected"] is True
        assert stats["working"]["connected"] is False
        assert stats["long_term"]["connected"] is True
        assert stats["dashboard"]["total_conversations"] == 42
        logger.info("✅ 统计信息")


# =============================================================================
# Main
# =============================================================================

async def main():
    logger.info("=" * 60)
    logger.info("🧪 三层记忆编排器测试")
    logger.info("=" * 60)

    test = TestMemoryOrchestrator()
    await test.test_startup_all_down()
    await test.test_recall_context_redis_hit()
    await test.test_recall_context_redis_miss_mysql_hit()
    await test.test_remember_message_three_layer()
    await test.test_remember_customer_write_through()
    await test.test_stats_when_mysql_up()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 编排器测试全部通过")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
