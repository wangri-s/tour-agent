"""FastAPI 入口 —— /chat 接口 (千问驱动)"""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    logger.info("=" * 50)
    logger.info("Starting tour-agent...")
    logger.info(f"LLM Model: {os.getenv('LLM_MODEL', 'qwen-plus')}")
    logger.info(f"API Base: {os.getenv('DASHSCOPE_BASE_URL', 'dashscope')}")
    logger.info("=" * 50)
    _graph = build_graph()
    logger.info("✅ Graph compiled, ready to serve.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="tour-agent",
    description="入境定制游 LangGraph Multi-Agent API (千问驱动)",
    version="0.2.0",
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

    try:
        result = await _graph.ainvoke(state, config)
    except Exception as e:
        logger.exception("Graph invocation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # 构造响应
    draft_dict = None
    if result.get("draft") and result["draft"].itinerary_md:
        draft_dict = {
            "version": result["draft"].version,
            "itinerary_md": result["draft"].itinerary_md,
            "estimated_cost": result["draft"].estimated_cost,
            "weather_summary": result["draft"].weather_summary,
            "highlights": result["draft"].highlights,
        }

    quote_dict = None
    if result.get("quote"):
        quote_dict = result["quote"].model_dump()

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
    return {
        "status": "ok",
        "version": "0.2.0",
        "model": os.getenv("LLM_MODEL", "qwen-plus"),
        "provider": "dashscope (千问)",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
