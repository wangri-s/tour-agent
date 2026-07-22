"""FastAPI 入口 —— /chat 接口"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph import build_graph, OverallState, TripNeed

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
    logger.info("Starting tour-agent...")
    _graph = build_graph()
    logger.info("Graph compiled, ready to serve.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="tour-agent",
    description="入境定制游 LangGraph Multi-Agent API",
    version="0.1.0",
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
    session_id: str = Field(..., description="会话唯一标识")
    customer_id: str = Field(..., description="客户唯一标识")
    channel: str = Field(..., description="渠道: whatsapp | wechat | web | messenger | tiktok")
    message: str = Field(..., description="用户消息")
    language: str = Field(default="zh", description="语言偏好")


class ChatResponse(BaseModel):
    reply: str = Field(default="", description="最终回复")
    draft: dict | None = Field(default=None, description="行程草案")
    quote: dict | None = Field(default=None, description="报价单")
    branch: str = Field(default="", description="当前分支")
    need_human: bool = Field(default=False, description="是否已转人工")


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """统一对话入口

    调用 LangGraph invoke，返回结构化响应。
    """

    from langchain_core.messages import HumanMessage

    # 构造初始 State
    state: OverallState = OverallState(
        session_id=req.session_id,
        customer_id=req.customer_id,
        channel=req.channel,
        language=req.language,
        messages=[HumanMessage(content=req.message)],
    )

    config = {"configurable": {"thread_id": req.session_id}}

    try:
        result = await _graph.ainvoke(state, config)
    except Exception as e:
        logger.exception("Graph invocation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # 构造响应
    draft_dict = None
    if result.get("draft") and result["draft"].itinerary_md:
        draft_dict = result["draft"].model_dump()

    quote_dict = None
    if result.get("quote"):
        quote_dict = result["quote"].model_dump()

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
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
