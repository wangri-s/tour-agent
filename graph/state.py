"""LangGraph 全局 State 定义

基于 MessagesState 扩展，统一承载会话上下文、路由信息、业务数据、控制字段与输出字段。
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


# =============================================================================
# 枚举
# =============================================================================

class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    WECHAT = "wechat"
    WEB = "web"
    MESSENGER = "messenger"
    TIKTOK = "tiktok"


class Branch(str, Enum):
    SERVICE = "service"        # 智能客服
    SALES = "sales"            # 销售
    OPERATIONS = "operations"  # 运营
    PLANNER = "planner"        # 旅游定制


class IntentLevel(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


class NextAction(str, Enum):
    REVISE = "revise"
    ACCEPT = "accept"
    GIVE_UP = "give_up"


# =============================================================================
# 业务数据模型
# =============================================================================

class TripNeed(BaseModel):
    """客户行程需求 —— 必填项 + 偏好项 + 特殊需求"""

    # 必填项
    destination: str = ""         # 目的地城市
    days: int = 0                 # 行程天数
    arrival_date: str = ""        # 抵达日期 (YYYY-MM-DD)
    pax: int = 0                  # 人数
    budget_per_person: float = 0  # 人均预算 (CNY)

    # 偏好项
    theme: str = ""               # 主题偏好 (历史文化 / 自然风光 / 美食 / 摄影 …)
    pace: str = ""                # 节奏偏好 (轻松 / 适中 / 紧凑)
    accommodation: str = ""       # 住宿偏好 (经济 / 舒适 / 豪华)
    dietary: str = ""             # 饮食要求

    # 特殊需求
    special_requests: str = ""

    def is_complete(self) -> bool:
        """检查五必填项是否全部齐全"""
        return all([
            self.destination,
            self.days > 0,
            self.arrival_date,
            self.pax > 0,
            self.budget_per_person > 0,
        ])

    def missing_fields(self) -> list[str]:
        """返回缺失的必填字段名"""
        missing: list[str] = []
        if not self.destination:
            missing.append("目的地 (destination)")
        if self.days <= 0:
            missing.append("天数 (days)")
        if not self.arrival_date:
            missing.append("抵达日期 (arrival_date)")
        if self.pax <= 0:
            missing.append("人数 (pax)")
        if self.budget_per_person <= 0:
            missing.append("人均预算 (budget_per_person)")
        return missing


class TripDraft(BaseModel):
    """行程草案"""

    version: int = 0                    # 修订版本号
    itinerary_md: str = ""              # Markdown 行程正文
    estimated_cost: float = 0           # 预估人均费用
    weather_summary: str = ""           # 目的地天气摘要
    highlights: list[str] = Field(default_factory=list)  # 每日亮点
    daily_notes: list[str] = Field(default_factory=list)  # 每日备注


class Quote(BaseModel):
    """报价单"""

    flights: float = 0
    hotels: float = 0
    transport: float = 0
    tickets: float = 0
    meals: float = 0
    guide: float = 0
    total: float = 0
    notes: str = ""


# =============================================================================
# 全局 State
# =============================================================================

class OverallState(MessagesState):
    """入境定制游全局会话 State

    所有四类 Agent 共享，由 LangGraph Checkpoint 持久化。
    """

    # ---- 渠道与会话 ----
    session_id: str = ""
    customer_id: str = ""
    channel: str = ""          # Channel 枚举值
    language: str = "zh"

    # ---- 路由 ----
    current_branch: str = ""   # Branch 枚举值
    intent_scores: dict[str, float] = Field(default_factory=dict)

    # ---- 业务数据 ----
    need: TripNeed = Field(default_factory=TripNeed)
    draft: TripDraft = Field(default_factory=TripDraft)
    revision_count: int = 0
    intent_level: str = ""     # IntentLevel 枚举值

    # ---- 控制 ----
    need_human: bool = False
    next_action: str = ""      # NextAction 枚举值
    collected_fields: list[str] = Field(default_factory=list)

    # ---- 输出 ----
    final_reply: str = ""
    quote: Optional[Quote] = None


# =============================================================================
# Reduced State（节点返回值用 TypedDict 标注 partial 更新）
# =============================================================================

class PartialState(TypedDict, total=False):
    """LangGraph 节点可返回的部分 State 字段"""

    messages: Annotated[list[Any], add_messages]
    session_id: str
    customer_id: str
    channel: str
    language: str
    current_branch: str
    intent_scores: dict[str, float]
    need: TripNeed
    draft: TripDraft
    revision_count: int
    intent_level: str
    need_human: bool
    next_action: str
    collected_fields: list[str]
    final_reply: str
    quote: Optional[Quote]
