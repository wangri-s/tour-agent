"""城市天气查询工具 —— 第三方 API"""

from langchain_core.tools import tool


@tool
async def get_weather(city: str, date: str) -> str:
    """查询城市天气

    Args:
        city: 城市名 (中文或英文)
        date: 日期 (YYYY-MM-DD)

    Returns:
        JSON: {"city": str, "date": str, "weather": str, "temp_high": int, "temp_low": int, "rain_prob": float}
    """
    # TODO: 接入真实天气 API (和风天气 / OpenWeatherMap)
    import json

    return json.dumps({
        "city": city,
        "date": date,
        "weather": "晴转多云",
        "temp_high": 28,
        "temp_low": 18,
        "rain_prob": 0.2,
        "suitable": True,
    }, ensure_ascii=False)
