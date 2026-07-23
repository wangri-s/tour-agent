"""Langfuse 可观测性 — Token、延迟、Agent调用链全链路追踪

接入 Langfuse:
- LLM 调用追踪 (model, tokens, latency, input/output)
- Tool 调用追踪 (tool name, args, result, latency)
- Agent 调用链 (graph node → agent → llm → tool 层级关系)
- Session 关联 (按 session_id 分组)
- 错误追踪 (异常堆栈)

降级: Langfuse 不可用时不影响业务。
"""

from __future__ import annotations

import os
import time
import json
import logging
import functools
from typing import Any, Callable
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_langfuse_client: Any = None


def get_langfuse():
    """懒加载 Langfuse 客户端"""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client if _langfuse_client != "disabled" else None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        logger.info("[Langfuse] 未配置密钥，可观测性已禁用")
        _langfuse_client = "disabled"
        return None

    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.info(f"[Langfuse] 连接成功 → {host}")
        return _langfuse_client
    except ImportError:
        logger.warning("[Langfuse] langfuse 包未安装")
        _langfuse_client = "disabled"
        return None
    except Exception as e:
        logger.error(f"[Langfuse] 初始化失败: {e}")
        _langfuse_client = "disabled"
        return None


# =============================================================================
# Trace 上下文
# =============================================================================

class ObservabilityTrace:
    """单次请求的追踪上下文"""

    def __init__(self, session_id: str, customer_id: str = ""):
        self.session_id = session_id
        self.customer_id = customer_id
        self.trace_id = f"trace-{session_id}-{int(time.time() * 1000)}"
        self.spans: list[dict] = []
        self.start_time = time.time()

    def add_span(
        self,
        name: str,
        span_type: str,
        input_data: Any = None,
        output_data: Any = None,
        metadata: dict | None = None,
        latency_ms: float = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: str = "",
    ):
        self.spans.append({
            "name": name,
            "type": span_type,
            "input": str(input_data)[:500] if input_data else "",
            "output": str(output_data)[:500] if output_data else "",
            "metadata": metadata or {},
            "latency_ms": round(latency_ms, 1),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "error": error,
            "timestamp": time.time(),
        })

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "total_latency_ms": round((time.time() - self.start_time) * 1000, 1),
            "span_count": len(self.spans),
            "spans": self.spans,
        }


# 当前请求的 trace (线程/协程本地存储)
import threading
_trace_local = threading.local()


def start_trace(session_id: str, customer_id: str = "") -> ObservabilityTrace:
    """开始新的追踪"""
    trace = ObservabilityTrace(session_id, customer_id)
    _trace_local.current_trace = trace
    return trace


def get_trace() -> ObservabilityTrace | None:
    """获取当前追踪"""
    return getattr(_trace_local, "current_trace", None)


def end_trace() -> dict | None:
    """结束追踪并上报 Langfuse"""
    trace = get_trace()
    if not trace:
        return None

    data = trace.to_dict()
    _trace_local.current_trace = None

    # 上报到 Langfuse
    lf = get_langfuse()
    if lf:
        try:
            lf_trace = lf.trace(
                id=trace.trace_id,
                name="chat-request",
                session_id=trace.session_id,
                user_id=trace.customer_id,
                metadata={"total_spans": len(trace.spans)},
            )
            for span in trace.spans:
                lf_trace.span(
                    name=span["name"],
                    input=span["input"][:1000] if span["input"] else None,
                    output=span["output"][:1000] if span["output"] else None,
                    metadata={
                        **span["metadata"],
                        "latency_ms": span["latency_ms"],
                        "tokens_in": span["tokens_in"],
                        "tokens_out": span["tokens_out"],
                    },
                )
            lf.flush()
            logger.debug(f"[Langfuse] Trace 上报: {trace.trace_id} ({len(trace.spans)} spans)")
        except Exception as e:
            logger.error(f"[Langfuse] 上报失败: {e}")

    return data


# =============================================================================
# 装饰器 — 自动追踪 LLM / Tool 调用
# =============================================================================

def trace_llm_call(func_name: str):
    """追踪 LLM 调用的装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            trace = get_trace()
            start = time.time()
            error = ""
            tokens_in = 0
            tokens_out = 0
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict):
                    tokens_in = result.get("usage", {}).get("prompt_tokens", 0) or kwargs.get("prompt_tokens_est", 0)
                    tokens_out = result.get("usage", {}).get("completion_tokens", 0)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                if trace:
                    trace.add_span(
                        name=func_name,
                        span_type="llm",
                        input_data=str(kwargs.get("messages", ""))[:200],
                        output_data=str(error)[:200] if error else "ok",
                        metadata={"model": kwargs.get("model", "unknown")},
                        latency_ms=(time.time() - start) * 1000,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        error=error,
                    )
        return wrapper
    return decorator


def trace_tool_call(tool_name: str):
    """追踪 Tool 调用的装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            trace = get_trace()
            start = time.time()
            error = ""
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                if trace:
                    trace.add_span(
                        name=f"tool:{tool_name}",
                        span_type="tool",
                        input_data=str(kwargs)[:300],
                        output_data=str(error)[:300] if error else "ok",
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )
        return wrapper
    return decorator
