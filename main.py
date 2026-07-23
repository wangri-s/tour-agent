"""FastAPI 入口 —— /chat 接口 (千问驱动 + 三层记忆)"""

from __future__ import annotations

import os
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _memory
    logger.info("=" * 50)
    logger.info("Starting tour-agent v0.3.0 — 三层记忆 + RAG")
    logger.info(f"LLM Model: {os.getenv('LLM_MODEL', 'qwen-plus')}")
    logger.info(f"API Base: {os.getenv('DASHSCOPE_BASE_URL', 'dashscope')}")
    logger.info("=" * 50)

    # 启动三层记忆系统
    _memory = MemoryOrchestrator()
    mem_status = await _memory.startup()
    logger.info(
        f"Memory: Redis={mem_status['redis']}, "
        f"Kafka={mem_status['kafka']}, MySQL={mem_status['mysql']}"
    )

    # 编译 LangGraph
    _graph = build_graph()
    logger.info("✅ Graph compiled, ready to serve.")
    yield

    # 关闭
    if _memory:
        await _memory.shutdown()
    logger.info("Shutting down.")


app = FastAPI(
    title="tour-agent",
    description="入境定制游 LangGraph Multi-Agent API — 千问驱动 + 三层记忆 + RAG",
    version="0.3.0",
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

    流程: input_guard → session_context → intent_router
              → [customer_service | sales_agent | operations_agent | trip_planner]
              → ... → operations_sync → END
    """

    from langchain_core.messages import HumanMessage

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

    try:
        result = await _graph.ainvoke(state, config)
    except Exception as e:
        logger.exception("Graph invocation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # 构造响应 (先构造，再保存记忆)
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
            session_id=req.session_id,
            customer_id=req.customer_id,
            role="assistant",
            content=result["final_reply"],
            channel=req.channel,
            language=req.language,
            branch=branch,
        )
        await _memory.remember_event(
            event_type="response_generated",
            session_id=req.session_id,
            customer_id=req.customer_id,
            agent_name=branch,
            payload={
                "reply_len": len(result.get("final_reply", "")),
                "has_draft": bool(draft_dict),
                "has_quote": bool(quote_dict),
            },
        )

    logger.info(
        f"[API] {req.session_id} → branch={result.get('current_branch')}, "
        f"reply_len={len(result.get('final_reply', ''))}, "
        f"draft={'yes' if draft_dict else 'no'}"
    )

    return ChatResponse(
        reply=result.get("final_reply", ""),
        draft=draft_dict,
        quote=quote_dict,
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
        "version": "0.3.0",
        "model": os.getenv("LLM_MODEL", "qwen-plus"),
        "provider": "dashscope (千问)",
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
