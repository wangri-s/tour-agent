"""意图路由器节点 —— 结构化输出四类意图概率 + 转人工判断"""

from __future__ import annotations

import re
from typing import Any, cast

from graph.state import OverallState, PartialState, Branch
from agents.intent_router import IntentRouterAgent

# 转人工触发关键词 — 仅限明确要求人工介入的场景
HUMAN_HANDOFF_KEYWORDS: list[str] = [
    "投诉", "差评", "人工", "真人", "叫你们经理",
    "complaint", "dissatisfied",
]

# 补全参数模式 — 用户正在回答 agent 的追问，应路由回原分支
# 例: "三天"/"5天" → planner, "2人"/"3个人" → planner, "预算5000" → planner
TRIP_PARAM_PATTERNS: list[str] = [
    r"^\d+\s*天$",           # "三天", "5天", "3 天"
    r"^\d+\s*日$",           # "5日"
    r"^\d+\s*个?\s*人$",     # "2人", "3个人", "2 人"
    r"^预算\s*\d+",          # "预算5000", "预算 3000"
    r"^\d+\s*[块元]$",       # "5000块", "3000元"
    r"^\d+\s*[kKwW]$",       # "5k", "8K"
]

# 非行程关键词 — 即使用户在行程规划会话中，这些词也表明用户想问别的事
# 如身份询问、投诉、FAQ、订单操作等，不应路由到 planner
NON_TRIP_KEYWORDS: list[str] = [
    # 身份询问
    "旅行社", "你是", "你是谁", "哪个公司", "什么公司",
    # 投诉/情绪
    "投诉", "差评", "骗人", "太差",
    # 订单操作 (即使有行程上下文也应走 operations)
    "退款", "取消", "改签", "改期", "退票",
    "升级", "降级", "换房", "换酒店", "加床", "加人",
    # 签证/入境
    "签证", "入境",
    # 支付/汇率
    "支付", "付款", "支付宝", "微信支付", "汇率", "信用卡",
    # 天气/安全
    "天气", "安全", "紧急", "报警",
]

# 订单操作动作词 — 有行程上下文时，这些词表明用户想修改/操作订单
# 直接路由到 operations，不经过 LLM（确定性高，0ms）
# 支持短语和单字组合（如"加一张床"→匹配"加"+"床"）
ORDER_ACTION_KEYWORDS: list[str] = [
    # 取消/退款
    "退款", "退票", "退房", "取消订单", "取消行程",
    # 改期
    "改签", "改期", "换个日期", "换个时间", "改到",
    # 升级/降级
    "升级", "降级",
    # 换酒店/换房
    "换房", "换个酒店", "换酒店", "换个房",
    # 加人/加床
    "加床", "加人", "加一个人", "多加", "加一张床", "加个床",
    # 减人
    "减人", "减少一个人",
]
# 分散匹配：单字组合 (如"加一张床"中"加"和"床"分开了)
ORDER_ACTION_PAIRS: list[tuple[str, str]] = [
    ("换", "酒店"), ("换", "房"), ("换", "日期"), ("换", "时间"),
    ("加", "床"), ("加", "人"), ("加", "进去"),
    ("减", "人"), ("减", "床"),
    ("退", "票"), ("退", "款"), ("退", "房"),
    ("改", "日期"), ("改", "时间"), ("改", "到"),
]

_router = IntentRouterAgent()


def _is_trip_param(text: str) -> bool:
    """检测消息是否为行程参数补全 (回答追问)"""
    for pat in TRIP_PARAM_PATTERNS:
        if re.match(pat, text.strip()):
            return True
    return False


def _has_trip_context(state: OverallState) -> bool:
    """检测会话上下文中是否已有行程规划进行中"""
    need = state.get("need") if isinstance(state, dict) else getattr(state, "need", None)
    if need is None:
        return False
    if isinstance(need, dict):
        return bool(need.get("destination"))
    return bool(getattr(need, "destination", ""))


async def intent_router(state: OverallState) -> PartialState:
    """意图识别 + 转人工前置判断

    1. 关键词命中 → need_human=True, 跳过模型调用
    2. 行程参数补全 (数字+单位) → 直接路由到 planner
    3. 否则调用轻量模型输出四类概率
    4. 最高概率 < 0.3 → 兜底进入客服
    """

    msgs: list[Any] = state.get("messages", []) if isinstance(state, dict) else state.messages
    last_msg = msgs[-1] if msgs else None
    if last_msg is None:
        return cast(PartialState, {"current_branch": Branch.SERVICE.value})

    text: str = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # ---- 关键词拦截: 投诉转人工 ----
    if any(kw in text.lower() for kw in HUMAN_HANDOFF_KEYWORDS):
        return cast(PartialState, {
            "need_human": True,
            "current_branch": Branch.SERVICE.value,
        })

    # ---- 订单操作关键词: 有行程上下文时直接走 operations (0ms, 不调LLM) ----
    has_context = _has_trip_context(state)
    is_order_action = (
        any(kw in text for kw in ORDER_ACTION_KEYWORDS) or
        any(a in text and b in text for a, b in ORDER_ACTION_PAIRS)
    )
    if is_order_action and has_context:
        return cast(PartialState, {
            "current_branch": Branch.OPERATIONS.value,
            "intent_scores": {"operations": 0.90, "service": 0.05, "sales": 0.02, "planner": 0.03},
        })

    # ---- 行程参数补全: 用户正在回答规划师的追问 ----
    # 条件: (参数模式匹配) OR (有行程上下文 AND 不是明显的非行程问题)
    is_param = _is_trip_param(text)
    is_non_trip = any(kw in text for kw in NON_TRIP_KEYWORDS)

    if is_param or (has_context and not is_non_trip):
        # 参数补全 或 在规划会话中且不是非行程问题 → 走 planner
        return cast(PartialState, {
            "current_branch": Branch.PLANNER.value,
            "intent_scores": {"planner": 0.9, "service": 0.05, "sales": 0.03, "operations": 0.02},
        })

    # ---- 模型路由 ----
    result: dict[str, Any] = await _router.classify(text)

    branch: str = result.get("branch", Branch.SERVICE.value)
    raw_scores: dict[str, Any] = result.get("scores", {})
    valid_branches = {"service", "sales", "operations", "planner"}
    scores: dict[str, float] = {
        k: float(v) for k, v in raw_scores.items()
        if k in valid_branches and isinstance(v, (int, float))
    }

    # 最高概率兜底
    if scores and max(scores.values()) < 0.3:
        branch = Branch.SERVICE.value

    return cast(PartialState, {
        "current_branch": branch,
        "intent_scores": scores,
        "need_human": bool(result.get("need_human", False)),
    })
