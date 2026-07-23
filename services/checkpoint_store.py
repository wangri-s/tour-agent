"""PostgresSaver — LangGraph 持久化 Checkpoint 存储

替换开发期 MemorySaver，支持:
- 会话跨服务重启恢复
- 多实例共享 checkpoint
- 生产环境持久化

使用 langgraph-checkpoint-postgres 包。
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def create_postgres_saver() -> Any | None:
    """创建 PostgresSaver 实例

    从环境变量读取 PostgreSQL 连接信息。
    如果连接失败或包未安装，返回 None (退化为 MemorySaver)。

    Returns:
        PostgresSaver 实例 或 None
    """
    pg_url = os.getenv("POSTGRES_URL", "")
    if not pg_url:
        pg_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/tourai",
        )
        # 如果 DATABASE_URL 是 MySQL URL，则不使用
        if "mysql" in pg_url.lower():
            logger.info("[Checkpoint] DATABASE_URL 是 MySQL，跳过 PostgresSaver")
            return None

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        saver = PostgresSaver.from_conn_string(pg_url)
        await saver.setup()
        logger.info(f"[Checkpoint] PostgresSaver 连接成功 → {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
        return saver

    except ImportError:
        logger.warning("[Checkpoint] langgraph-checkpoint-postgres 未安装，使用 MemorySaver")
        return None
    except Exception as e:
        logger.warning(f"[Checkpoint] PostgresSaver 连接失败: {e}，使用 MemorySaver")
        return None


def create_postgres_saver_sync() -> Any | None:
    """同步版本 (用于 builder.py)"""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return asyncio.run(create_postgres_saver())
    except Exception as e:
        logger.warning(f"[Checkpoint] 同步创建失败: {e}")
        return None
