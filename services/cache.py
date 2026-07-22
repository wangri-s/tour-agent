"""Redis 缓存服务 —— 跨会话记忆与会话热数据"""

from __future__ import annotations

import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Cache:
    """Redis 缓存抽象

    MVP: 占位，第三阶段接入
    - 跨会话客户画像
    - 会话临时状态
    - 频率限制计数器
    """

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    async def get(self, key: str) -> Any | None:
        """读取缓存"""
        # TODO: aioredis
        logger.debug(f"[Cache] GET {key}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """写入缓存，默认 TTL 1小时"""
        # TODO
        logger.debug(f"[Cache] SET {key} (TTL={ttl}s)")

    async def delete(self, key: str) -> None:
        """删除缓存"""
        # TODO
        logger.debug(f"[Cache] DEL {key}")

    async def get_customer_profile(self, customer_id: str) -> dict[str, Any]:
        """获取客户画像"""
        profile = await self.get(f"profile:{customer_id}")
        return profile or {}

    async def set_customer_profile(self, customer_id: str, profile: dict[str, Any]) -> None:
        """保存客户画像"""
        await self.set(f"profile:{customer_id}", profile, ttl=86400 * 30)  # 30天


cache = Cache()
