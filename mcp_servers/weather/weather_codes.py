"""WMO 天气代码 → 中文描述 + Emoji

Open-Meteo 使用 WMO (World Meteorological Organization) 标准天气代码。
参考: https://open-meteo.com/en/docs#weathervariables

代码范围:
  0:        晴天
  1-3:      多云
  45, 48:   雾/霾
  51-55:    毛毛雨
  61-65:    雨
  66-67:    冻雨
  71-77:    雪
  80-82:    阵雨
  85-86:    阵雪
  95-99:    雷暴
"""

from __future__ import annotations

# WMO 代码 → (中文描述, emoji, 是否影响出行)
_WMO_MAP: dict[int, tuple[str, str, bool]] = {
    0:  ("晴天", "☀️", False),
    1:  ("大部晴朗", "🌤️", False),
    2:  ("多云", "⛅", False),
    3:  ("阴天", "☁️", False),
    45: ("雾", "🌫️", True),
    48: ("冻雾/霾", "🌫️", True),
    51: ("小毛毛雨", "🌦️", False),
    53: ("中毛毛雨", "🌦️", False),
    55: ("大毛毛雨", "🌧️", False),
    56: ("冻毛毛雨", "🌧️❄️", True),
    57: ("冻毛毛雨", "🌧️❄️", True),
    61: ("小雨", "🌧️", False),
    63: ("中雨", "🌧️", True),
    65: ("大雨", "🌧️", True),
    66: ("小冻雨", "🌧️❄️", True),
    67: ("大冻雨", "🌧️❄️", True),
    71: ("小雪", "🌨️", False),
    73: ("中雪", "🌨️", True),
    75: ("大雪", "❄️", True),
    77: ("雪粒", "🌨️", False),
    80: ("小阵雨", "🌦️", False),
    81: ("中阵雨", "🌧️", True),
    82: ("大阵雨/暴雨", "⛈️", True),
    85: ("小阵雪", "🌨️", False),
    86: ("大阵雪", "❄️", True),
    95: ("雷暴", "⛈️", True),
    96: ("雷暴+小冰雹", "⛈️🧊", True),
    99: ("雷暴+大冰雹", "⛈️🧊", True),
}

# 温度舒适度判断
_COMFORT_ZONES = [
    (range(18, 27), "非常舒适", "🟢"),
    (range(10, 18), "较凉", "🟡"),
    (range(27, 33), "较热", "🟡"),
    (range(0, 10), "寒冷", "🔵"),
    (range(33, 40), "炎热", "🟠"),
    (range(-30, 0), "严寒", "🔴"),
    (range(40, 100), "酷热", "🔴"),
]


def get_weather_desc(code: int) -> str:
    """获取天气代码的中文描述"""
    return _WMO_MAP.get(code, ("未知天气", "❓", False))[0]


def get_weather_emoji(code: int) -> str:
    """获取天气代码的 emoji"""
    return _WMO_MAP.get(code, ("未知", "❓", False))[1]


def is_bad_weather(code: int) -> bool:
    """判断是否影响出行的恶劣天气"""
    return _WMO_MAP.get(code, ("未知", "❓", False))[2]


def get_comfort_level(temp_c: float) -> tuple[str, str]:
    """获取温度舒适度等级

    Returns:
        (舒适度描述, emoji)
    """
    t = int(temp_c)
    for temp_range, desc, emoji in _COMFORT_ZONES:
        if t in temp_range:
            return desc, emoji
    return "未知", "⚪"


def format_weather_summary(
    city: str,
    date_str: str,
    temp_high: float,
    temp_low: float,
    weather_code: int,
    precipitation: float = 0,
    wind_speed: float = 0,
    humidity: float = 0,
) -> str:
    """格式化单日天气摘要 (中文友好)

    Returns:
        "北京 10月20日: ☀️ 晴天, 8°C ~ 20°C, 降水0mm, 适合出游"
    """
    emoji = get_weather_emoji(weather_code)
    desc = get_weather_desc(weather_code)
    comfort, _ = get_comfort_level((temp_high + temp_low) / 2)

    parts = [
        f"{emoji} {desc}",
        f"{temp_low:.0f}°C ~ {temp_high:.0f}°C",
        f"体感{comfort}",
    ]

    if precipitation > 0:
        parts.append(f"降水{precipitation:.1f}mm")
    if wind_speed > 5:
        parts.append(f"风速{wind_speed:.0f}km/h")

    bad = is_bad_weather(weather_code)
    travel_tip = "⚠️ 注意天气影响" if bad else "✅ 适合出游"

    return f"{date_str}: {' | '.join(parts)} | {travel_tip}"


def get_clothing_advice(temp_low: float, temp_high: float, weather_code: int) -> str:
    """根据温度和天气给出穿衣建议

    Returns:
        穿衣建议文本
    """
    avg = (temp_low + temp_high) / 2
    is_rain = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99)
    is_snow = weather_code in (71, 73, 75, 77, 85, 86)

    if avg >= 28:
        base = "轻薄夏装 (T恤、短裤、裙子)"
        if is_rain:
            base += "，带雨伞/防晒衣"
        else:
            base += "，注意防晒"
    elif avg >= 20:
        base = "夏秋过渡装 (薄长袖、衬衫、薄外套)"
        if is_rain:
            base += "，带雨具"
    elif avg >= 10:
        base = "春秋装 (卫衣、夹克、薄毛衣)"
        if is_rain:
            base += "，带雨伞"
    elif avg >= 0:
        base = "冬装 (厚外套、毛衣、围巾)"
        if is_snow:
            base += "，防滑鞋、手套"
    else:
        base = "厚冬装 (羽绒服、保暖内衣、帽子手套)"
        if is_snow:
            base += "，注意防滑"

    # 早晚温差大
    if temp_high - temp_low > 12:
        base += "。早晚温差大，建议带可穿脱的外套"

    return base
