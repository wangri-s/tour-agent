"""报价 Agent —— 基于 draft 与 need 生成结构化报价单"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from prompts.quote_agent import QUOTE_AGENT_PROMPT
from graph.state import OverallState, Quote
from tools.quote_price import quote_price


class QuoteAgent(BaseAgent):
    """生成分项报价：机票、酒店、交通、门票、餐饮、导游"""

    def __init__(self):
        super().__init__(name="quote_agent")
        self.tools = [quote_price]

    def system_prompt(self) -> str:
        return QUOTE_AGENT_PROMPT

    async def generate(self, state: OverallState) -> dict[str, Any]:
        """生成报价单

        Returns:
            {
                "quote": Quote | None,
                "reply": str,
                "messages": [...],
            }
        """

        s = state if isinstance(state, dict) else state.__dict__ if hasattr(state, '__dict__') else {}
        need = s.get("need") if isinstance(s, dict) else state.need
        draft = s.get("draft") if isinstance(s, dict) else state.draft
        context = {
            "need": need.model_dump() if hasattr(need, "model_dump") else need,
            "draft": draft.model_dump() if hasattr(draft, "model_dump") else draft,
        }

        messages = [
            {"role": "user", "content": f"生成报价：\n{context}"}
        ]

        result = await self.call_llm(messages, tools=self.tools)
        content = result.get("content", "")

        # 解析报价
        quote = self._parse_quote(content)

        return {
            "quote": quote,
            "reply": content,
            "messages": [],
        }

    def _parse_quote(self, content: str) -> Quote | None:
        """从 LLM 输出解析 Quote

        TODO MVP: 用结构化输出
        """
        try:
            import json
            # 尝试从内容中提取 JSON
            if "{" in content and "}" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                data = json.loads(content[start:end])
                return Quote(**data)
        except Exception:
            pass
        return None
