"""业务 Agent 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.llm_gateway import LLMGateway


def _normalize_role(msg) -> str:
    """将 LangChain 消息类型映射为 API role (human→user, ai→assistant)"""
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool", "function": "tool"}
    if isinstance(msg, dict):
        raw = msg.get("role", "?")
    elif hasattr(msg, "type"):
        raw = msg.type
    else:
        raw = "assistant"
    return role_map.get(raw, raw)


class BaseAgent(ABC):
    """所有业务 Agent 的基类

    封装 LLM 调用、工具绑定、错误处理等公共逻辑。
    """

    def __init__(self, name: str = "base"):
        self.name = name
        self.llm = LLMGateway()

    @abstractmethod
    def system_prompt(self) -> str:
        """返回该 Agent 的 system prompt"""
        ...

    def _build_system_prompt(self, override: str = "") -> str:
        """构建最终 system prompt — 自动注入旅行社品牌身份

        降级链:
          1. 如果调用者传了 override (如 trip_planner 传了 agency 版本 prompt) → 直接用
          2. 否则 → self.system_prompt() + prompt_manager 注入品牌身份

        所有 agent 自动获得旅行社身份，无需逐个修改。
        """
        from services.prompt_manager import get_current_agency, prompt_manager

        agency_id = get_current_agency()

        if override:
            return override  # trip_planner 已经处理了版本选择和身份注入

        base = self.system_prompt()
        return prompt_manager.inject_identity(agency_id, base)

    def _fix_identity_in_reply(self, text: str) -> str:
        """回复后处理 — 将 LLM 编造的虚假身份替换为正确的旅行社名称

        某些 LLM (如 qwen) 在训练数据中有强身份偏见（如自称"悠游中国"），
        即使 system prompt 明确写了所属机构也会忽略。
        这里做最终兜底替换。
        """
        from services.prompt_manager import get_current_agency, prompt_manager

        agency_id = get_current_agency()
        config = prompt_manager.get_agency_config(agency_id)
        brand_name = config.get("brand_name", "")

        if not brand_name or brand_name in text:
            return text  # 已经正确，无需替换

        import re

        fixed = text

        # 策略: 一刀切 — 匹配所有虚假身份模式并替换
        # LLM 编造的身份模式多种多样, 用宽匹配 + 逐层清理

        # 1. 如果开头就是 "您好！😊 我是" + 任意内容 + "智能客服/助手" → 整句替换开头
        fixed = re.sub(
            r'^(您好！[😊]?\s*)'
            r'我是.{0,60}?(智能客服|智能助手|数字平台|服务平台)'
            r'.{0,120}?[。]',
            f'\\1我是「{brand_name}」的旅行顾问，专为海外游客提供一站式中文旅游服务。',
            fixed,
        )

        # 2. 如果开头是 "您好！😊 我不是" → 整段替换
        fixed = re.sub(
            r'^(您好！[😊]?\s*)'
            r'我不是.{0,200}?[。]',
            f'\\1我是「{brand_name}」的旅行顾问，专为海外游客提供一站式中文旅游服务。',
            fixed,
        )

        # 3. 清理: 删除 "不是传统旅行社..." → "..."
        fixed = re.sub(r'[，,]\s*不是传统旅行社[^。，,]*[，,。]', '，', fixed)

        # 4. 清理: 删除 "而是XX平台/助手..."
        fixed = re.sub(r'而是[^，。]{0,60}(平台|助手|客服)[^，。]{0,10}[，。]', '，', fixed)

        # 5. 清理: 删除 "我们不隶属于任何商业旅行社..."
        fixed = re.sub(r'我们不隶属于任何商业旅行社[^。]*[。]', '', fixed)

        # 6. 清理双品牌名重复
        fixed = re.sub(
            f'{re.escape(brand_name)}{re.escape(brand_name)}',
            brand_name,
            fixed,
        )

        # 7. 最终兜底: 开头没有品牌名 → 强制插入
        if brand_name not in fixed[:150]:
            fixed = re.sub(
                r'^(您好！[😊]?\s*)(我是)',
                f'\\1我是「{brand_name}」的旅行顾问，',
                fixed,
                count=1,
            )

        return fixed

    def _inject_identity_to_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """在用户消息前插入身份声明 — 用于客服等不遵从 system prompt 的场景

        将品牌身份直接注入为 system 消息（插入到消息列表开头），
        比 system prompt 更接近对话上下文，更难被 LLM 忽略。
        """
        from services.prompt_manager import get_current_agency, prompt_manager

        agency_id = get_current_agency()
        if not agency_id:
            return messages  # 没有指定旅行社，不注入

        config = prompt_manager.get_agency_config(agency_id)
        brand_name = config.get("brand_name", "")

        if not brand_name:
            return messages

        identity_msg = (
            f'[系统身份 — 最高优先级] 你是「{brand_name}」的旅行顾问。'
            f'当用户问你是谁时，必须以「我是{brand_name}的旅行顾问」开头回答。'
            f'禁止说「我不是某一家旅行社」或自称平台/助手。'
        )

        return [{"role": "system", "content": identity_msg}] + list(messages)

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """封装 LLM 调用 — 自动注入旅行社品牌身份 + 回复修正"""
        result = await self.llm.chat(
            system=self._build_system_prompt(),
            messages=self._inject_identity_to_messages(messages),
            tools=tools,
        )
        # 修正 LLM 编造的虚假身份
        if isinstance(result, dict) and "content" in result:
            result["content"] = self._fix_identity_in_reply(result["content"])
        return result

    async def call_llm_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str = "",
    ) -> str:
        """流式 LLM 调用 — 边生成边推送到 stream queue，返回完整文本

        自动注入旅行社品牌身份到 system prompt 和消息列表（双重保险）。
        """
        from services.stream_context import get_stream_queue

        queue = get_stream_queue()
        full_text = ""

        async for token in self.llm.chat_stream(
            system=self._build_system_prompt(system),
            messages=self._inject_identity_to_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            full_text += token
            if queue:
                await queue.put(("token", token))

        # 修正 LLM 编造的虚假身份
        return self._fix_identity_in_reply(full_text)
