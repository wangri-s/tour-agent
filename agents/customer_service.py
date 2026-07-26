"""智能客服 Agent —— FAQ / 订单查询 / 退改政策 / 签证须知 / 产品介绍

基于 RAG 语义检索实现，知识库: knowledge/customer_service_kb.md
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from agents.base import BaseAgent, _normalize_role
from prompts.customer_service import CUSTOMER_SERVICE_PROMPT
from tools.rag_search import rag_search
from tools.check_handoff import check_handoff

if TYPE_CHECKING:
    from graph.state import OverallState


class CustomerServiceAgent(BaseAgent):
    """多语言客服，基于 RAG 语义检索回答产品、政策、FAQ、订单等问题"""

    def __init__(self):
        super().__init__(name="customer_service")
        self.tools = [rag_search, check_handoff]

    def system_prompt(self) -> str:
        return CUSTOMER_SERVICE_PROMPT

    async def handle(self, state: "OverallState") -> dict[str, Any]:
        """处理客服对话

        流程:
          1. 从用户消息提取查询意图
          2. RAG 语义检索知识库 (优先 service 分类)
          3. LLM 基于检索结果生成回复
          4. 检测是否需要转人工

        Returns:
            {
                "reply": str,       # 回复内容
                "need_human": bool,
                "messages": [...],
            }
        """

        msgs = state.get("messages", []) if isinstance(state, dict) else state.messages
        recent = [
            {"role": _normalize_role(m), "content": m.content}
            for m in msgs[-10:]
        ]

        # RAG-first: 先检索知识库，让 LLM 基于检索结果回答
        # 这样产品介绍、政策说明等都可以从知识库获取最新信息
        try:
            last_msg = recent[-1]["content"] if recent else ""
            if last_msg:
                # 构建检索查询：拼接最近几轮会话上下文
                context_msgs = [m["content"] for m in recent[-3:]]
                search_query = " ".join(context_msgs)[:500]

                # RAG 语义检索
                rag_result = await rag_search.ainvoke({
                    "query": search_query,
                    "top_k": 5,
                })
                if rag_result:
                    # 将检索结果注入消息列表作为上下文
                    recent.insert(0, {
                        "role": "system",
                        "content": (
                            "[知识库检索结果 — 请基于以下信息回答客户问题]\n"
                            f"{rag_result}\n\n"
                            "[重要提示] 如果知识库中有产品介绍、价格、政策等具体信息，"
                            "请优先引用知识库内容回答。对于产品介绍类问题，"
                            "详细介绍各产品线的特点、价格、适合人群。"
                            "对于身份问题，根据系统提示中的品牌信息回答。"
                        ),
                    })
        except Exception as e:
            # RAG 检索失败不阻断对话，LLM 用自己的知识回答
            pass

        result = await self.call_llm_stream(recent, tools=self.tools)

        return {
            "reply": result,
            "need_human": "转人工" in result or "人工客服" in result,
            "messages": [],
        }
