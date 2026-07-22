"""短时记忆层 (Short-Term Memory) — Redis 驱动

负责:
- 会话上下文 (最近消息、当前状态)
- 客户画像热数据
- 频率限制
- 工具结果缓存
- 分布式锁

数据生命周期: 5 分钟 ~ 24 小时
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.redis_cache import redis_cache, KeyPrefix, TTL

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """短时记忆 — 热数据高速缓存"""

    def __init__(self):
        self._cache = redis_cache

    # =========================================================================
    # 会话管理
    # =========================================================================

    async def load_context(self, session_id: str) -> dict[str, Any]:
        """加载会话完整上下文

        Returns:
            {
                "messages": [...],     # 最近 10 轮对话
                "need": {...},         # 当前行程需求
                "draft": {...},        # 当前行程草案
                "branch": "...",       # 当前 Agent
                "language": "zh",
            }
        """
        ctx = await self._cache.get_session_context(session_id)
        if not ctx:
            return {}

        # 补充消息历史
        messages = await self._cache.get_recent_messages(session_id, 10)
        ctx["messages"] = messages
        return ctx

    async def save_context(
        self,
        session_id: str,
        context: dict[str, Any],
    ) -> None:
        """保存会话上下文 (自动分层: 消息历史 vs 状态数据)"""
        # 消息历史单独存储 (list)
        if "messages" in context:
            for msg in context.pop("messages"):
                await self._cache.append_message(
                    session_id,
                    msg.get("role", "user"),
                    msg.get("content", ""),
                )

        # 状态数据 (hash → json string)
        state_data = {
            k: v for k, v in context.items()
            if k not in ("messages",)
        }
        await self._cache.save_session_context(session_id, state_data)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """追加单条消息"""
        await self._cache.append_message(session_id, role, content)

    async def get_history(self, session_id: str, count: int = 10) -> list[dict]:
        """获取最近 N 条消息"""
        return await self._cache.get_recent_messages(session_id, count)

    # =========================================================================
    # 客户画像热缓存
    # =========================================================================

    async def get_profile(self, customer_id: str) -> dict[str, Any] | None:
        """获取客户画像 (热缓存)"""
        return await self._cache.get_customer_profile(customer_id)

    async def cache_profile(
        self,
        customer_id: str,
        profile: dict[str, Any],
    ) -> None:
        """缓存客户画像 (24h TTL)"""
        await self._cache.cache_customer_profile(customer_id, profile)

    async def invalidate_profile(self, customer_id: str) -> None:
        """失效客户画像缓存"""
        await self._cache.invalidate_customer(customer_id)

    # =========================================================================
    # 频率限制
    # =========================================================================

    async def check_rate(
        self,
        session_id: str,
        max_per_minute: int = 30,
    ) -> tuple[bool, int]:
        """检查会话频率限制

        Returns:
            (allowed, remaining)
        """
        return await self._cache.check_rate_limit(
            session_id,
            max_requests=max_per_minute,
        )

    # =========================================================================
    # Agent 状态
    # =========================================================================

    async def save_agent_state(
        self,
        session_id: str,
        agent_name: str,
        state: dict[str, Any],
    ) -> None:
        """保存 Agent 临时工作状态 (5min TTL)"""
        await self._cache.save_agent_state(session_id, agent_name, state)

    async def get_agent_state(
        self,
        session_id: str,
        agent_name: str,
    ) -> dict[str, Any]:
        """获取 Agent 临时状态"""
        return await self._cache.get_agent_state(session_id, agent_name)

    # =========================================================================
    # 工具缓存
    # =========================================================================

    async def cache_tool_result(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: str,
    ) -> None:
        """缓存工具调用结果"""
        args_hash = redis_cache.hash_args(**args)
        await self._cache.cache_tool_result(tool_name, args_hash, result)

    async def get_tool_result(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str | None:
        """获取缓存的工具结果"""
        args_hash = redis_cache.hash_args(**args)
        return await self._cache.get_tool_cache(tool_name, args_hash)

    # =========================================================================
    # 行程草稿
    # =========================================================================

    async def save_draft(self, session_id: str, draft: dict[str, Any]) -> None:
        """保存行程草稿 (1h TTL)"""
        await self._cache.save_agent_state(session_id, "trip_draft", draft)

    async def get_draft(self, session_id: str) -> dict[str, Any]:
        """获取行程草稿"""
        return await self._cache.get_agent_state(session_id, "trip_draft")
