"""真实天气 API 工具 —— 和风天气 (QWeather) + 内置气候数据库降级

和风天气免费订阅 (1000次/天):
- 注册: https://dev.qweather.com/
- API Key 配置在 .env: QWEATHER_API_KEY=xxx

降级策略:
  1. 和风天气 API 可用 → 实时天气 + 7日预报
  2. API 不可用/超限 → 回退内置气候数据库 (get_weather 的 _WEATHER_DB)

架构:
  用户查询 → [和风天气实时API] → 成功 → 返回真实数据
                                  → 失败 → 内置气候数据库兜底
"""

from __future__ import annotations

import os
import json
import logging
from datetime import date as dt_date
from datetime import datetime

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 和风天气城市 ID 映射 (主要旅游城市)
_CITY_IDS = {
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "成都": "101270100", "杭州": "101210100",
    "武汉": "101200100", "西安": "101110100", "重庆": "101040100",
    "青岛": "101120200", "长沙": "101250100", "南京": "101190100",
    "厦门": "101230200", "昆明": "101290100", "大连": "101070200",
    "天津": "101030100", "苏州": "101190400", "桂林": "101300500",
    "张家界": "101251100", "三亚": "101310200", "丽江": "101291400",
    "拉萨": "101140100", "哈尔滨": "101050100", "贵阳": "101260100",
    "乌鲁木齐": "101130100", "呼和浩特": "101080100", "南宁": "101300100",
}


@tool
async def get_real_weather(city: str, date: str = "") -> str:
    """查询中国城市真实天气 (和风天气 API)。

    返回指定城市的实时天气和7日预报，包括温度、湿度、风力、降水概率、
    穿衣建议和旅游适宜度评价。

    Args:
        city: 城市名 (中文，如：北京、上海、西安、成都)
        date: 可选日期 (YYYY-MM-DD)，不传则返回今天天气

    Returns:
        JSON: {city, current: {temp, humidity, wind, text},
               forecast: [{date, high, low, text, rain_prob}],
               advice: {clothes, suitable, tips}}
    """
    api_key = os.getenv("QWEATHER_API_KEY", "")

    if not api_key:
        logger.info("[WeatherAPI] 未配置 QWEATHER_API_KEY，降级到内置数据库")
        return await _fallback_weather(city, date)

    city_id = _CITY_IDS.get(city)
    if not city_id:
        # 未知城市 → 降级
        logger.info(f"[WeatherAPI] 未知城市 '{city}'，降级")
        return await _fallback_weather(city, date)

    try:
        import urllib.request
        import urllib.error

        # 1. 查实时天气
        current_url = (
            f"https://devapi.qweather.com/v7/weather/now"
            f"?location={city_id}&key={api_key}"
        )
        current_data = await _api_get(current_url)

        # 2. 查7日预报
        forecast_url = (
            f"https://devapi.qweather.com/v7/weather/7d"
            f"?location={city_id}&key={api_key}"
        )
        forecast_data = await _api_get(forecast_url)

        if not current_data or current_data.get("code") != "200":
            logger.warning(f"[WeatherAPI] API 返回异常: {current_data.get('code') if current_data else 'None'}")
            return await _fallback_weather(city, date)

        now = current_data.get("now", {})
        daily_list = forecast_data.get("daily", [])

        # 格式化输出
        current = {
            "temp": f"{now.get('temp', '?')}°C",
            "feels_like": f"{now.get('feelsLike', '?')}°C",
            "humidity": f"{now.get('humidity', '?')}%",
            "wind": f"{now.get('windDir', '?')} {now.get('windScale', '?')}级",
            "text": now.get("text", "未知"),
            "icon": now.get("icon", ""),
        }

        forecast = []
        for day in daily_list[:7]:
            forecast.append({
                "date": day.get("fxDate", ""),
                "high": f"{day.get('tempMax', '?')}°C",
                "low": f"{day.get('tempMin', '?')}°C",
                "text_day": day.get("textDay", ""),
                "text_night": day.get("textNight", ""),
                "rain_prob": f"{day.get('precip', '?')}%",
                "wind": f"{day.get('windDirDay', '?')} {day.get('windScaleDay', '?')}级",
            })

        # 生成旅游建议
        temp_high = int(now.get("temp", 20))
        advice = _generate_advice(temp_high, now.get("text", ""), now.get("humidity", "50"))

        result = {
            "source": "和风天气 (QWeather)",
            "city": city,
            "city_id": city_id,
            "current": current,
            "forecast": forecast,
            "advice": advice,
        }

        logger.info(f"[WeatherAPI] 获取 {city} 实时天气成功: {current['temp']} {current['text']}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"[WeatherAPI] 请求失败: {e}")
        return await _fallback_weather(city, date)


async def _api_get(url: str, timeout: int = 10) -> dict:
    """异步 HTTP GET"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tour-agent/0.3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"[WeatherAPI] HTTP GET 失败: {e}")
        return {}


def _generate_advice(temp: int, weather_text: str, humidity: str) -> dict:
    """根据天气数据生成旅游建议"""
    hum = int(humidity) if humidity.isdigit() else 50

    # 穿衣建议
    if temp >= 30:
        clothes = "短袖+防晒衣+遮阳帽"
    elif temp >= 22:
        clothes = "短袖+薄外套"
    elif temp >= 15:
        clothes = "薄外套+长裤"
    elif temp >= 5:
        clothes = "毛衣+厚外套"
    elif temp >= -5:
        clothes = "羽绒服+毛衣+帽子"
    else:
        clothes = "最厚羽绒服+帽子+手套+雪靴"

    # 适宜度
    if 15 <= temp <= 28 and hum < 70:
        suitable = "极佳 🌟🌟🌟🌟🌟"
        tips = "气候宜人，非常适合户外旅游"
    elif 5 <= temp <= 33 and hum < 85:
        suitable = "良好 🌟🌟🌟🌟"
        tips = "适合出行，注意适时添减衣物"
    else:
        suitable = "一般 🌟🌟🌟"
        tips = "注意天气变化，准备室内备选方案"

    # 雨天提醒
    if "雨" in weather_text:
        tips += "，建议携带雨具"
    elif "雪" in weather_text:
        tips += "，注意防滑保暖"
    elif "晴" in weather_text and temp >= 30:
        tips += "，注意防晒补水，避免正午户外活动"

    return {"clothes": clothes, "suitable": suitable, "tips": tips}


async def _fallback_weather(city: str, date: str) -> str:
    """降级到内置气候数据库"""
    from tools.get_weather import get_weather
    logger.info(f"[WeatherAPI] 降级到内置数据库: {city}")
    result = await get_weather.ainvoke({"city": city, "date": date or "2026-01-01"})
    data = json.loads(result)
    data["source"] = "内置气候数据库 (降级)"
    return json.dumps(data, ensure_ascii=False, indent=2)
