"""Open-Meteo 天气 API 客户端

完全免费，无需 API Key，全球覆盖。
API 文档: https://open-meteo.com/en/docs

限制:
  - 免费层: 10,000 calls/day
  - 预报天数: 最多 16 天
  - 历史数据: 支持回溯 (适合行前规划)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from .city_coords import get_coords, CityCoord
from .weather_codes import (
    get_weather_desc,
    get_weather_emoji,
    get_comfort_level,
    get_clothing_advice,
    format_weather_summary,
    is_bad_weather,
)

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"

# Open-Meteo 免费 API 最大预报天数
MAX_FORECAST_DAYS = 16

# 缓存 HTTP 客户端 (复用连接)
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    return _client


# =========================================================================
# 核心 API 调用
# =========================================================================


async def fetch_weather(
    lat: float,
    lon: float,
    start_date: str = "",
    end_date: str = "",
    forecast_days: int = 7,
) -> dict[str, Any]:
    """调用 Open-Meteo Forecast API

    Args:
        lat: 纬度
        lon: 经度
        start_date: 开始日期 (YYYY-MM-DD), 超过 16 天自动忽略
        end_date: 结束日期 (YYYY-MM-DD), 超过 16 天自动忽略
        forecast_days: 预报天数 (1-16)

    Returns:
        Open-Meteo API 原始 JSON 响应
    """
    today = date.today()
    max_date = today + timedelta(days=MAX_FORECAST_DAYS)

    # 日期校验: 超出预报范围的日期自动忽略，改查默认 7 天
    effective_start = start_date
    effective_end = end_date
    if start_date:
        try:
            sd = date.fromisoformat(start_date)
            if sd > max_date:
                logger.info(
                    "[Open-Meteo] start_date=%s 超出 %d 天预报范围, 使用默认预报",
                    start_date, MAX_FORECAST_DAYS,
                )
                effective_start = ""
                effective_end = ""
        except ValueError:
            effective_start = ""
            effective_end = ""

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max",
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        "timezone": "Asia/Shanghai",
        "forecast_days": min(forecast_days, MAX_FORECAST_DAYS),
    }

    if effective_start:
        params["start_date"] = effective_start
    if effective_end:
        params["end_date"] = effective_end

    client = await _get_client()
    try:
        resp = await client.get(OPEN_METEO_FORECAST, params=params)
        resp.raise_for_status()
        data = resp.json()
        logger.debug(
            "[Open-Meteo] %s,%s 天气获取成功 (forecast_days=%s)",
            lat, lon, forecast_days,
        )
        return data
    except httpx.HTTPError as e:
        logger.error("[Open-Meteo] API 请求失败: %s", e)
        raise


async def search_location(name: str, count: int = 5) -> list[dict]:
    """通过地名搜索经纬度 (Geocoding API)

    用于处理不在内置坐标库中的城市。

    Args:
        name: 城市名称
        count: 返回结果数

    Returns:
        [{"name": "北京", "lat": 39.9, "lon": 116.4, "country": "China"}, ...]
    """
    params = {"name": name, "count": count, "language": "zh", "format": "json"}

    client = await _get_client()
    try:
        resp = await client.get(OPEN_METEO_GEOCODING, params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            results.append({
                "name": r.get("name", ""),
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
                "country": r.get("country", ""),
                "admin1": r.get("admin1", ""),  # 省/州
            })
        return results
    except httpx.HTTPError as e:
        logger.error("[Open-Meteo] Geocoding 失败: %s", e)
        return []


# =========================================================================
# 结构化天气数据
# =========================================================================


async def get_weather_for_city(
    city: str,
    start_date: str = "",
    end_date: str = "",
    forecast_days: int = 7,
) -> dict[str, Any]:
    """获取城市天气 — 结构化返回

    这是 trip_planner 调用的主要入口。

    Args:
        city: 城市名 (中文/拼音/英文)
        start_date: 行程开始日期 (YYYY-MM-DD)
        end_date: 行程结束日期 (YYYY-MM-DD)
        forecast_days: 预报天数

    Returns:
        {
            "city": "北京",
            "city_en": "Beijing",
            "lat": 39.9,
            "lon": 116.4,
            "current": { ... },     # 当前天气
            "daily": [ ... ],       # 每日预报
            "summary": "...",       # 行程天气总结
            "clothing_advice": "...",  # 穿衣建议
            "source": "Open-Meteo (实时)"
        }
    """
    coords = get_coords(city)
    if not coords:
        # 尝试 geocoding 查找
        locations = await search_location(city, count=1)
        if locations:
            loc = locations[0]
            coords = CityCoord(loc["lat"], loc["lon"], loc["name"])
        else:
            return {"error": f"未找到城市: {city}", "source": "Open-Meteo (失败)"}

    lat, lon, name_en = coords

    # 检测日期是否超出预报范围
    today = date.today()
    max_forecast = today + timedelta(days=MAX_FORECAST_DAYS)
    date_note = ""
    if start_date:
        try:
            sd = date.fromisoformat(start_date)
            if sd > max_forecast:
                date_note = (
                    f"⚠️ 行程日期 {start_date} 超出 {MAX_FORECAST_DAYS} 天预报范围，"
                    f"以下为当前 {forecast_days} 天预报作为气候参考。"
                    f"实际出行日期临近时天气可能有变化，建议出发前重新查询。"
                )
        except ValueError:
            pass

    try:
        raw = await fetch_weather(lat, lon, start_date, end_date, forecast_days)
    except Exception as e:
        logger.warning("[Weather] Open-Meteo 失败: %s, 城市=%s", e, city)
        return {"error": str(e), "source": "Open-Meteo (失败)"}

    # 解析当前天气
    current_raw = raw.get("current", {})
    current = {
        "temperature": current_raw.get("temperature_2m"),
        "humidity": current_raw.get("relative_humidity_2m"),
        "weather_code": current_raw.get("weather_code"),
        "weather": get_weather_desc(current_raw.get("weather_code", 0)),
        "weather_emoji": get_weather_emoji(current_raw.get("weather_code", 0)),
        "wind_speed": current_raw.get("wind_speed_10m"),
        "time": current_raw.get("time", ""),
    }

    # 解析每日预报
    daily_raw = raw.get("daily", {})
    daily = []
    dates = daily_raw.get("time", [])
    temps_max = daily_raw.get("temperature_2m_max", [])
    temps_min = daily_raw.get("temperature_2m_min", [])
    weather_codes = daily_raw.get("weather_code", [])
    precip = daily_raw.get("precipitation_sum", [])
    winds = daily_raw.get("wind_speed_10m_max", [])

    bad_days = 0
    for i in range(len(dates)):
        code = weather_codes[i] if i < len(weather_codes) else 0
        if is_bad_weather(code):
            bad_days += 1

        daily.append({
            "date": dates[i] if i < len(dates) else "",
            "temp_high": temps_max[i] if i < len(temps_max) else None,
            "temp_low": temps_min[i] if i < len(temps_min) else None,
            "weather_code": code,
            "weather": get_weather_desc(code),
            "weather_emoji": get_weather_emoji(code),
            "precipitation_mm": precip[i] if i < len(precip) else 0,
            "wind_kmh": winds[i] if i < len(winds) else 0,
        })

    # 行程天气总结
    if daily:
        highs = [d["temp_high"] for d in daily if d["temp_high"] is not None]
        lows = [d["temp_low"] for d in daily if d["temp_low"] is not None]
        avg_high = sum(highs) / len(highs) if highs else 0
        avg_low = sum(lows) / len(lows) if lows else 0

        comfort, _ = get_comfort_level((avg_high + avg_low) / 2)
        summary = (
            f"{daily[0]['date']} 至 {daily[-1]['date']} "
            f"平均 {avg_low:.0f}°C ~ {avg_high:.0f}°C, "
            f"体感{comfort}。"
        )
        if bad_days > 0:
            summary += f" 其中 {bad_days} 天可能有恶劣天气，建议关注。"
    else:
        summary = "暂无预报数据"

    # 穿衣建议
    clothing = get_clothing_advice(
        lows[0] if lows else 15,
        highs[0] if highs else 25,
        weather_codes[0] if weather_codes else 0,
    ) if daily else "暂无建议"

    result: dict[str, Any] = {
        "city": city,
        "city_en": name_en,
        "lat": lat,
        "lon": lon,
        "current": current,
        "daily": daily,
        "summary": summary,
        "clothing_advice": clothing,
        "source": "Open-Meteo (实时)",
    }
    if date_note:
        result["date_note"] = date_note
    return result


async def close_client():
    """关闭 HTTP 客户端"""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
