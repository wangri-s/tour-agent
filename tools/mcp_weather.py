"""MCP 天气工具 — LangChain @tool 适配层

内部直接调用 mcp_servers.weather.open_meteo (同进程, 零 MCP 开销)。
同时 MCP Server 对外暴露相同功能给外部 MCP 客户端。

数据源: Open-Meteo (免费, 无 API Key, 全球覆盖)

与旧版 weather_api.py 的区别:
  - 数据源: Open-Meteo (免费) vs 和风天气 (需要 API Key)
  - 协议: 同时支持 MCP 协议 (外部) + LangChain @tool (内部)
  - 城市覆盖: 50+ 城市 + geocoding 在线查找
"""

from __future__ import annotations

import json
import logging

from langchain.tools import tool

from mcp_servers.weather.open_meteo import get_weather_for_city
from mcp_servers.weather.city_coords import get_coords, search_city, get_all_city_names

logger = logging.getLogger(__name__)


@tool
async def mcp_get_weather(
    city: str,
    start_date: str = "",
    end_date: str = "",
    forecast_days: int = 7,
) -> str:
    """查询城市实时天气和预报 — 基于 Open-Meteo API

    获取指定城市的当前天气、每日预报、穿衣建议和出行提示。
    用于行程规划时的天气查询。

    Args:
        city: 目的地城市名 (中文或英文), 如 "北京", "西安", "Chengdu"
        start_date: 行程开始日期 (YYYY-MM-DD), 如 "2026-10-20"
        end_date: 行程结束日期 (可选, YYYY-MM-DD)
        forecast_days: 预报天数 (1-16, 默认7)

    Returns:
        JSON 格式的天气预报，包含:
        - current: 当前天气 (温度/湿度/天气状况/风速)
        - daily: 每日详细预报 (最高/最低温/天气/降水/风速)
        - summary: 行程期间天气总结
        - clothing_advice: 穿衣建议
        - travel_tip: 出行提示 (含恶劣天气预警)

    Example:
        mcp_get_weather("北京", "2026-10-20", "2026-10-25")
        mcp_get_weather("成都", forecast_days=5)
    """
    logger.info(
        "[MCP Weather] 查询: city=%s, start=%s, end=%s, days=%s",
        city, start_date, end_date, forecast_days,
    )

    try:
        data = await get_weather_for_city(city, start_date, end_date, forecast_days)
    except Exception as e:
        logger.error("[MCP Weather] 查询失败: %s", e)
        return json.dumps({
            "error": f"天气查询失败: {e}",
            "source": "Open-Meteo (异常)",
            "hint": f"请检查城市名是否正确。支持: {', '.join(get_all_city_names()[:25])}...",
        }, ensure_ascii=False)

    # 处理城市未找到
    if "error" in data:
        logger.warning("[MCP Weather] 城市未找到: %s", city)
        return json.dumps({
            "error": data["error"],
            "source": data.get("source", "Open-Meteo (失败)"),
            "hint": f"请确认城市名。支持的城市: {', '.join(get_all_city_names()[:25])}...",
            "try_search": f"可以尝试 mcp_search_city('{city}') 模糊搜索",
        }, ensure_ascii=False)

    # 构建返回 (兼容旧接口格式)
    result = {
        "city": data["city"],
        "city_en": data["city_en"],
        "lat": data["lat"],
        "lon": data["lon"],
        "source": data["source"],
        "current": data["current"],
        "daily": data["daily"],
        "summary": data["summary"],
        "clothing_advice": data["clothing_advice"],
    }

    # 统计恶劣天气天数
    bad_days = sum(
        1 for d in data["daily"]
        if d["weather_code"] in (45, 48, 63, 65, 67, 73, 75, 82, 86, 95, 96, 99)
    )
    result["bad_weather_days"] = bad_days
    result["travel_tip"] = (
        f"⚠️ 有 {bad_days} 天可能受天气影响，建议准备备用室内方案"
        if bad_days > 0
        else "✅ 行程期间天气良好，适合出游"
    )

    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
async def mcp_search_city(query: str) -> str:
    """模糊搜索城市名 — 当不确定城市确切名字时使用

    Args:
        query: 搜索关键词, 如 "西", "hang", "大理"

    Returns:
        JSON 格式的匹配城市列表
    """
    results = search_city(query, limit=10)
    return json.dumps({
        "query": query,
        "results": results,
        "count": len(results),
        "hint": "使用其中的 name 字段作为 city 参数" if results else f"未找到匹配 '{query}' 的城市",
    }, ensure_ascii=False, indent=2)


# 兼容别名 (方便从旧代码迁移)
mcp_weather_tool = mcp_get_weather
mcp_weather_search = mcp_search_city
