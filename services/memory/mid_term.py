"""中期记忆层 (Mid-Term Memory) — Redis 驱动

每 5 轮对话压缩一次，生成渐进式摘要。
摘要存储在 Redis List 中，后续轮次自动注入为上下文。

数据生命周期: 30 天 (TTL)
"""

from __future__ import annotations

import json
import time
import logging
from typing import Any

from services.redis_cache import redis_cache, KeyPrefix, TTL

logger = logging.getLogger(__name__)

MAX_SUMMARIES = 5  # 最多保留 5 段摘要 (覆盖 25 轮)


class MidTermMemory:
    """中期记忆 — 隔 N 轮压缩保存"""

    def __init__(self):
        self._cache = redis_cache

    # =========================================================================
    # 摘要存取
    # =========================================================================

    async def save_summary(
        self,
        session_id: str,
        summary: str,
        round_range: str,
    ) -> None:
        """保存一段摘要到 Redis List (FIFO，保留最近 N 段)"""
        if not self._cache._client:
            return

        key = f"{KeyPrefix.MID_TERM}{session_id}"
        entry = json.dumps({
            "rounds": round_range,          # "1-5", "6-10", "11-15"
            "summary": summary,
            "timestamp": time.time(),
        }, ensure_ascii=False)

        await self._cache._client.rpush(key, entry)
        # 只保留最近 N 段
        await self._cache._client.ltrim(key, -MAX_SUMMARIES, -1)
        await self._cache._client.expire(key, TTL.MID_TERM)

        logger.info(
            "[MidTerm] 摘要已保存: %s → 第%s轮 (%d字)",
            session_id[:12], round_range, len(summary),
        )

    async def get_summaries(self, session_id: str) -> list[dict[str, Any]]:
        """获取全部中期摘要 (按时间排序)"""
        if not self._cache._client:
            return []

        key = f"{KeyPrefix.MID_TERM}{session_id}"
        entries = await self._cache._client.lrange(key, 0, -1)
        return [json.loads(e) for e in entries] if entries else []

    async def get_recent_summaries(
        self, session_id: str, count: int = 3
    ) -> str:
        """获取最近 N 段摘要，拼接为上下文文本"""
        summaries = await self.get_summaries(session_id)
        if not summaries:
            return ""

        recent = summaries[-count:]
        parts = [
            f"[第{s['rounds']}轮] {s['summary']}"
            for s in recent
        ]
        return "\n---\n".join(parts)

    async def get_latest_summary(self, session_id: str) -> str:
        """获取最新一段摘要 (用于合并)"""
        summaries = await self.get_summaries(session_id)
        if not summaries:
            return ""
        return summaries[-1].get("summary", "")

    # =========================================================================
    # 旧会话恢复
    # =========================================================================

    async def recover_from_history(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        llm_gateway: Any = None,
    ) -> str | None:
        """计数器过期后，从 MySQL 历史消息恢复为一段摘要

        Returns:
            生成的摘要文本 或 None
        """
        if not messages or not llm_gateway:
            return None

        history_text = "\n".join(
            f"[{m.get('role', '?')}]: {m.get('content', '')[:200]}"
            for m in messages[-50:]  # 最多取 50 条
        )

        try:
            prompt = (
                "请将以下对话历史压缩为简洁摘要，保留关键信息:\n\n"
                "关键信息类别:\n"
                "1. 客户需求: 目的地、日期、人数、预算、偏好\n"
                "2. 已确认信息: 哪些需求已确认\n"
                "3. 待确认信息: 还有什么需要确认\n"
                "4. 行程变更: 客户要求过什么修改\n"
                "5. 情绪变化: 客户满意度变化\n\n"
                f"对话历史:\n{history_text[:3000]}\n\n"
                "请用中文输出，每类 1-2 句，总长度不超过 300 字。"
            )
            result = await llm_gateway.chat(
                system="你是一个专业的对话摘要助手。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            summary = result.get("content", "")[:300]
            if summary:
                await self.save_summary(session_id, summary, "历史")
                logger.info(
                    "[MidTerm] 旧会话恢复: %s → %d字摘要",
                    session_id[:12], len(summary),
                )
            return summary
        except Exception as e:
            logger.warning("[MidTerm] 恢复失败: %s", e)
            return None