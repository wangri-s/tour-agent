"""Trip Planner Prompt v1 — 标准版 (默认)

适用场景: 大多数旅行社，中端客户
风格: 专业友好，四星酒店+打车+特色餐厅
"""

# 直接复用现有 prompt (保持向后兼容)
from prompts.trip_planner import TRIP_PLANNER_PROMPT as TRIP_PLANNER_V1_STANDARD

# 同时导出 PROMPT 别名 (供 prompt_manager 动态加载)
PROMPT = TRIP_PLANNER_V1_STANDARD
