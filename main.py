"""FastAPI 入口 —— /chat + /chat/stream (千问驱动 + 三层记忆 + RAG + COT + LangSmith + Langfuse)"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════
# Windows 编码修复: GBK → UTF-8 (必须在其他 import 之前)
# ═══════════════════════════════════════════════════════════════════════
import sys
import os
import locale
import time
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
# 强制 locale 返回 UTF-8 (修复 httpx/httpcore 在 Windows 上的 GBK 问题)
if hasattr(locale, "getpreferredencoding"):
    locale.getpreferredencoding = lambda _do_setlocale=True: "UTF-8"  # type: ignore[method-assign]

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph import build_graph
from graph.state import OverallState
from services.memory import MemoryOrchestrator
from services.observability import start_trace, end_trace
from services.context_compressor import get_compressor
from services.stream_context import set_stream_queue, reset_stream_queue
from services.checkpoint_store import create_postgres_saver_async, shutdown_postgres_saver

# MCP Weather Server (Open-Meteo 免费 API)
from mcp_servers.weather.server import mcp as weather_mcp

# LangSmith (LangGraph 官方可观测平台, 自动追踪节点图)
_LANGSMITH_READY = False
_langsmith_client: Any = None
try:
    import langsmith as _ls  # type: ignore[no-redef]
    _langsmith_api_key = os.getenv("LANGCHAIN_API_KEY", "")
    if _langsmith_api_key and "xxx" not in _langsmith_api_key:
        _langsmith_client = _ls.Client()
        _LANGSMITH_READY = True
except ImportError:
    _ls = None  # type: ignore[no-redef]
except Exception:
    _ls = None  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tour-agent")

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

_graph: Any = None
_memory: MemoryOrchestrator | None = None
_postgres_checkpoint: bool = False
_langsmith_ready: bool = _LANGSMITH_READY


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：连接记忆系统 → 编译 Graph → 服务 → 关闭"""
    global _graph, _memory, _postgres_checkpoint

    logger.info("=" * 50)
    logger.info("Starting tour-agent v0.5.0 — LangSmith + Langfuse + COT + PostgresSaver")
    logger.info("LLM Model: %s", os.getenv("LLM_MODEL", "qwen-plus"))
    logger.info("LangSmith: %s", "✅" if _langsmith_ready else "⚠️ 未配置")
    logger.info("=" * 50)

    # 启动三层记忆系统
    _memory = MemoryOrchestrator()
    # 跳过 Kafka 事件桥接 (避免启动耗时)
    async def _noop() -> None:
        return None
    _memory._setup_event_bridge = _noop  # type: ignore[method-assign]
    mem_status = await _memory.startup()
    logger.info(
        "Memory: Redis=%s, Kafka=%s, MySQL=%s",
        mem_status["redis"], mem_status["kafka"], mem_status["mysql"],
    )

    # 编译 LangGraph (PostgresSaver 优先 → MemorySaver 降级)
    checkpointer = await create_postgres_saver_async()
    _graph = build_graph(checkpointer=checkpointer)
    _postgres_checkpoint = checkpointer is not None
    logger.info("✅ Graph compiled (PostgresCheckpoint=%s), ready to serve.", _postgres_checkpoint)

    # 加载 Prompt 版本管理器 (多旅行社支持)
    from services.prompt_manager import prompt_manager as _pm
    pm_status = await _pm.load_all()
    logger.info("📝 Prompt Manager: %d agencies, versions=%s",
                pm_status["agencies"], pm_status["versions"])
    yield

    # 关闭
    if _memory:
        await _memory.shutdown()
    await shutdown_postgres_saver()
    logger.info("Shutting down.")


app = FastAPI(
    title="tour-agent",
    description="入境定制游 LangGraph Multi-Agent API — 千问驱动 + 三层记忆 + RAG",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 MCP Weather Server (Open-Meteo, 免费实时天气)
# 访问: http://127.0.0.1:8002/mcp/weather
weather_app = weather_mcp.http_app(path="/mcp")
app.mount("/mcp/weather", weather_app)


# =============================================================================
# Admin API — Prompt 版本管理
# =============================================================================

@app.get("/admin/prompts")
async def admin_list_prompts():
    """查看所有旅行社的 prompt 版本配置"""
    from services.prompt_manager import prompt_manager as pm

    agencies = []
    for a in pm.list_agencies():
        config = pm.get_agency_config(a["agency_id"])
        agencies.append({
            "agency_id": a["agency_id"],
            "brand_name": a["brand_name"],
            "brand_name_en": a.get("brand_name_en", ""),
            "prompt_versions": config.get("prompt_versions", {}),
            "has_override": bool(config.get("prompt_overrides", {})),
            "tone": config.get("output_style", {}).get("tone", "professional"),
        })

    versions = pm.list_versions("trip_planner")

    return {
        "agencies": agencies,
        "versions": versions,
        "total_agencies": len(agencies),
        "total_versions": len(versions),
    }


@app.get("/admin/prompts/{agency_id}")
async def admin_get_agency_prompt(agency_id: str):
    """查看某个旅行社的完整 prompt 文本"""
    from services.prompt_manager import prompt_manager as pm

    config = pm.get_agency_config(agency_id)
    prompt = pm.get_prompt(agency_id, "trip_planner")

    return {
        "agency_id": agency_id,
        "brand_name": config.get("brand_name"),
        "version": config.get("prompt_versions", {}).get("trip_planner", "v1_standard"),
        "prompt_length": len(prompt),
        "prompt_text": prompt,
        "config": {
            "output_style": config.get("output_style", {}),
            "model_overrides": config.get("model_overrides", {}),
            "has_prompt_override": bool(config.get("prompt_overrides", {})),
        },
    }


@app.post("/admin/prompts/reload")
async def admin_reload_prompts():
    """热加载所有旅行社配置和 prompt 版本 (无需重启服务)"""
    from services.prompt_manager import prompt_manager as pm

    status = await pm.reload()
    return {
        "status": "ok",
        "message": "配置已重新加载",
        **status,
    }


# =============================================================================
# Request / Response
# =============================================================================

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话唯一标识", examples=["sess-001"])
    customer_id: str = Field(..., description="客户唯一标识", examples=["c-001"])
    agency_id: str = Field(
        default="",
        description="旅行社 ID (用于 prompt 版本选择), 如 luxury_travel / budget_travel",
        examples=["luxury_travel"],
    )
    channel: str = Field(
        default="web",
        description="渠道: whatsapp | wechat | web | messenger | tiktok",
        examples=["web"],
    )
    message: str = Field(..., description="用户消息", examples=["我想去北京玩5天，2个人，预算每人8000"])
    language: str = Field(default="zh", description="语言偏好")


class ChatResponse(BaseModel):
    reply: str = Field(default="", description="最终回复")
    draft: dict | None = Field(default=None, description="行程草案 (Markdown + 费用)")
    quote: dict | None = Field(default=None, description="报价单")
    branch: str = Field(default="", description="当前分支")
    need_human: bool = Field(default=False, description="是否已转人工")


# =============================================================================
# 工具函数
# =============================================================================

def _extract_draft(raw_draft: Any) -> dict | None:
    """安全提取 TripDraft → dict"""
    if raw_draft is None:
        return None
    md = raw_draft.itinerary_md if hasattr(raw_draft, "itinerary_md") else raw_draft.get("itinerary_md", "")
    if not md:
        return None
    return {
        "version": raw_draft.version if hasattr(raw_draft, "version") else raw_draft.get("version", 0),
        "itinerary_md": md,
        "estimated_cost": raw_draft.estimated_cost if hasattr(raw_draft, "estimated_cost") else raw_draft.get("estimated_cost", 0),
        "weather_summary": raw_draft.weather_summary if hasattr(raw_draft, "weather_summary") else raw_draft.get("weather_summary", ""),
        "highlights": raw_draft.highlights if hasattr(raw_draft, "highlights") else raw_draft.get("highlights", []),
    }


def _extract_quote(raw_quote: Any) -> dict | None:
    """安全提取 Quote → dict"""
    if raw_quote is None:
        return None
    return raw_quote.model_dump() if hasattr(raw_quote, "model_dump") else dict(raw_quote)


async def _load_history(session_id: str) -> list[dict[str, str]]:
    """从记忆系统加载历史消息并压缩"""
    history_msgs: list[dict[str, str]] = []
    if _memory:
        history = await _memory.recall_context(session_id)
        if history.get("messages"):
            history_msgs = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in history["messages"]
            ]
    return history_msgs


async def _save_assistant_reply(
    session_id: str, customer_id: str, channel: str,
    language: str, branch: str, final_reply: str,
    draft_dict: dict | None, quote_dict: dict | None,
) -> None:
    """保存 AI 回复到三层记忆"""
    if not _memory or not final_reply:
        return
    await _memory.remember_message(
        session_id=session_id, customer_id=customer_id,
        role="assistant", content=final_reply,
        channel=channel, language=language, branch=branch,
    )
    await _memory.remember_event(
        event_type="response_generated",
        session_id=session_id, customer_id=customer_id,
        agent_name=branch,
        payload={
            "reply_len": len(final_reply),
            "has_draft": bool(draft_dict),
            "has_quote": bool(quote_dict),
        },
    )


def _build_fallback_reply(draft_dict: dict | None) -> str:
    """草案已生成但无回复时的兜底文案"""
    if not draft_dict:
        return "(暂无回复)"
    cost = draft_dict.get("estimated_cost", 0)
    cost_str = f"\n💰 预估人均费用：**¥{cost:,.0f}**" if cost > 0 else ""
    return (
        f"为您定制了行程 ✨{cost_str}\n\n"
        "📋 行程已生成。您可以：\n"
        "- ✅ **满意** → 回复「好的」，我为您生成报价单\n"
        "- 🔄 **修改** → 告诉我哪里需要调整\n"
        "- 📞 **人工** → 回复「转人工」，由旅行顾问接洽"
    )


def _start_langsmith_trace(req: ChatRequest) -> Any:
    """创建 LangSmith trace 上下文"""
    if not _langsmith_ready or _ls is None:
        return None
    try:
        ctx = _ls.trace(
            name="chat",
            inputs={"message": req.message[:200], "channel": req.channel},
            metadata={
                "session_id": req.session_id,
                "customer_id": req.customer_id,
                "channel": req.channel,
                "language": req.language,
                "version": "0.5.0",
            },
            tags=[req.channel, req.language, "tour-agent"],
        )
        ctx.__enter__()
        return ctx
    except Exception:
        return None


def _end_langsmith_trace(ctx: Any, exc: Any = None) -> None:
    """安全关闭 LangSmith trace"""
    if ctx is None:
        return
    try:
        if exc:
            ctx.__exit__(type(exc), exc, exc.__traceback__)
        else:
            ctx.__exit__(None, None, None)
    except Exception:
        pass


# =============================================================================
# /chat — 非流式接口
# =============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """统一对话入口 (非流式)

    LangGraph 节点自动被 LangSmith 追踪 (设置 LANGCHAIN_API_KEY 后)。
    流程: input_guard → session_context → intent_router
              → [customer_service | sales_agent | operations_agent | trip_planner]
              → ... → operations_sync → END
    """

    from langchain_core.messages import HumanMessage

    t_start = time.time()

    # ---- LangSmith Trace ----
    ls_ctx = _start_langsmith_trace(req)

    # ---- Langfuse Trace ----
    trace_ctx = start_trace(req.session_id, req.customer_id)

    # ---- 上下文加载与压缩 ----
    history_msgs = await _load_history(req.session_id)
    all_messages = history_msgs + [{"role": "user", "content": req.message}]
    _compressed = await get_compressor().compress(all_messages, req.session_id, max_tokens=5200)

    # ---- 中期记忆注入 ----
    mid_context = ""
    if _memory:
        mid_context = await _memory.inject_mid_term_context(req.session_id)

    # 构建 graph state (含中期记忆)
    state_messages: list[Any] = [HumanMessage(content=req.message)]
    if mid_context:
        from langchain_core.messages import SystemMessage
        state_messages.insert(0, SystemMessage(
            content=f"[会话中期记忆 — 前方对话摘要]\n{mid_context}"
        ))

    state: OverallState = {  # type: ignore[assignment]
        "session_id": req.session_id,
        "customer_id": req.customer_id,
        "agency_id": req.agency_id,
        "channel": req.channel,
        "language": req.language,
        "messages": state_messages,  # type: ignore[list-item]
    }

    config = {"configurable": {"thread_id": req.session_id}}
    logger.info("[API] %s | %s | agency=%s | %s...",
                req.session_id, req.channel, req.agency_id or "default", req.message[:80])

    # ---- 保存用户消息 ----
    if _memory:
        await _memory.remember_message(
            session_id=req.session_id, customer_id=req.customer_id,
            role="user", content=req.message,
            channel=req.channel, language=req.language,
        )

    trace_ctx.add_span(
        "input_processing", "pipeline",
        input_data=req.message[:200],
        metadata={"msg_count": len(all_messages), "mid_context": bool(mid_context)},
    )

    # ---- 调用 LangGraph ----
    from services.prompt_manager import set_current_agency
    set_current_agency(req.agency_id)
    assert _graph is not None, "Graph 未初始化 (lifespan 应已编译)"
    try:
        result = await _graph.ainvoke(state, config)
    except Exception as e:
        logger.exception("Graph invocation failed")
        trace_ctx.add_span("error", "pipeline", error=str(e))
        end_trace()
        _end_langsmith_trace(ls_ctx, e)
        raise HTTPException(status_code=500, detail=str(e))

    # ---- 构造响应 ----
    draft_dict = _extract_draft(result.get("draft"))
    quote_dict = _extract_quote(result.get("quote"))
    branch = result.get("current_branch", "")
    final_reply = result.get("final_reply", "") or _build_fallback_reply(draft_dict)

    # ---- 保存 AI 回复 ----
    await _save_assistant_reply(
        req.session_id, req.customer_id, req.channel, req.language,
        branch, final_reply, draft_dict, quote_dict,
    )

    # ---- 中期记忆压缩 (每 5 轮触发) ----
    if _memory:
        await _memory.maybe_compress_mid_term(req.session_id, all_messages)

    latency_ms = (time.time() - t_start) * 1000
    logger.info(
        "[API] %s → branch=%s reply=%d draft=%s latency=%.0fms",
        req.session_id, branch, len(final_reply),
        "yes" if draft_dict else "no", latency_ms,
    )

    # ---- 结束追踪 ----
    trace_ctx.add_span(
        "chat_response", "pipeline",
        output_data=final_reply[:200],
        metadata={
            "branch": branch,
            "draft_len": len(draft_dict.get("itinerary_md", "")) if draft_dict else 0,
            "has_quote": bool(quote_dict),
            "total_latency_ms": round(latency_ms),
        },
    )
    end_trace()
    _end_langsmith_trace(ls_ctx)

    return ChatResponse(
        reply=final_reply, draft=draft_dict, quote=quote_dict,
        branch=branch, need_human=result.get("need_human", False),
    )


# =============================================================================
# /chat/stream — SSE 流式接口
# =============================================================================

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式对话入口 — Server-Sent Events (SSE)

    事件类型:
        token  — 文本片段 (LLM 实时生成)
        branch — 处理分支 (planner/service/sales/operations)
        draft  — 行程草案 (JSON)
        quote  — 报价单 (JSON)
        reply  — 非流式最终回复 (兜底)
        done   — 流结束
        error  — 错误信息
    """

    from langchain_core.messages import HumanMessage

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def run_graph() -> None:
        """后台执行 graph，token 由 agent 推送到 queue"""
        token_ctx = set_stream_queue(queue)
        try:
            t_start = time.time()

            # 上下文压缩 + 中期记忆注入
            history_msgs = await _load_history(req.session_id)
            all_messages = history_msgs + [{"role": "user", "content": req.message}]
            _compressed = await get_compressor().compress(all_messages, req.session_id, max_tokens=5200)

            mid_context = ""
            if _memory:
                mid_context = await _memory.inject_mid_term_context(req.session_id)

            state_msgs: list[Any] = [HumanMessage(content=req.message)]
            if mid_context:
                from langchain_core.messages import SystemMessage
                state_msgs.insert(0, SystemMessage(
                    content=f"[会话中期记忆 — 前方对话摘要]\n{mid_context}"
                ))

            state: OverallState = {  # type: ignore[assignment]
                "session_id": req.session_id,
                "customer_id": req.customer_id,
                "agency_id": req.agency_id,
                "channel": req.channel,
                "language": req.language,
                "messages": state_msgs,  # type: ignore[list-item]
            }

            config = {"configurable": {"thread_id": req.session_id}}
            logger.info("[API-stream] %s | %s | %s...", req.session_id, req.channel, req.message[:80])

            # 保存用户消息
            if _memory:
                await _memory.remember_message(
                    session_id=req.session_id, customer_id=req.customer_id,
                    role="user", content=req.message,
                    channel=req.channel, language=req.language,
                )

            # 执行 graph
            from services.prompt_manager import set_current_agency
            set_current_agency(req.agency_id)
            assert _graph is not None, "Graph 未初始化"
            try:
                result = await _graph.ainvoke(state, config)
            except Exception as e:
                logger.exception("Graph invocation failed in stream")
                await queue.put(("error", str(e)[:500]))
                return

            # 推送分支
            branch = result.get("current_branch", "")
            await queue.put(("branch", branch))

            # 推送草稿
            draft_dict = _extract_draft(result.get("draft"))
            if draft_dict:
                await queue.put(("draft", draft_dict))

            # 推送报价
            quote_dict = _extract_quote(result.get("quote"))
            if quote_dict:
                await queue.put(("quote", quote_dict))

            # 推送非流式回复 (兜底)
            final_reply = result.get("final_reply", "")
            if final_reply:
                await queue.put(("reply", final_reply))

            # 保存 AI 回复
            await _save_assistant_reply(
                req.session_id, req.customer_id, req.channel, req.language,
                branch, final_reply, draft_dict, quote_dict,
            )

            # 中期记忆压缩
            if _memory:
                await _memory.maybe_compress_mid_term(req.session_id, all_messages)

            latency_ms = (time.time() - t_start) * 1000
            logger.info("[API-stream] %s done, latency=%.0fms", req.session_id, latency_ms)

        except Exception as e:
            logger.exception("Stream graph task failed")
            await queue.put(("error", str(e)[:500]))
        finally:
            reset_stream_queue(token_ctx)
            await queue.put(("done", ""))

    async def event_generator():
        """SSE 事件生成器"""
        task = asyncio.create_task(run_graph())

        try:
            while True:
                event = await queue.get()
                event_type, data = event

                if event_type == "done":
                    yield f"event: done\ndata: {json.dumps({'status': 'ok'}, ensure_ascii=False)}\n\n"
                    break
                if event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'error': data}, ensure_ascii=False)}\n\n"
                    break
                if event_type == "token":
                    yield f"event: token\ndata: {json.dumps({'text': data}, ensure_ascii=False)}\n\n"
                elif event_type == "branch":
                    yield f"event: branch\ndata: {json.dumps({'branch': data}, ensure_ascii=False)}\n\n"
                elif event_type == "draft":
                    yield f"event: draft\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif event_type == "quote":
                    yield f"event: quote\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif event_type == "reply":
                    yield f"event: reply\ndata: {json.dumps({'text': data}, ensure_ascii=False)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# Health check
# =============================================================================

@app.get("/health")
async def health():
    mem_stats: dict[str, Any] = {}
    if _memory:
        mem_stats = await _memory.get_stats()

    return {
        "status": "ok",
        "version": "0.5.0",
        "model": os.getenv("LLM_MODEL", "qwen-plus"),
        "provider": "dashscope (千问)",
        "features": {
            "checkpoint": "postgres" if _postgres_checkpoint else "memory",
            "langsmith": _langsmith_ready,
            "langfuse": os.getenv("LANGFUSE_PUBLIC_KEY", "") != "",
            "weather_api": os.getenv("QWEATHER_API_KEY", "") != "",
            "rag": "milvus+dashscope",
            "cot_prompts": True,
            "context_compression": True,
            "streaming": True,
        },
        "memory": mem_stats,
        "rag": {
            "milvus": os.getenv("MILVUS_HOST", "localhost"),
            "embedding_model": "text-embedding-v3",
        },
    }


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8002)
