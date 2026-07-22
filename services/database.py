"""数据库服务 —— PostgreSQL + pgvector"""

from __future__ import annotations

import os
from typing import Any


class Database:
    """数据库抽象层

    MVP: 占位，第二 / 三阶段接入 PostgresSaver + pgvector
    """

    def __init__(self):
        self.dsn = os.getenv("DATABASE_URL", "postgresql://localhost:5432/tourai")

    async def connect(self) -> None:
        """建立连接池"""
        # TODO: asyncpg / SQLAlchemy async
        pass

    async def close(self) -> None:
        """关闭连接池"""
        pass

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """执行 SQL"""
        # TODO
        pass

    async def fetch(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """查询"""
        # TODO
        return []


db = Database()
