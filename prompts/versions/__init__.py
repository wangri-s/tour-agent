"""Prompt 版本注册表

每个版本文件导出 PROMPT 变量，格式:
    PROMPT = "完整的 system prompt 文本..."

版本命名规范: v{major}_{variant}
  - v1_standard:  标准版 (全旅行社通用)
  - v2_luxury:    奢华版 (高端定制社)
  - v3_budget:    经济版 (青年/背包客社)
"""

from .trip_planner_v1 import TRIP_PLANNER_V1_STANDARD
from .trip_planner_v2 import PROMPT as TRIP_PLANNER_V2_LUXURY
from .trip_planner_v3 import PROMPT as TRIP_PLANNER_V3_BUDGET

__all__ = [
    "TRIP_PLANNER_V1_STANDARD",
    "TRIP_PLANNER_V2_LUXURY",
    "TRIP_PLANNER_V3_BUDGET",
]

# 版本元数据 (供 UI 展示)
VERSION_META = {
    "v1_standard": {
        "name": "标准版",
        "description": "全旅行社通用，兼顾舒适与性价比，适合大多数客户",
        "target": "中端客户 (人均 ¥1500-3500/天)",
        "tone": "专业友好",
        "hotel": "四星级",
        "created": "2026-07",
    },
    "v2_luxury": {
        "name": "奢华版",
        "description": "高端定制，五星酒店+私人导游+VIP体验，适合高净值客户",
        "target": "高端客户 (人均 ¥3500+/天)",
        "tone": "尊贵典雅",
        "hotel": "五星级+",
        "created": "2026-07",
    },
    "v3_budget": {
        "name": "经济版",
        "description": "极致性价比，青旅+公共交通+地道小吃，适合背包客和学生",
        "target": "预算客户 (人均 <¥1500/天)",
        "tone": "轻松活力",
        "hotel": "青旅/民宿",
        "created": "2026-07",
    },
}
