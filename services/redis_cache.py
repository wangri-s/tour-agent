"""Redis 缓存服务 —— 短时记忆层 (Short-Term Memory)

三层记忆中的「短时记忆」:
- 会话上下文缓存     (TTL: 30min idle)
- 客户画像热数据     (TTL: 24h)
- 频率限制计数器     (TTL: 按窗口)
- Agent 临时状态     (TTL: 5min)
- 工具调用结果缓存   (TTL: 10min)

与 MySQL 长时记忆的配合:
- 读: Redis hit → 直接返回; miss → MySQL → 回填 Redis
- 写: Redis 立即更新 → 异步刷 MySQL (通过 Kafka)

架构: redis[hiredis] + 连接池 + 自动序列化
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
from typing import Any
from datetime import timedelta

logger = logging.getLogger(__name__)

# =============================================================================
# Key 前缀约定
# =============================================================================

class KeyPrefix:
    """Redis Key 命名空间"""
    SESSION     = "tourai:session:"       # 会话上下文: hash
    CUSTOMER    = "tourai:customer:"       # 客户画像: hash
    RATE_LIMIT  = "tourai:ratelimit:"      # 频率限制: string (counter)
    AGENT_STATE = "tourai:agent:"          # Agent 临时状态: string (json)
    TOOL_CACHE  = "tourai:tool:"           # 工具缓存: string (json)
    TRIP_DRAFT  = "tourai:draft:"          # 行程草稿缓存: string (json)
    LOCK        = "tourai:lock:"           # 分布式锁: string
    MID_TERM    = "tourai:mid:"            # 中期记忆摘要: list
    ROUND       = "tourai:round:"          # 轮次计数器: string (int)


# =============================================================================
# TTL 配置 (秒)
# =============================================================================

class TTL:
    SESSION     = 1800      # 30 分钟
    CUSTOMER    = 86400     # 24 小时
    RATE_LIMIT  = 60        # 1 分钟窗口
    AGENT_STATE = 300       # 5 分钟
    TOOL_CACHE  = 600       # 10 分钟
    TRIP_DRAFT  = 3600      # 1 小时
    LOCK        = 30        # 30 秒
    MID_TERM    = 86400 * 30  # 30 天 (中期摘要)
    ROUND       = 86400 * 7   # 7 天 (轮次计数器, 每次访问续期)


class RedisCache:
    """Redis 短时记忆层

    使用 hiredis 解析器 + 连接池，支持:
    - 会话上下文 (最近 N 轮消息)
    - 客户画像热缓存
    - 频率限制 (滑动窗口)
    - 工具结果缓存
    - 分布式锁
    """

    def __init__(self, url: str | None = None):
        self.redis_url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._pool: Any = None
        self._client: Any = None

    # =========================================================================
    # 连接管理
    # =========================================================================

    async def connect(self) -> bool:
        """建立 Redis 连接池"""
        try:
            import redis.asyncio as aioredis

            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                socket_timeout=5,
                socket_connect_timeout=3,
                retry_on_timeout=True,
                decode_responses=True,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)

            # 健康检查
            await self._client.ping()
            logger.info(f"[Redis] 连接成功 → {self.redis_url}")
            return True

        except ImportError:
            logger.warning("[Redis] redis-py 未安装，短时记忆降级为内存字典")
            return False
        except Exception as e:
            logger.error(f"[Redis] 连接失败: {e}")
            self._pool = None
            self._client = None
            return False

    async def close(self) -> None:
        """关闭连接池"""
        if self._pool:
            try:
                await self._pool.disconnect()
                logger.info("[Redis] 连接已关闭")
            except Exception:
                pass
        self._pool = None
        self._client = None

    @property
    def client(self):
        """获取原生 Redis 客户端 (用于高级操作)"""
        return self._client

    # =========================================================================
    # 会话上下文 (Session Context)
    # =========================================================================

    async def save_session_context(
        self,
        session_id: str,
        context: dict[str, Any],
        ttl: int = TTL.SESSION,
    ) -> bool:
        """保存会话上下文 (最近消息摘要 + 当前状态)"""
        if not self._client:
            return False
        try:
            key = f"{KeyPrefix.SESSION}{session_id}"
            await self._client.set(key, json.dumps(context, ensure_ascii=False), ex=ttl)
            logger.debug(f"[Redis] 保存会话 {session_id}, TTL={ttl}s")
            return True
        except Exception as e:
            logger.error(f"[Redis] 保存会话失败: {e}")
            return False

    async def get_session_context(self, session_id: str) -> dict[str, Any]:
        """获取会话上下文"""
        if not self._client:
            return {}
        try:
            key = f"{KeyPrefix.SESSION}{session_id}"
            data = await self._client.get(key)
            if data:
                # 续期
                await self._client.expire(key, TTL.SESSION)
                return json.loads(data)
            return {}
        except Exception as e:
            logger.error(f"[Redis] 读取会话失败: {e}")
            return {}

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        max_history: int = 20,
    ) -> None:
        """追加消息到会话历史 (自动裁剪)"""
        if not self._client:
            return
        try:
            key = f"{KeyPrefix.SESSION}{session_id}:history"
            msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
            await self._client.rpush(key, msg)
            await self._client.ltrim(key, -max_history, -1)
            await self._client.expire(key, TTL.SESSION)
        except Exception as e:
            logger.error(f"[Redis] 追加消息失败: {e}")

    async def get_recent_messages(self, session_id: str, count: int = 10) -> list[dict]:
        """获取最近 N 条消息"""
        if not self._client:
            return []
        try:
            key = f"{KeyPrefix.SESSION}{session_id}:history"
            items = await self._client.lrange(key, -count, -1)
            return [json.loads(item) for item in items]
        except Exception:
            return []

    # =========================================================================
    # 客户画像 (Customer Profile)
    # =========================================================================

    async def cache_customer_profile(
        self,
        customer_id: str,
        profile: dict[str, Any],
        ttl: int = TTL.CUSTOMER,
    ) -> bool:
        """缓存客户画像"""
        if not self._client:
            return False
        try:
            key = f"{KeyPrefix.CUSTOMER}{customer_id}"
            await self._client.set(key, json.dumps(profile, ensure_ascii=False), ex=ttl)
            return True
        except Exception as e:
            logger.error(f"[Redis] 缓存客户画像失败: {e}")
            return False

    async def get_customer_profile(self, customer_id: str) -> dict[str, Any] | None:
        """获取缓存的客户画像"""
        if not self._client:
            return None
        try:
            key = f"{KeyPrefix.CUSTOMER}{customer_id}"
            data = await self._client.get(key)
            return json.loads(data) if data else None
        except Exception:
            return None

    async def invalidate_customer(self, customer_id: str) -> None:
        """失效客户缓存 (画像更新后调用)"""
        if not self._client:
            return
        try:
            await self._client.delete(f"{KeyPrefix.CUSTOMER}{customer_id}")
        except Exception:
            pass

    # =========================================================================
    # 频率限制 (Rate Limiting)
    # =========================================================================

    async def check_rate_limit(
        self,
        identifier: str,
        max_requests: int = 30,
        window_seconds: int = TTL.RATE_LIMIT,
    ) -> tuple[bool, int]:
        """滑动窗口频率限制

        Args:
            identifier:    标识 (session_id 或 customer_id)
            max_requests:  最大请求数
            window_seconds: 窗口大小 (秒)

        Returns:
            (allowed: bool, remaining: int)
        """
        if not self._client:
            return (True, max_requests)  # Redis 不可用时放行

        try:
            key = f"{KeyPrefix.RATE_LIMIT}{identifier}"
            current = await self._client.incr(key)

            if current == 1:
                await self._client.expire(key, window_seconds)

            remaining = max(0, max_requests - current)
            allowed = current <= max_requests

            if not allowed:
                ttl = await self._client.ttl(key)
                logger.warning(
                    f"[Redis] 频率限制触发: {identifier} "
                    f"({current}/{max_requests} in {window_seconds}s)"
                )

            return (allowed, remaining)

        except Exception as e:
            logger.error(f"[Redis] 频率限制检查失败: {e}")
            return (True, max_requests)

    # =========================================================================
    # Agent 临时状态
    # =========================================================================

    async def save_agent_state(
        self,
        session_id: str,
        agent_name: str,
        state: dict[str, Any],
        ttl: int = TTL.AGENT_STATE,
    ) -> bool:
        """保存 Agent 临时工作状态"""
        if not self._client:
            return False
        try:
            key = f"{KeyPrefix.AGENT_STATE}{session_id}:{agent_name}"
            await self._client.set(key, json.dumps(state, ensure_ascii=False), ex=ttl)
            return True
        except Exception:
            return False

    async def get_agent_state(self, session_id: str, agent_name: str) -> dict[str, Any]:
        """获取 Agent 临时状态"""
        if not self._client:
            return {}
        try:
            key = f"{KeyPrefix.AGENT_STATE}{session_id}:{agent_name}"
            data = await self._client.get(key)
            return json.loads(data) if data else {}
        except Exception:
            return {}

    # =========================================================================
    # 工具结果缓存
    # =========================================================================

    async def cache_tool_result(
        self,
        tool_name: str,
        args_hash: str,
        result: str,
        ttl: int = TTL.TOOL_CACHE,
    ) -> bool:
        """缓存工具调用结果 (相同参数直接返回)"""
        if not self._client:
            return False
        try:
            key = f"{KeyPrefix.TOOL_CACHE}{tool_name}:{args_hash}"
            await self._client.set(key, result, ex=ttl)
            return True
        except Exception:
            return False

    async def get_tool_cache(self, tool_name: str, args_hash: str) -> str | None:
        """获取缓存的工具结果"""
        if not self._client:
            return None
        try:
            key = f"{KeyPrefix.TOOL_CACHE}{tool_name}:{args_hash}"
            return await self._client.get(key)
        except Exception:
            return None

    # =========================================================================
    # 分布式锁
    # =========================================================================

    async def acquire_lock(
        self,
        resource: str,
        ttl: int = TTL.LOCK,
    ) -> bool:
        """获取分布式锁 (SET NX EX)"""
        if not self._client:
            return True  # 无 Redis 时不阻塞
        try:
            key = f"{KeyPrefix.LOCK}{resource}"
            token = os.urandom(8).hex()
            acquired = await self._client.set(key, token, nx=True, ex=ttl)
            return bool(acquired)
        except Exception:
            return True

    async def release_lock(self, resource: str) -> None:
        """释放分布式锁"""
        if not self._client:
            return
        try:
            key = f"{KeyPrefix.LOCK}{resource}"
            await self._client.delete(key)
        except Exception:
            pass

    # =========================================================================
    # 工具方法
    # =========================================================================

    @staticmethod
    def hash_args(*args, **kwargs) -> str:
        """对工具参数取 hash (用于缓存 key)"""
        import hashlib
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()[:12]


# =============================================================================
# 预置实例
# =============================================================================

redis_cache = RedisCache()
