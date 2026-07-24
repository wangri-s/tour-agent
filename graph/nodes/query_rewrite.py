"""查询改写节点 — 错别字纠正 + 同义词规范化 + 模糊地名修正

在意图路由之前执行，用轻量模型 (qwen-turbo) 对用户输入做快速纠错，
提升下游意图识别和需求提取的准确率。

策略:
  1. 仅纠正明显错别字 (如 "背景"→"北京")
  2. 拼音/英文地名 → 标准中文名 (如 "beijing"→"北京")
  3. 模糊城市名补全 (如 "杭"→"杭州")
  4. 保留原始消息不变 (写入 state.original_message)
"""

from __future__ import annotations

import asyncio
import logging
import re

from graph.state import OverallState, PartialState
from services.llm_gateway import gateway_router

logger = logging.getLogger(__name__)

# 快速纠错 prompt — 只纠正明显错误，不改变语义
_REWRITE_PROMPT = """你是一个中文输入纠错助手。你的任务是对用户消息做最低限度的修正：

## 纠正规则（严格按顺序）
1. **错别字纠正**: 仅纠正明显同音/近音错字
   - "背景" → "北京"（当明显是地名时）
   - "悲伤" → "北京"
   - "成度" → "成都"
   - "柜门" → "桂林"
   - 其他明显音近错字

2. **拼音/英文地名 → 中文**:
   - "beijing" → "北京", "shanghai" → "上海"
   - "tokyo" → "东京", "seoul" → "首尔"

3. **模糊地名补全**（仅当地名明显时）:
   - "杭" → "杭州"（如果上下文是旅游）
   - "大" → 不要随便改！保留原样。除非上下文明确是"大理"。

4. **数字格式统一**:
   - "3日" / "3天" → 保留原样
   - "俩人" / "2人" → 保留原样

## 禁止事项
- ❌ 不要改变用户的核心意图
- ❌ 不要添加用户没有提到的信息
- ❌ 不要改写句式
- ❌ 不要纠正非地名的一般词汇
- ❌ 如果无法确定正确写法，保留原文

## 输出格式
只输出修正后的文本，不要解释，不要加引号或标记。
如果没有任何需要修正的地方，原样输出用户消息。

## 示例
输入: 我想去背景旅游5天
输出: 我想去北京旅游5天

输入: 三个银去悲伤
输出: 三个人去北京

输入: 推荐一下hangzhou的美食
输出: 推荐一下杭州的美食

输入: 帮我查一下签证政策
输出: 帮我查一下签证政策

---

用户消息: {message}

修正后:"""

# 常见错别字速查表 (补充 LLM 可能漏掉的)
_TYPO_FIXES: dict[str, str] = {
    "背景旅游": "北京旅游",
    "悲伤旅游": "北京旅游",
    "成度旅游": "成都旅游",
    "柜门旅游": "桂林旅游",
    "洗安": "西安",
    "航州": "杭州",
    "重亲": "重庆",
    "下门": "厦门",
    "三涯": "三亚",
}

# 拼音→中文城市名
_PINYIN_CITIES: dict[str, str] = {
    "beijing": "北京", "bj": "北京",
    "shanghai": "上海", "sh": "上海",
    "xian": "西安", "xi'an": "西安",
    "chengdu": "成都", "cd": "成都",
    "guilin": "桂林", "gl": "桂林",
    "guangzhou": "广州", "gz": "广州",
    "shenzhen": "深圳", "sz": "深圳",
    "hangzhou": "杭州", "hz": "杭州",
    "nanjing": "南京", "nj": "南京",
    "chongqing": "重庆", "cq": "重庆",
    "kunming": "昆明", "km": "昆明",
    "lijiang": "丽江",
    "lasa": "拉萨", "lhasa": "拉萨",
    "xiamen": "厦门", "xm": "厦门",
    "sanya": "三亚",
    "haerbin": "哈尔滨", "harbin": "哈尔滨",
    "wuhan": "武汉",
    "tianjin": "天津",
    "qingdao": "青岛",
    "dali": "大理",
    "luoyang": "洛阳",
    "tokyo": "东京",
    "seoul": "首尔",
    "bangkok": "曼谷",
    "singapore": "新加坡",
    "paris": "巴黎",
    "london": "伦敦",
    "new york": "纽约",
    "dubai": "迪拜",
}


def _quick_fix(text: str) -> str:
    """规则级快速纠错 (零延迟, LLM 前执行)"""
    fixed = text

    # 1. 整词替换 (错别字速查)
    for wrong, correct in _TYPO_FIXES.items():
        if wrong in fixed:
            fixed = fixed.replace(wrong, correct)
            logger.info("[QueryRewrite] 规则纠错: %s → %s", wrong, correct)

    # 2. 拼音城市名替换 (整词匹配, 不改变包含城市名的普通词)
    words = re.split(r'(\s+|[,，。！？、；：""''（）])', fixed)
    for i, word in enumerate(words):
        lower = word.lower().strip()
        if lower in _PINYIN_CITIES:
            words[i] = _PINYIN_CITIES[lower]
            logger.info("[QueryRewrite] 拼音→中文: %s → %s", word.strip(), _PINYIN_CITIES[lower])
    fixed = "".join(words)

    return fixed


async def _llm_rewrite(message: str, timeout: float = 3.0) -> str:
    """调用 qwen-turbo 做智能纠错 (超时则跳过)"""
    try:
        prompt = _REWRITE_PROMPT.format(message=message)
        result = await asyncio.wait_for(
            gateway_router.chat(
                system="你是一个中文纠错助手。只纠正错别字，不改变用户意图。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            ),
            timeout=timeout,
        )
        content = result.get("content", "").strip()
        # 清理 LLM 可能加的多余标记
        content = content.strip('"''「」""')
        if content and content != message:
            logger.info("[QueryRewrite] LLM 纠错: %s → %s", message[:50], content[:50])
            return content
    except asyncio.TimeoutError:
        logger.debug("[QueryRewrite] LLM 纠错超时 (%.1fs), 跳过", timeout)
    except Exception as e:
        logger.debug("[QueryRewrite] LLM 纠错异常: %s", e)

    return message


async def query_rewrite(state: OverallState) -> PartialState:
    """查询改写 — 错别字纠正 + 模糊地名修正

    流程:
      1. 取最后一条用户消息
      2. 规则级快速纠错 (拼音→中文, 常见错别字)
      3. LLM 智能纠错 (qwen-turbo, 3s 超时)
      4. 如修正成功 → 更新消息内容
      5. 如无变化 → 不修改
    """
    msgs = state.get("messages", []) if isinstance(state, dict) else state.messages
    last_msg = msgs[-1] if msgs else None
    if last_msg is None:
        return {}

    original = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # 规则级纠错
    fixed = _quick_fix(original)

    # LLM 纠错 (仅当规则纠错没变化时, 避免重复改)
    if fixed == original:
        fixed = await _llm_rewrite(original)
    else:
        # 规则已纠错, LLM 再做二次校对 (可选, 用更短超时)
        fixed = await _llm_rewrite(fixed)

    if fixed == original:
        return {}  # 无变化, 不修改 state

    logger.info("[QueryRewrite] 改写: %s → %s", original[:60], fixed[:60])

    # 替换最后一条消息
    new_msg = type(last_msg)(content=fixed)
    # 保留原始消息 (改写记录)
    if isinstance(state, dict):
        state["original_message"] = original
    else:
        state.original_message = original

    return {"messages": [new_msg]}  # type: ignore[return-value]
