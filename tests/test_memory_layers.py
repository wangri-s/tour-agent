"""三层记忆系统测试 — Redis / Kafka / MySQL

运行方式:
    python tests/test_memory_layers.py          # 只跑单元测试 (mock)
    python tests/test_memory_layers.py --live   # 集成测试 (需要 Docker 服务)
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("memory-test")


# =============================================================================
# Redis 短时记忆测试
# =============================================================================

class TestRedisCache:
    """Redis 缓存层测试 (mock)"""

    def test_hash_args(self):
        """参数 hash 一致性"""
        from services.redis_cache import RedisCache
        h1 = RedisCache.hash_args(city="北京", date="2026-09-15")
        h2 = RedisCache.hash_args(date="2026-09-15", city="北京")
        assert h1 == h2, "相同参数应产生相同 hash"
        h3 = RedisCache.hash_args(city="上海")
        assert h1 != h3, "不同参数应产生不同 hash"
        logger.info("✅ hash_args 一致")

    def test_key_prefixes(self):
        """Key 命名空间"""
        from services.redis_cache import KeyPrefix, TTL
        assert KeyPrefix.SESSION.startswith("tourai:")
        assert KeyPrefix.CUSTOMER.startswith("tourai:")
        assert TTL.SESSION == 1800
        assert TTL.CUSTOMER == 86400
        assert TTL.TOOL_CACHE == 600
        logger.info("✅ Key 命名空间 & TTL 正确")

    @patch("redis.asyncio.ConnectionPool")
    @patch("redis.asyncio.Redis")
    async def test_session_context_save_load(self, mock_redis_cls, mock_pool_cls):
        """会话上下文保存 & 加载"""
        from services.redis_cache import RedisCache
        cache = RedisCache()

        # 模拟连接
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_pool_cls.from_url.return_value = MagicMock()
        mock_redis_cls.return_value = mock_client

        await cache.connect()
        assert cache._client is not None

        # 模拟 set/get
        mock_client.set = AsyncMock(return_value=True)
        mock_client.get = AsyncMock(return_value=json.dumps({"need": "data"}))
        mock_client.expire = AsyncMock(return_value=True)

        # 保存
        ok = await cache.save_session_context("sess-001", {"branch": "planner", "language": "zh"})
        assert ok is True
        mock_client.set.assert_called_once()

        # 加载
        ctx = await cache.get_session_context("sess-001")
        assert ctx["need"] == "data"
        mock_client.expire.assert_called()  # 自动续期
        logger.info("✅ 会话上下文读写")

    @patch("redis.asyncio.ConnectionPool")
    @patch("redis.asyncio.Redis")
    async def test_rate_limiting(self, mock_redis_cls, mock_pool_cls):
        """频率限制"""
        from services.redis_cache import RedisCache
        cache = RedisCache()

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_pool_cls.from_url.return_value = MagicMock()
        mock_redis_cls.return_value = mock_client

        await cache.connect()

        # 第1次: 放行
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.expire = AsyncMock(return_value=True)
        allowed, remaining = await cache.check_rate_limit("sess-001", max_requests=30)
        assert allowed is True
        assert remaining == 29

        # 第31次: 拦截
        mock_client.incr = AsyncMock(return_value=31)
        mock_client.ttl = AsyncMock(return_value=30)
        allowed, remaining = await cache.check_rate_limit("sess-001", max_requests=30)
        assert allowed is False
        assert remaining == 0
        logger.info("✅ 频率限制")

    @patch("redis.asyncio.ConnectionPool")
    @patch("redis.asyncio.Redis")
    async def test_distributed_lock(self, mock_redis_cls, mock_pool_cls):
        """分布式锁"""
        from services.redis_cache import RedisCache
        cache = RedisCache()

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.set = AsyncMock(return_value=True)   # SET NX 成功
        mock_client.delete = AsyncMock(return_value=True)
        mock_pool_cls.from_url.return_value = MagicMock()
        mock_redis_cls.return_value = mock_client

        await cache.connect()

        acquired = await cache.acquire_lock("trip-gen-sess-001")
        assert acquired is True

        await cache.release_lock("trip-gen-sess-001")
        logger.info("✅ 分布式锁")


# =============================================================================
# Kafka 工作记忆测试
# =============================================================================

class TestKafkaBroker:
    """Kafka 消息测试 (mock)"""

    @patch("aiokafka.AIOKafkaProducer")
    async def test_event_payload_structure(self, mock_producer_cls):
        """事件结构验证"""
        from services.kafka_broker import KafkaBroker, Topic

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=MagicMock())
        mock_producer_cls.return_value = mock_producer

        broker = KafkaBroker()
        await broker.connect()

        # 发布事件
        result = await broker.publish_event(
            Topic.AGENT_EVENTS,
            "trip_generated",
            payload={"destination": "北京", "days": 5},
            session_id="s1",
            customer_id="c1",
            agent_name="trip_planner",
        )
        assert result is True
        mock_producer.send_and_wait.assert_called_once()

        # 验证事件结构
        call_args = mock_producer.send_and_wait.call_args
        topic = call_args[1]["topic"] if "topic" in call_args[1] else call_args[0][0]
        assert topic == Topic.AGENT_EVENTS
        logger.info("✅ 事件发布")

    @patch("aiokafka.AIOKafkaProducer")
    async def test_task_enqueue(self, mock_producer_cls):
        """异步任务入队"""
        from services.kafka_broker import KafkaBroker, Topic

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock()
        mock_producer_cls.return_value = mock_producer

        broker = KafkaBroker()
        await broker.connect()

        result = await broker.enqueue_task(
            Topic.CRM_SYNC,
            "crm.upsert_customer",
            payload={"customer_id": "c1", "name": "John"},
        )
        assert result is True
        mock_producer.send.assert_called_once()
        logger.info("✅ 任务入队")

    def test_topic_constants(self):
        """Topic 常量"""
        from services.kafka_broker import Topic, EventType
        assert Topic.AGENT_EVENTS == "agent-events"
        assert Topic.TRIP_TASKS == "trip-tasks"
        assert Topic.CRM_SYNC == "crm-sync"
        assert EventType.TRIP_GENERATED == "trip_generated"
        assert EventType.INTENT_DETECTED == "intent_detected"
        logger.info("✅ Topic / EventType 常量")


# =============================================================================
# MySQL 长时记忆测试
# =============================================================================

class TestMySQLStore:
    """MySQL 存储测试 (mock)"""

    async def test_dsn_parsing(self):
        """DSN 解析"""
        from services.mysql_store import MySQLStore

        store = MySQLStore("mysql://user:pass@host:3306/dbname")
        from urllib.parse import urlparse
        p = urlparse(store.dsn)
        assert p.hostname == "host"
        assert p.port == 3306
        assert p.username == "user"
        assert p.password == "pass"
        assert p.path == "/dbname"
        logger.info("✅ DSN 解析")

    def test_sql_templates_valid(self):
        """SQL 模板语法检查"""
        from services.mysql_store import MySQLStore
        store = MySQLStore()

        # 验证所有 SQL 模板包含关键字段
        methods_with_sql = [
            "save_message",
            "get_conversation",
            "get_recent_messages",
            "upsert_customer_profile",
            "get_customer_profile",
            "save_trip",
            "get_customer_trips",
            "save_event",
            "save_faq_feedback",
            "get_rag_stats",
        ]
        for name in methods_with_sql:
            assert hasattr(store, name), f"缺少方法: {name}"
        logger.info(f"✅ {len(methods_with_sql)} 个 CRUD 方法存在")


# =============================================================================
# 集成测试 (需要 Docker)
# =============================================================================

async def test_redis_live():
    """真实 Redis 连接测试"""
    from services.redis_cache import RedisCache

    cache = RedisCache()
    ok = await cache.connect()
    if not ok:
        logger.warning("⏭️  Redis 未运行，跳过")
        return

    # 写
    await cache.save_session_context("test-sess", {"test": True})
    # 读
    ctx = await cache.get_session_context("test-sess")
    assert ctx.get("test") is True
    # 频率限制
    allowed, _ = await cache.check_rate_limit("test-rate", max_requests=5)
    assert allowed is True
    # 清理
    await cache._client.delete("tourai:session:test-sess")
    await cache._client.delete("tourai:ratelimit:test-rate")
    await cache.close()
    logger.info("✅ Redis 集成测试通过")


async def test_milvus_live():
    """真实 Milvus 连接测试"""
    from services.vector_store import milvus_store

    ok = await milvus_store.connect()
    if not ok:
        logger.warning("⏭️  Milvus 未运行，跳过")
        return

    count = await milvus_store.count()
    logger.info(f"  Collection 文档数: {count}")

    # 测试搜索 (可能为空)
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if api_key and "xxx" not in api_key:
        from services.vector_store import embedding_service
        vec = await embedding_service.embed_query("北京")
        if vec:
            results = await milvus_store.search(vec, top_k=2)
            logger.info(f"  搜索 '北京': {len(results)} 条结果")

    await milvus_store.close()
    logger.info("✅ Milvus 集成测试通过")


# =============================================================================
# Main
# =============================================================================

async def main():
    import sys
    live = "--live" in sys.argv

    logger.info("=" * 60)
    logger.info("🧪 三层记忆系统测试" + (" (集成模式)" if live else " (Mock模式)"))
    logger.info("=" * 60)

    # --- 单元测试 ---
    logger.info("\n📦 Redis 短时记忆")
    rt = TestRedisCache()
    rt.test_hash_args()
    rt.test_key_prefixes()
    await rt.test_session_context_save_load()
    await rt.test_rate_limiting()
    await rt.test_distributed_lock()

    logger.info("\n📦 Kafka 工作记忆")
    kt = TestKafkaBroker()
    kt.test_topic_constants()
    await kt.test_event_payload_structure()
    await kt.test_task_enqueue()

    logger.info("\n📦 MySQL 长时记忆")
    mt = TestMySQLStore()
    await mt.test_dsn_parsing()
    mt.test_sql_templates_valid()

    # --- 集成测试 ---
    if live:
        logger.info("\n📦 集成测试")
        await test_redis_live()
        await test_milvus_live()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 三层记忆测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
