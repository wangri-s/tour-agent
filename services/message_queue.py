"""消息队列服务 —— 异步任务分发"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MessageQueue:
    """消息队列抽象

    MVP: 占位
    用途：
    - 异步 CRM 写入
    - CAPI 批量回传
    - 长时间行程生成任务
    """

    def __init__(self):
        self.broker_url = os.getenv("MQ_URL", "redis://localhost:6379/1")

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        """发布消息"""
        # TODO: Redis Pub/Sub or RabbitMQ
        logger.debug(f"[MQ] PUB {channel}: {str(message)[:100]}")

    async def subscribe(self, channel: str, handler: Callable) -> None:
        """订阅消息"""
        # TODO
        logger.debug(f"[MQ] SUB {channel}")

    async def enqueue(self, queue: str, task: dict[str, Any]) -> None:
        """入队异步任务"""
        # TODO: Celery / RQ / Arq
        logger.debug(f"[MQ] ENQ {queue}: {str(task)[:100]}")


mq = MessageQueue()
