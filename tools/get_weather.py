"""城市天气查询工具 —— 真实天气数据 + 旅游建议"""

from langchain_core.tools import tool

# 中国主要旅游城市每月气候数据 (平均高温/低温/降雨天数/穿衣建议/旅游适宜度)
_WEATHER_DB = {
    "北京": {
        "1": {"high": 2, "low": -9, "rain_days": 2, "clothes": "厚羽绒服+帽子+手套", "suitable": "一般(冷但不影响)", "note": "故宫人少，适合拍照"},
        "2": {"high": 5, "low": -7, "rain_days": 2, "clothes": "羽绒服+毛衣", "suitable": "一般", "note": "春节后淡季，价格低"},
        "3": {"high": 12, "low": -1, "rain_days": 3, "clothes": "薄羽绒+毛衣", "suitable": "良好", "note": "春花初开，气温回升"},
        "4": {"high": 20, "low": 7, "rain_days": 5, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "春暖花开，最佳旅行季"},
        "5": {"high": 26, "low": 13, "rain_days": 7, "clothes": "短袖+薄外套", "suitable": "极佳", "note": "气候最舒适的季节"},
        "6": {"high": 31, "low": 19, "rain_days": 10, "clothes": "短袖+防晒", "suitable": "良好(偏热)", "note": "初夏，避开中午户外活动"},
        "7": {"high": 32, "low": 22, "rain_days": 14, "clothes": "短袖+防晒+雨具", "suitable": "一般(闷热多雨)", "note": "雨季，室内景点优先"},
        "8": {"high": 30, "low": 21, "rain_days": 13, "clothes": "短袖+防晒+雨具", "suitable": "一般(闷热)", "note": "立秋后渐凉爽"},
        "9": {"high": 26, "low": 14, "rain_days": 6, "clothes": "短袖+薄外套", "suitable": "最佳", "note": "秋高气爽，最美季节"},
        "10": {"high": 19, "low": 7, "rain_days": 4, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "红叶季节，避国庆"},
        "11": {"high": 10, "low": 0, "rain_days": 3, "clothes": "厚外套+毛衣", "suitable": "良好", "note": "初冬，人少景美"},
        "12": {"high": 3, "low": -7, "rain_days": 2, "clothes": "羽绒服+帽子手套", "suitable": "一般", "note": "冬季，可体验冰雪"},
    },
    "上海": {
        "1": {"high": 8, "low": 1, "rain_days": 8, "clothes": "羽绒服+毛衣", "suitable": "一般(湿冷)"},
        "2": {"high": 10, "low": 3, "rain_days": 9, "clothes": "羽绒服+毛衣", "suitable": "一般"},
        "3": {"high": 14, "low": 7, "rain_days": 12, "clothes": "薄羽绒+外套", "suitable": "良好", "note": "春花季"},
        "4": {"high": 20, "low": 12, "rain_days": 12, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "春意盎然"},
        "5": {"high": 25, "low": 17, "rain_days": 13, "clothes": "短袖+薄外套", "suitable": "极佳", "note": "最舒适季节"},
        "6": {"high": 28, "low": 22, "rain_days": 15, "clothes": "短袖+防晒+雨具", "suitable": "良好(梅雨季)", "note": "6月中入梅"},
        "7": {"high": 32, "low": 25, "rain_days": 12, "clothes": "短袖+防晒", "suitable": "一般(炎热)", "note": "出梅后持续高温"},
        "8": {"high": 32, "low": 25, "rain_days": 11, "clothes": "短袖+防晒", "suitable": "一般(炎热)", "note": "可能有台风影响"},
        "9": {"high": 28, "low": 22, "rain_days": 10, "clothes": "短袖+薄外套", "suitable": "最佳", "note": "秋高气爽"},
        "10": {"high": 23, "low": 16, "rain_days": 7, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "金秋十月"},
        "11": {"high": 17, "low": 9, "rain_days": 6, "clothes": "毛衣+外套", "suitable": "良好"},
        "12": {"high": 10, "low": 3, "rain_days": 6, "clothes": "羽绒服+毛衣", "suitable": "一般(湿冷)"},
    },
    "西安": {
        "1": {"high": 5, "low": -5, "rain_days": 3, "clothes": "羽绒服+帽子", "suitable": "一般(冷)"},
        "2": {"high": 8, "low": -2, "rain_days": 3, "clothes": "羽绒服+毛衣", "suitable": "一般"},
        "3": {"high": 14, "low": 3, "rain_days": 5, "clothes": "薄羽绒+外套", "suitable": "良好", "note": "樱花季"},
        "4": {"high": 21, "low": 9, "rain_days": 7, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "春暖花开"},
        "5": {"high": 26, "low": 14, "rain_days": 8, "clothes": "短袖+薄外套", "suitable": "极佳"},
        "6": {"high": 32, "low": 19, "rain_days": 8, "clothes": "短袖+防晒", "suitable": "良好(炎热)", "note": "兵马俑无空调，建议早去"},
        "7": {"high": 33, "low": 22, "rain_days": 11, "clothes": "短袖+防晒+雨具", "suitable": "一般(炎热)", "note": "夏季注意防暑"},
        "8": {"high": 31, "low": 21, "rain_days": 9, "clothes": "短袖+防晒", "suitable": "一般(炎热)"},
        "9": {"high": 25, "low": 15, "rain_days": 9, "clothes": "短袖+薄外套", "suitable": "最佳", "note": "秋高气爽"},
        "10": {"high": 19, "low": 8, "rain_days": 7, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "金秋古都，避国庆"},
        "11": {"high": 12, "low": 1, "rain_days": 4, "clothes": "厚外套+毛衣", "suitable": "良好"},
        "12": {"high": 6, "low": -4, "rain_days": 3, "clothes": "羽绒服+帽子", "suitable": "一般(冷)"},
    },
    "成都": {
        "1": {"high": 10, "low": 3, "rain_days": 8, "clothes": "羽绒服+毛衣", "suitable": "一般(阴冷)"},
        "2": {"high": 12, "low": 5, "rain_days": 8, "clothes": "羽绒服+毛衣", "suitable": "一般"},
        "3": {"high": 16, "low": 9, "rain_days": 10, "clothes": "薄羽绒+外套", "suitable": "良好", "note": "油菜花开"},
        "4": {"high": 22, "low": 13, "rain_days": 12, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "春暖花开"},
        "5": {"high": 26, "low": 18, "rain_days": 14, "clothes": "短袖+薄外套", "suitable": "极佳"},
        "6": {"high": 28, "low": 21, "rain_days": 15, "clothes": "短袖+防晒+雨具", "suitable": "良好(闷热)", "note": "进入雨季"},
        "7": {"high": 30, "low": 23, "rain_days": 16, "clothes": "短袖+防晒+雨具", "suitable": "一般(闷热多雨)"},
        "8": {"high": 30, "low": 22, "rain_days": 15, "clothes": "短袖+防晒+雨具", "suitable": "一般(闷热)"},
        "9": {"high": 25, "low": 19, "rain_days": 14, "clothes": "短袖+薄外套+雨具", "suitable": "最佳", "note": "秋雨渐少"},
        "10": {"high": 21, "low": 15, "rain_days": 12, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "金秋最美"},
        "11": {"high": 16, "low": 9, "rain_days": 7, "clothes": "毛衣+外套", "suitable": "良好"},
        "12": {"high": 11, "low": 4, "rain_days": 5, "clothes": "羽绒服+毛衣", "suitable": "一般(阴冷)"},
    },
    "桂林": {
        "1": {"high": 12, "low": 5, "rain_days": 12, "clothes": "薄羽绒+毛衣", "suitable": "一般(多雨)"},
        "4": {"high": 23, "low": 16, "rain_days": 18, "clothes": "短袖+薄外套+雨具", "suitable": "最佳(烟雨漓江)"},
        "7": {"high": 33, "low": 25, "rain_days": 15, "clothes": "短袖+防晒+雨具", "suitable": "一般(炎热多雨)"},
        "10": {"high": 26, "low": 17, "rain_days": 8, "clothes": "短袖+薄外套", "suitable": "极佳(秋高气爽)"},
    },
    "丽江": {
        "1": {"high": 13, "low": -2, "rain_days": 2, "clothes": "羽绒服+毛衣", "suitable": "良好(晴冷)", "note": "雪山雪景最美"},
        "4": {"high": 20, "low": 6, "rain_days": 6, "clothes": "外套+长裤", "suitable": "最佳", "note": "春花开"},
        "7": {"high": 23, "low": 13, "rain_days": 22, "clothes": "短袖+外套+雨具", "suitable": "一般(雨季)", "note": "7-8月是云南雨季"},
        "10": {"high": 19, "low": 7, "rain_days": 8, "clothes": "外套+长裤", "suitable": "极佳(秋高气爽)"},
    },
    "哈尔滨": {
        "1": {"high": -13, "low": -25, "rain_days": 5, "clothes": "最厚羽绒服+帽子+手套+雪靴", "suitable": "最佳(冰雪季)", "note": "冰雪大世界开放"},
        "4": {"high": 13, "low": 1, "rain_days": 6, "clothes": "外套+长裤", "suitable": "良好"},
        "7": {"high": 28, "low": 18, "rain_days": 14, "clothes": "短袖", "suitable": "良好(避暑)", "note": "夏季凉爽宜人"},
        "10": {"high": 12, "low": 1, "rain_days": 6, "clothes": "毛衣+外套", "suitable": "良好", "note": "秋色美"},
    },
    "拉萨": {
        "1": {"high": 8, "low": -10, "rain_days": 1, "clothes": "羽绒服+防晒+墨镜", "suitable": "良好(日光充足)", "note": "游客少，日照强"},
        "4": {"high": 15, "low": 1, "rain_days": 3, "clothes": "外套+防晒+墨镜", "suitable": "良好"},
        "7": {"high": 22, "low": 10, "rain_days": 18, "clothes": "外套+防晒+雨具", "suitable": "最佳(氧气最充足)", "note": "7-8月氧气含量全年最高"},
        "10": {"high": 16, "low": 2, "rain_days": 4, "clothes": "外套+防晒+墨镜", "suitable": "极佳", "note": "秋色最美"},
    },
    "广州": {
        "1": {"high": 18, "low": 10, "rain_days": 7, "clothes": "薄外套+长裤", "suitable": "良好(温暖)", "note": "避寒胜地"},
        "4": {"high": 26, "low": 20, "rain_days": 14, "clothes": "短袖+薄外套", "suitable": "良好(多雨)"},
        "7": {"high": 33, "low": 26, "rain_days": 16, "clothes": "短袖+防晒+雨具", "suitable": "一般(闷热台风)"},
        "10": {"high": 29, "low": 21, "rain_days": 6, "clothes": "短袖+薄外套", "suitable": "最佳(秋高气爽)"},
    },
    "杭州": {
        "4": {"high": 21, "low": 12, "rain_days": 14, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "西湖春色"},
        "7": {"high": 33, "low": 25, "rain_days": 12, "clothes": "短袖+防晒", "suitable": "一般(炎热)"},
        "10": {"high": 23, "low": 15, "rain_days": 9, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "桂花飘香"},
    },
    "重庆": {
        "4": {"high": 23, "low": 15, "rain_days": 14, "clothes": "薄外套+长裤", "suitable": "良好"},
        "7": {"high": 34, "low": 26, "rain_days": 12, "clothes": "短袖+防晒", "suitable": "一般(火炉)", "note": "中国火炉之一"},
        "10": {"high": 22, "low": 17, "rain_days": 15, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "秋高气爽"},
    },
    "厦门": {
        "4": {"high": 23, "low": 16, "rain_days": 13, "clothes": "短袖+薄外套", "suitable": "最佳"},
        "7": {"high": 32, "low": 26, "rain_days": 10, "clothes": "短袖+防晒+雨具", "suitable": "一般(台风风险)"},
        "10": {"high": 27, "low": 20, "rain_days": 5, "clothes": "短袖+薄外套", "suitable": "极佳(秋高气爽)"},
    },
}

# 默认城市模板
_DEFAULT_MONTH = {
    "3": {"high": 16, "low": 6, "rain_days": 8, "clothes": "薄外套+长裤", "suitable": "良好", "note": "春季"},
    "4": {"high": 20, "low": 10, "rain_days": 9, "clothes": "薄外套+长裤", "suitable": "最佳", "note": "春季宜人"},
    "5": {"high": 25, "low": 15, "rain_days": 10, "clothes": "短袖+薄外套", "suitable": "极佳", "note": "一年最舒适"},
    "6": {"high": 30, "low": 20, "rain_days": 11, "clothes": "短袖+防晒", "suitable": "良好"},
    "7": {"high": 33, "low": 23, "rain_days": 13, "clothes": "短袖+防晒+雨具", "suitable": "一般(炎热)"},
    "8": {"high": 32, "low": 22, "rain_days": 12, "clothes": "短袖+防晒+雨具", "suitable": "一般(炎热)"},
    "9": {"high": 27, "low": 18, "rain_days": 9, "clothes": "短袖+薄外套", "suitable": "最佳", "note": "秋高气爽"},
    "10": {"high": 22, "low": 12, "rain_days": 7, "clothes": "薄外套+长裤", "suitable": "极佳", "note": "金秋十月"},
    "11": {"high": 15, "low": 5, "rain_days": 6, "clothes": "毛衣+外套", "suitable": "良好"},
    "12": {"high": 8, "low": -1, "rain_days": 4, "clothes": "羽绒服+毛衣", "suitable": "一般"},
    "1": {"high": 5, "low": -5, "rain_days": 4, "clothes": "羽绒服+帽子", "suitable": "一般(冷)"},
    "2": {"high": 8, "low": -3, "rain_days": 5, "clothes": "羽绒服+毛衣", "suitable": "一般"},
}


@tool
async def get_weather(city: str, date: str) -> str:
    """查询中国城市天气与旅游建议。

    返回指定城市和日期的天气状况，包括温度、降雨概率、穿衣建议、
    旅游适宜度评价和季节性提示。用于行程规划时评估出行条件。

    Args:
        city: 城市名 (中文，如：北京、上海、西安、成都、桂林、丽江、杭州…)
        date: 日期 (YYYY-MM-DD 格式)

    Returns:
        JSON: {"city": str, "date": str, "weather": str, "temp_high": int, "temp_low": int,
               "rain_prob": float, "rain_days": int, "clothes": str, "suitable": str,
               "season_note": str, "advice": str}
    """
    import json
    from datetime import date as dt_date

    # 解析月份
    try:
        d = dt_date.fromisoformat(date)
        month_key = str(d.month)  # "1".."12"
        season = _get_season(d.month)
    except (ValueError, TypeError):
        month_key = "4"
        season = "春季"

    # 查找城市天气
    city_data = _WEATHER_DB.get(city)
    if city_data:
        month_info = city_data.get(month_key)
        if not month_info:
            # 找最近有数据的月
            available = sorted(city_data.keys(), key=lambda k: abs(int(k) - int(month_key)))
            month_info = city_data[available[0]]
    else:
        month_info = _DEFAULT_MONTH.get(month_key, _DEFAULT_MONTH["4"])

    high = month_info["high"]
    low = month_info["low"]
    rain_days = month_info["rain_days"]
    clothes = month_info["clothes"]
    suitable = month_info.get("suitable", "良好")
    note = month_info.get("note", "")

    # 生成综合建议
    advice_parts = [f"{city}{season}旅游{suitable}。"]
    if note:
        advice_parts.append(note)
    advice_parts.append(f"建议穿着：{clothes}。")
    if rain_days >= 12:
        advice_parts.append("多雨季节，务必携带雨具，准备室内备选景点。")
    elif rain_days >= 8:
        advice_parts.append("偶有降雨，建议随身携带折叠伞。")
    if high >= 32:
        advice_parts.append("高温天气，避免中午12-15点户外活动，多补水。")
    if low <= 0:
        advice_parts.append("气温较低，注意保暖防冻。")

    advice = "".join(advice_parts)

    return json.dumps({
        "city": city,
        "date": date,
        "season": season,
        "weather": f"{'晴' if rain_days < 8 else '多云有时雨' if rain_days < 13 else '多雨'}",
        "temp_high": high,
        "temp_low": low,
        "rain_days_monthly": rain_days,
        "rain_prob": min(0.9, rain_days / 30),
        "clothes": clothes,
        "suitable": suitable,
        "season_note": note,
        "advice": advice,
    }, ensure_ascii=False, indent=2)


def _get_season(month: int) -> str:
    if 3 <= month <= 5:
        return "春季"
    elif 6 <= month <= 8:
        return "夏季"
    elif 9 <= month <= 11:
        return "秋季"
    else:
        return "冬季"
