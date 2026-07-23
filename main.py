"""FastAPI 入口 —— /chat 接口 (千问驱动 + 三层记忆 + RAG + COT + LangSmith + Langfuse)"""

from __future__ import annotations

import os
import time
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph import build_graph
from graph.state import OverallState
from services.memory import MemoryOrchestrator
from services.observability import start_trace, end_trace, get_trace
from services.context_compressor import get_compressor

# LangSmith (LangGraph 官方可观测平台, 自动追踪节点图)
_LANGSMITH_READY = False
_langsmith_client = None
try:
    import langsmith as ls
    _langsmith_api_key = os.getenv("LANGCHAIN_API_KEY", "")
    if _langsmith_api_key and "xxx" not in _langsmith_api_key:
        _langsmith_client = ls.Client()
        _LANGSMITH_READY = True
except ImportError:
    pass
except Exception:
    pass

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tour-agent")

# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------

_graph = None
_memory: MemoryOrchestrator | None = None
_postgres_checkpoint = False
_langsmith_ready = _LANGSMITH_READY


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _memory, _postgres_checkpoint
    logger.info("=" * 50)
    logger.info("Starting tour-agent v0.5.0 — LangSmith + Langfuse + COT + PostgresSaver")
    logger.info(f"LLM Model: {os.getenv('LLM_MODEL', 'qwen-plus')}")
    logger.info(f"LangSmith: {'✅' if _langsmith_ready else '⚠️ 未配置'}")
    logger.info("=" * 50)

    # 启动三层记忆系统
    _memory = MemoryOrchestrator()
    # 跳过 Kafka 事件桥接 (避免启动耗时)
    async def _noop(): return None
    _memory._setup_event_bridge = _noop
    mem_status = await _memory.startup()
    logger.info(
        f"Memory: Redis={mem_status['redis']}, "
        f"Kafka={mem_status['kafka']}, MySQL={mem_status['mysql']}"
    )

    # 编译 LangGraph (PostgresSaver 优先)
    _graph = build_graph()
    _postgres_checkpoint = not isinstance(_graph.checkpointer, type(MemorySaver))  # type: ignore
    logger.info(f"✅ Graph compiled (PostgresCheckpoint={_postgres_checkpoint}), ready to serve.")
    yield

    # 关闭
    if _memory:
        await _memory.shutdown()
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


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话唯一标识", examples=["sess-001"])
    customer_id: str = Field(..., description="客户唯一标识", examples=["c-001"])
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


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """统一对话入口

    LangGraph 节点自动被 LangSmith 追踪 (设置 LANGCHAIN_API_KEY 后)。
    流程: input_guard → session_context → intent_router
              → [customer_service | sales_agent | operations_agent | trip_planner]
              → ... → operations_sync → END
    """

    from langchain_core.messages import HumanMessage

    t_start = time.time()

    # =========================================================================
    # LangSmith Trace 上下文 (自动追踪 Graph 节点 + LLM + Tool 调用)
    # =========================================================================
    ls_ctx = None
    if _langsmith_ready and ls:
        try:
            ls_ctx = ls.trace(
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
            ls_ctx.__enter__()
        except Exception:
            ls_ctx = None

    # =========================================================================
    # Langfuse 追踪 (LLM Token + 自定义 Span)
    # =========================================================================
    trace = start_trace(req.session_id, req.customer_id)

    # 上下文压缩
    history_msgs = []
    if _memory:
        history = await _memory.recall_context(req.session_id)
        if history.get("messages"):
            history_msgs = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in history["messages"]
            ]

    all_messages = history_msgs + [{"role": "user", "content": req.message}]
    compressor = get_compressor()
    compressed = await compressor.compress(all_messages, req.session_id, max_tokens=6000)

    state = OverallState(
        session_id=req.session_id,
        customer_id=req.customer_id,
        channel=req.channel,
        language=req.language,
        messages=[HumanMessage(content=req.message)],
    )

    config = {"configurable": {"thread_id": req.session_id}}
    logger.info(f"[API] {req.session_id} | {req.channel} | {req.message[:80]}...")

    # 保存用户消息到三层记忆
    if _memory:
        await _memory.remember_message(
            session_id=req.session_id,
            customer_id=req.customer_id,
            role="user",
            content=req.message,
            channel=req.channel,
            language=req.language,
        )

    trace.add_span("input_processing", "pipeline", input_data=req.message[:200],
                   metadata={"msg_count": len(all_messages), "compressed": len(compressed) < len(all_messages)})

    # =========================================================================
    # 调用 LangGraph (节点自动被 LangSmith 追踪)
    # =========================================================================
    try:
        result = await _graph.ainvoke(state, config)
    except Exception as e:
        logger.exception("Graph invocation failed")
        trace.add_span("error", "pipeline", error=str(e))
        end_trace()
        if ls_ctx:
            try: ls_ctx.__exit__(type(e), e, e.__traceback__)
            except: pass
        raise HTTPException(status_code=500, detail=str(e))

    # 构造响应
    draft_dict = None
    raw_draft = result.get("draft")
    if raw_draft:
        md = raw_draft.itinerary_md if hasattr(raw_draft, "itinerary_md") else raw_draft.get("itinerary_md", "")
        if md:
            draft_dict = {
                "version": raw_draft.version if hasattr(raw_draft, "version") else raw_draft.get("version", 0),
                "itinerary_md": md,
                "estimated_cost": raw_draft.estimated_cost if hasattr(raw_draft, "estimated_cost") else raw_draft.get("estimated_cost", 0),
                "weather_summary": raw_draft.weather_summary if hasattr(raw_draft, "weather_summary") else raw_draft.get("weather_summary", ""),
                "highlights": raw_draft.highlights if hasattr(raw_draft, "highlights") else raw_draft.get("highlights", []),
            }

    quote_dict = None
    raw_quote = result.get("quote")
    if raw_quote:
        quote_dict = raw_quote.model_dump() if hasattr(raw_quote, "model_dump") else raw_quote

    # 保存 AI 回复到三层记忆
    if _memory and result.get("final_reply"):
        branch = result.get("current_branch", "")
        await _memory.remember_message(
            session_id=req.session_id, customer_id=req.customer_id,
            role="assistant", content=result["final_reply"],
            channel=req.channel, language=req.language, branch=branch,
        )
        await _memory.remember_event(
            event_type="response_generated",
            session_id=req.session_id, customer_id=req.customer_id,
            agent_name=branch,
            payload={"reply_len": len(result.get("final_reply", "")),
                      "has_draft": bool(draft_dict), "has_quote": bool(quote_dict)},
        )

    final_reply = result.get("final_reply", "")
    if not final_reply and draft_dict:
        cost = draft_dict.get("estimated_cost", 0)
        cost_str = f"\n💰 预估人均费用：**¥{cost:,.0f}**" if cost > 0 else ""
        final_reply = (
            f"为您定制了行程 ✨{cost_str}\n\n"
            f"📋 行程已生成。您可以：\n"
            f'- ✅ **满意** → 回复「好的」，我为您生成报价单\n'
            f'- 🔄 **修改** → 告诉我哪里需要调整\n'
            f'- 📞 **人工** → 回复「转人工」，由旅行顾问接洽'
        )

    latency_ms = (time.time() - t_start) * 1000
    logger.info(
        f"[API] {req.session_id} → branch={result.get('current_branch')} "
        f"reply={len(final_reply)} draft={'yes' if draft_dict else 'no'} "
        f"latency={latency_ms:.0f}ms"
    )

    # 结束追踪
    trace.add_span("chat_response", "pipeline",
                   output_data=final_reply[:200],
                   metadata={"branch": result.get("current_branch", ""),
                             "draft_len": len(draft_dict.get("itinerary_md", "")) if draft_dict else 0,
                             "has_quote": bool(quote_dict),
                             "total_latency_ms": round(latency_ms)})
    end_trace()

    # 关闭 LangSmith trace
    if ls_ctx:
        try:
            ls_ctx.__exit__(None, None, None)
        except Exception:
            pass

    return ChatResponse(
        reply=final_reply, draft=draft_dict, quote=quote_dict,
        branch=result.get("current_branch", ""),
        need_human=result.get("need_human", False),
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    mem_stats = {}
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
        },
        "memory": mem_stats,
        "rag": {
            "milvus": os.getenv("MILVUS_HOST", "localhost"),
            "embedding_model": "text-embedding-v3",
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
