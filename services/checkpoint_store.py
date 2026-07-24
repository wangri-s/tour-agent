"""PostgresSaver — LangGraph 持久化 Checkpoint 存储

替换开发期 MemorySaver，支持:
- 会话跨服务重启恢复
- 多实例共享 checkpoint
- 生产环境持久化

使用 langgraph-checkpoint-postgres 包。

注意: ainvoke() 需要 AsyncPostgresSaver (aio 子模块)，
同步的 PostgresSaver 不支持 async 方法 (aget_tuple 等)。
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 持有 context manager 引用，shutdown 时退出
_pg_context: Any = None


async def create_postgres_saver_async() -> Any | None:
    """创建 AsyncPostgresSaver 实例

    供 lifespan 调用。Linux/Mac 上直接可用。
    Windows: psycopg 与 uvicorn ProactorEventLoop 不兼容，自动降级 MemorySaver。

    Returns:
        AsyncPostgresSaver 实例 或 None
    """
    global _pg_context

    pg_url = os.getenv("POSTGRES_URL", "")
    if not pg_url:
        pg_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/tourai",
        )
        if "mysql" in pg_url.lower():
            logger.info("[Checkpoint] DATABASE_URL 是 MySQL，跳过 PostgresSaver")
            return None

    import sys as _sys
    if _sys.platform == "win32":
        logger.warning(
            "[Checkpoint] Windows psycopg 与 uvicorn ProactorEventLoop 不兼容，"
            "使用 MemorySaver。部署到 Linux 后自动启用 PostgresSaver。"
        )
        return None

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        cm = AsyncPostgresSaver.from_conn_string(pg_url)
        saver = await cm.__aenter__()
        await saver.setup()
        _pg_context = cm

        logger.info(
            "[Checkpoint] AsyncPostgresSaver 连接成功 → %s",
            pg_url.split("@")[1] if "@" in pg_url else pg_url,
        )
        return saver

    except ImportError:
        logger.warning("[Checkpoint] langgraph-checkpoint-postgres 未安装，使用 MemorySaver")
        return None
    except Exception as e:
        logger.warning("[Checkpoint] AsyncPostgresSaver 连接失败: %s，使用 MemorySaver", e)
        return None


def create_postgres_saver_sync() -> Any | None:
    """同步版本 — builder.py 降级路径，当前由 lifespan 异步管理"""
    return None


async def shutdown_postgres_saver() -> None:
    """关闭 PostgresSaver context manager (释放连接池)"""
    global _pg_context
    if _pg_context:
        try:
            await _pg_context.__aexit__(None, None, None)
            logger.info("[Checkpoint] AsyncPostgresSaver 已关闭")
        except Exception as e:
            logger.warning("[Checkpoint] 关闭失败: %s", e)
        _pg_context = None
