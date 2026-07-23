"""流式输出上下文管理器 —— 通过 ContextVar 在线程/协程间传递 asyncio.Queue

用法:
    # SSE 端点
    queue = asyncio.Queue()
    token = stream_ctx.set(queue)
    try:
        # graph 运行中，agent 通过 get_stream_queue() 获取 queue 并推送 token
        await run_graph(...)
    finally:
        stream_ctx.reset(token)
        await queue.put(None)  # 哨兵: 流结束

    # Agent 内部
    queue = get_stream_queue()
    if queue:
        await queue.put(("token", "你好"))   # 推送文本块
        await queue.put(("draft", draft_obj))  # 推送草稿
        await queue.put(("quote", quote_obj))  # 推送报价
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar

_stream_queue: ContextVar[asyncio.Queue | None] = ContextVar("stream_queue", default=None)


def get_stream_queue() -> asyncio.Queue | None:
    """获取当前协程的流式队列（由 SSE 端点设置）"""
    return _stream_queue.get()


def set_stream_queue(queue: asyncio.Queue | None):
    """设置当前协程的流式队列"""
    return _stream_queue.set(queue)


def reset_stream_queue(token):
    """重置 ContextVar 到之前的值"""
    _stream_queue.reset(token)
