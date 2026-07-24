"""PostgresSaver — LangGraph 持久化 Checkpoint 存储

替换开发期 MemorySaver，支持:
- 会话跨服务重启恢复
- 多实例共享 checkpoint
- 生产环境持久化

使用 langgraph-checkpoint-postgres 包。

注意: PostgresSaver.from_conn_string() 返回 context manager，
必须 __enter__() 后才能调用 setup()。
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_postgres_saver_sync() -> Any | None:
    """创建 PostgresSaver 实例 (同步)

    PostgresSaver.from_conn_string() 返回 _GeneratorContextManager，
    需要用 __enter__() 取出内部实例后才能 setup()。

    Returns:
        (saver, context_manager) 元组 或 None
        context_manager 需在整个应用生命周期保持打开，shutdown 时 __exit__()
    """
    pg_url = os.getenv("POSTGRES_URL", "")
    if not pg_url:
        pg_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/tourai",
        )
        if "mysql" in pg_url.lower():
            logger.info("[Checkpoint] DATABASE_URL 是 MySQL，跳过 PostgresSaver")
            return None

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        # from_conn_string 返回 context manager，手动进入
        cm = PostgresSaver.from_conn_string(pg_url)
        saver = cm.__enter__()
        saver.setup()

        logger.info(
            "[Checkpoint] PostgresSaver 连接成功 → %s",
            pg_url.split("@")[1] if "@" in pg_url else pg_url,
        )
        return saver

    except ImportError:
        logger.warning("[Checkpoint] langgraph-checkpoint-postgres 未安装，使用 MemorySaver")
        return None
    except Exception as e:
        logger.warning("[Checkpoint] PostgresSaver 连接失败: %s，使用 MemorySaver", e)
        return None
