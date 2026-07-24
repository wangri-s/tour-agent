"""天气 MCP Server — Open-Meteo 实时天气

基于 FastMCP 框架，提供 3 个工具:
  1. get_current_weather  — 当前实时天气
  2. get_forecast_7days   — 7 天预报
  3. get_trip_weather     — 行程天气 (日期范围 + 穿衣建议)

数据源: Open-Meteo (完全免费, 无需 API Key, 全球覆盖)

运行方式:
  # 开发模式 (stdio)
  python -m mcp_servers.weather.server

  # HTTP 模式 (生产)
  python -m mcp_servers.weather.server --http --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from typing import Any

from fastmcp import FastMCP

from .open_meteo import get_weather_for_city, search_location, close_client
from .city_coords import get_coords, search_city as local_search_city, get_all_city_names

logger = logging.getLogger(__name__)

# =========================================================================
# FastMCP Server
# =========================================================================

mcp = FastMCP(
    "weather-mcp-server",
    version="1.0.0",
)

# 全局状态
_server_task: asyncio.Task | None = None
_http_port: int = 8765


# =========================================================================
# MCP Tools
# =========================================================================


@mcp.tool()
async def get_current_weather(city: str) -> str:
    """查询城市当前实时天气

    获取指定城市的当前温度、湿度、天气状况、风速等信息。

    Args:
        city: 城市名 (中文或英文), 如 "北京", "Shanghai", "西安", "Tokyo"

    Returns:
        JSON 格式的当前天气信息

    Example:
        get_current_weather("北京")
    """
    data = await get_weather_for_city(city, forecast_days=1)

    if "error" in data:
        return json.dumps({
            "error": data["error"],
            "hint": f"支持的城市: {', '.join(get_all_city_names()[:20])}...",
        }, ensure_ascii=False)

    return json.dumps({
        "city": data["city"],
        "city_en": data["city_en"],
        "temperature": data["current"]["temperature"],
        "humidity": data["current"]["humidity"],
        "weather": data["current"]["weather"],
        "weather_emoji": data["current"]["weather_emoji"],
        "wind_speed_kmh": data["current"]["wind_speed"],
        "clothing_advice": data["clothing_advice"],
        "source": data["source"],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_forecast_7days(city: str, days: int = 7) -> str:
    """查询城市未来 N 天天气预报

    获取每日最高/最低温度、天气状况、降水量、风速等。

    Args:
        city: 城市名 (中文或英文)
        days: 预报天数 (1-7, 默认 7)

    Returns:
        JSON 格式的未来天气预报

    Example:
        get_forecast_7days("成都", days=5)
    """
    data = await get_weather_for_city(city, forecast_days=min(days, 7))

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    forecast = []
    for d in data["daily"]:
        forecast.append({
            "date": d["date"],
            "temp_high": d["temp_high"],
            "temp_low": d["temp_low"],
            "weather": d["weather"],
            "weather_emoji": d["weather_emoji"],
            "precipitation_mm": d["precipitation_mm"],
            "wind_kmh": d["wind_kmh"],
        })

    return json.dumps({
        "city": data["city"],
        "city_en": data["city_en"],
        "forecast_days": len(forecast),
        "daily": forecast,
        "source": data["source"],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_trip_weather(city: str, start_date: str, end_date: str = "") -> str:
    """查询行程日期的天气 — trip_planner 专用

    根据行程的出发日期和天数，返回该时间段内的完整天气预报，
    包括每日详情、整体总结、穿衣建议和出行提示。

    这是行程规划 agent 调用的主要天气工具。

    Args:
        city: 目的地城市名 (中文或英文), 如 "北京"
        start_date: 行程开始日期, 格式 YYYY-MM-DD, 如 "2026-10-20"
        end_date: 行程结束日期 (可选), YYYY-MM-DD, 如 "2026-10-25"

    Returns:
        JSON 格式的行程天气预报 (含每日详情 + 总结 + 穿衣建议)

    Example:
        get_trip_weather("北京", "2026-10-20", "2026-10-25")
        get_trip_weather("桂林", "2026-11-01")  # 只给开始日期，自动查 7 天
    """
    if not city or not start_date:
        return json.dumps({
            "error": "缺少必要参数",
            "required": ["city", "start_date"],
            "example": 'get_trip_weather("北京", "2026-10-20", "2026-10-25")',
        }, ensure_ascii=False)

    data = await get_weather_for_city(city, start_date, end_date, forecast_days=7)

    if "error" in data:
        return json.dumps({
            "error": data["error"],
            "hint": f"请确认城市名正确。支持的城市: {', '.join(get_all_city_names()[:20])}...",
        }, ensure_ascii=False)

    # 构建行程专用的天气摘要
    daily_summary = []
    for d in data["daily"]:
        daily_summary.append(
            f"{d['date']}: {d['weather_emoji']} {d['weather']}, "
            f"{d['temp_low']:.0f}°C ~ {d['temp_high']:.0f}°C"
            + (f", 降水{d['precipitation_mm']:.1f}mm" if d['precipitation_mm'] > 0 else "")
        )

    bad_days = sum(
        1 for d in data["daily"]
        if d["weather_code"] in (45, 48, 63, 65, 67, 73, 75, 82, 86, 95, 96, 99)
    )

    return json.dumps({
        "city": data["city"],
        "city_en": data["city_en"],
        "lat": data["lat"],
        "lon": data["lon"],
        "current_weather": {
            "temperature": data["current"]["temperature"],
            "weather": data["current"]["weather"],
            "weather_emoji": data["current"]["weather_emoji"],
            "humidity": data["current"]["humidity"],
            "time": data["current"]["time"],
        },
        "trip_daily": [
            {
                "date": d["date"],
                "temp_high": d["temp_high"],
                "temp_low": d["temp_low"],
                "weather": d["weather"],
                "weather_emoji": d["weather_emoji"],
                "precipitation_mm": d["precipitation_mm"],
                "wind_kmh": d["wind_kmh"],
            }
            for d in data["daily"]
        ],
        "summary": data["summary"],
        "clothing_advice": data["clothing_advice"],
        "bad_weather_days": bad_days,
        "travel_tip": (
            f"⚠️ 有 {bad_days} 天可能受天气影响，建议准备备用室内方案"
            if bad_days > 0
            else "✅ 行程期间天气良好，适合出游"
        ),
        "source": data["source"],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def search_city_weather(query: str) -> str:
    """模糊搜索城市名

    当你不知道城市确切名字时使用此工具。

    Args:
        query: 搜索关键词, 如 "西", "Hang", "Tokyo"

    Returns:
        JSON 格式的匹配城市列表

    Example:
        search_city_weather("西")
    """
    results = local_search_city(query, limit=15)
    if not results:
        # 尝试在线 geocoding
        results = await search_location(query, count=10)

    return json.dumps({
        "query": query,
        "results": results,
        "count": len(results),
    }, ensure_ascii=False, indent=2)


# =========================================================================
# Server 生命周期管理
# =========================================================================


async def start_server(port: int = 8765) -> None:
    """在后台启动 MCP HTTP server (供 main.py lifespan 调用)

    Args:
        port: HTTP 监听端口
    """
    global _server_task, _http_port
    _http_port = port

    logger.info("[Weather MCP] 启动 HTTP Server: http://127.0.0.1:%s", port)

    # FastMCP.run() 是阻塞的, 这里通过 asyncio.create_task 在后台运行
    # 但 FastMCP 3.x 的 run 会启动自己的 uvicorn server
    # 所以我们直接启动 uvicorn 来运行 FastMCP 的 ASGI app

    import uvicorn

    # FastMCP 3.x 的 http_app 方法
    app = mcp.http_app(path="/mcp")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    _server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)  # 等待启动

    logger.info("[Weather MCP] HTTP Server 已启动: http://127.0.0.1:%s/mcp", port)


async def stop_server() -> None:
    """停止 MCP server"""
    global _server_task

    logger.info("[Weather MCP] 正在关闭...")

    if _server_task and not _server_task.done():
        _server_task.cancel()
        try:
            await _server_task
        except asyncio.CancelledError:
            pass

    await close_client()
    logger.info("[Weather MCP] 已关闭")


# =========================================================================
# 直接运行入口 (用于独立进程或调试)
# =========================================================================


def main():
    """CLI 入口: python -m mcp_servers.weather.server"""
    parser = argparse.ArgumentParser(description="Weather MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="http",
        help="传输协议 (default: http)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP 监听端口 (default: 8765)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.transport == "stdio":
        logger.info("[Weather MCP] 以 stdio 模式启动")
        mcp.run(transport="stdio")
    else:
        logger.info("[Weather MCP] 以 HTTP 模式启动: http://127.0.0.1:%s", args.port)
        mcp.run(transport="http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
