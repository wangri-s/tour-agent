"""上下文压缩服务 — 长对话自动摘要压缩

策略:
  1. 滑动窗口: 保留最近 N 轮完整消息
  2. 历史压缩: 超出窗口的消息用 LLM 生成渐进式摘要
  3. Token 估算: 中文 ~1.5 字符/token
  4. 压缩阈值: 模型上下文窗口的 65% (qwen-max 8K → 5200 tokens)
  5. 分层压缩: 短期(最近10轮)完整 + 中期摘要 + 长期关键信息

使用:
    compressor = ContextCompressor()
    compressed = await compressor.compress(messages, max_tokens=5200)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 从统一配置读取压缩参数，缺失时回退硬编码默认值
def _get_compression_config():
    try:
        from services.config_loader import config as cfg
        return {
            "chars_per_token": cfg.get_float("memory.context_compression.chars_per_token", 1.5),
            "model_context_window": cfg.get_int("memory.context_compression.model_context_window", 8000),
            "compress_ratio": cfg.get_float("memory.context_compression.compress_ratio", 0.65),
            "recent_window": cfg.get_int("memory.context_compression.recent_window", 10),
        }
    except Exception:
        return {
            "chars_per_token": 1.5,
            "model_context_window": 8000,
            "compress_ratio": 0.65,
            "recent_window": 10,
        }

_comp_cfg = _get_compression_config()

# Token 估算: 中文约 1.5 字符/token
CHARS_PER_TOKEN = _comp_cfg["chars_per_token"]

# 模型上下文窗口 (tokens)
MODEL_CONTEXT_WINDOW = _comp_cfg["model_context_window"]

# 压缩阈值: 上下文窗口的 65% (留 35% 给输出)
COMPRESS_RATIO = _comp_cfg["compress_ratio"]
DEFAULT_MAX_TOKENS = int(MODEL_CONTEXT_WINDOW * COMPRESS_RATIO)

RECENT_WINDOW = _comp_cfg["recent_window"]
SUMMARY_PROMPT = """请将以下对话历史压缩为简洁摘要，保留关键信息:

关键信息类别:
1. 客户需求: 目的地、日期、人数、预算、偏好
2. 已确认信息: 哪些需求已确认
3. 待确认信息: 还有什么需要确认
4. 行程变更: 客户要求过什么修改
5. 情绪变化: 客户满意度变化

对话历史:
{history}

请用中文输出，每类 1-2 句，总长度不超过 300 字。"""


class ContextCompressor:
    """长对话压缩器

    用法:
        compressor = ContextCompressor(llm_gateway)
        compressed_msgs = await compressor.compress(all_messages)
    """

    def __init__(self, llm_gateway=None):
        self._llm = llm_gateway
        self._summaries: dict[str, str] = {}  # session_id → 累积摘要

    async def compress(
        self,
        messages: list[dict[str, str]],
        session_id: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> list[dict[str, str]]:
        """压缩消息列表到目标 token 数以内

        Args:
            messages: 完整消息历史 [{"role": "...", "content": "..."}]
            session_id: 会话 ID (用于累积摘要)
            max_tokens: 目标最大 token 数

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        total_chars = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = total_chars / CHARS_PER_TOKEN

        # 不需要压缩
        if estimated_tokens <= max_tokens:
            return messages

        logger.info(
            f"[Compressor] 压缩前: {len(messages)} 条消息, "
            f"~{estimated_tokens:.0f} tokens → 目标 ≤{max_tokens}"
        )

        # 分层: 近期窗口完整保留
        recent = messages[-RECENT_WINDOW:]
        older = messages[:-RECENT_WINDOW]

        if not older:
            return recent

        # 对历史生成摘要
        history_text = "\n".join(
            f"[{m['role']}]: {m['content'][:200]}"
            for m in older
        )

        summary = await self._generate_summary(history_text)

        # 累积摘要
        prev_summary = self._summaries.get(session_id, "")
        if prev_summary:
            summary = await self._merge_summaries(prev_summary, summary)
        self._summaries[session_id] = summary

        # 组装: 摘要 + 近期消息
        compressed = [{"role": "system", "content": f"[历史对话摘要]\n{summary}"}]
        compressed.extend(recent)

        new_chars = sum(len(m.get("content", "")) for m in compressed)
        new_tokens = new_chars / CHARS_PER_TOKEN
        logger.info(
            f"[Compressor] 压缩后: {len(compressed)} 条消息, "
            f"~{new_tokens:.0f} tokens (原 {len(messages)} 条)"
        )

        return compressed

    async def _generate_summary(self, history: str) -> str:
        """调用 LLM 生成摘要"""
        if not self._llm:
            return self._simple_summary(history)

        try:
            prompt = SUMMARY_PROMPT.format(history=history[:3000])
            result = await self._llm.chat(
                system="你是一个专业的对话摘要助手，擅长提取关键信息。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            return result.get("content", self._simple_summary(history))
        except Exception as e:
            logger.warning(f"[Compressor] LLM 摘要失败: {e}")
            return self._simple_summary(history)

    def _simple_summary(self, history: str) -> str:
        """简单规则摘要 (LLM 不可用时)"""
        lines = history.split("\n")
        key_lines = []
        keywords = ["目的地", "天数", "预算", "日期", "人数", "北京", "上海", "西安",
                      "成都", "桂林", "修改", "好的", "可以", "满意"]

        for line in lines:
            for kw in keywords:
                if kw in line:
                    key_lines.append(line.strip())
                    break

        if not key_lines:
            return f"历史共 {len(lines)} 条消息。"
        return "\n".join(key_lines[:10])

    async def _merge_summaries(self, old: str, new: str) -> str:
        """合并新旧摘要"""
        if not self._llm:
            return f"{old}\n{new}"

        try:
            prompt = f"将以下两段对话摘要合并为一段简洁摘要(不超过300字):\n\n[历史摘要]\n{old}\n\n[新摘要]\n{new}"
            result = await self._llm.chat(
                system="你是一个专业的摘要合并助手。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
            )
            return result.get("content", f"{old}\n{new}")
        except Exception:
            return f"{old}\n{new}"


# 全局实例 (懒初始化)
compressor: ContextCompressor | None = None


def get_compressor(llm_gateway=None) -> ContextCompressor:
    global compressor
    if compressor is None:
        compressor = ContextCompressor(llm_gateway)
    return compressor
