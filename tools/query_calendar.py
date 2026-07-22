"""节假日 / 周末判断工具 —— 含 2026 年中国节假日数据"""

from langchain_core.tools import tool

# 2026 年中国法定节假日
_HOLIDAYS_2026 = {
    # 元旦
    "2026-01-01": "元旦", "2026-01-02": "元旦假期", "2026-01-03": "元旦假期",
    # 春节 (2月17日除夕)
    "2026-02-15": "春节前夕", "2026-02-16": "除夕前夕",
    "2026-02-17": "除夕", "2026-02-18": "春节(初一)", "2026-02-19": "春节(初二)",
    "2026-02-20": "春节(初三)", "2026-02-21": "春节假期", "2026-02-22": "春节假期",
    "2026-02-23": "春节假期最后一天",
    # 清明节
    "2026-04-05": "清明节", "2026-04-06": "清明假期", "2026-04-07": "清明假期",
    # 劳动节
    "2026-05-01": "劳动节", "2026-05-02": "劳动节假期", "2026-05-03": "劳动节假期",
    "2026-05-04": "劳动节假期", "2026-05-05": "劳动节假期最后一天",
    # 端午节
    "2026-05-31": "端午节假期", "2026-06-01": "端午节假期", "2026-06-02": "端午节",
    # 中秋节+国庆节 (可能连休)
    "2026-09-29": "中秋节", "2026-09-30": "中秋假期",
    "2026-10-01": "国庆节", "2026-10-02": "国庆假期", "2026-10-03": "国庆假期",
    "2026-10-04": "国庆假期", "2026-10-05": "国庆假期", "2026-10-06": "国庆假期",
    "2026-10-07": "国庆假期最后一天",
}

# 拥挤度评级
_CROWD_LEVELS = {
    "春节": "极度拥挤 ⚠️⚠️⚠️ 酒店价格翻3-5倍，大部分商店关门",
    "国庆": "极度拥挤 ⚠️⚠️⚠️ 全国景点爆满，酒店价格翻3-5倍",
    "劳动节": "非常拥挤 ⚠️⚠️ 酒店价格翻2-3倍",
    "清明": "较拥挤 ⚠️ 短途出行增加",
    "端午": "较拥挤 ⚠️ 短途出行增加",
    "元旦": "中度拥挤 城市周边游增加",
    "中秋": "中度拥挤 与国庆连休时极度拥挤",
}


@tool
async def query_calendar(date: str) -> str:
    """查询指定日期是否为节假日、周末，以及人群拥挤度预测。

    用于行程规划时避开极端拥挤日期，选择最佳出行时间。

    Args:
        date: 日期 (YYYY-MM-DD 格式)

    Returns:
        JSON: {"date": str, "is_holiday": bool, "is_weekend": bool,
               "holiday_name": str, "crowded": bool, "crowd_level": str,
               "travel_advice": str}
    """
    import json
    from datetime import date as dt_date

    try:
        d = dt_date.fromisoformat(date)
    except (ValueError, TypeError):
        from datetime import date as today_date
        d = today_date.today()

    is_weekend = d.weekday() >= 5  # 周六=5, 周日=6
    date_str = d.strftime("%Y-%m-%d")

    # 查节假日
    holiday_name = _HOLIDAYS_2026.get(date_str, "")
    is_holiday = bool(holiday_name)

    # 拥挤度
    crowded = is_holiday or is_weekend
    crowd_level = ""
    travel_advice = ""

    if is_holiday:
        for keyword, level in _CROWD_LEVELS.items():
            if keyword in holiday_name:
                crowd_level = level
                break
        if not crowd_level:
            crowd_level = "节假日出行，景区人较多"
        travel_advice = f"⚠️ {holiday_name}期间{crowd_level}。"
        if "极度" in crowd_level or "非常" in crowd_level:
            travel_advice += " 强烈建议避开此日期！如必须出行，务必提前预订所有酒店和门票。"
    elif is_weekend:
        crowd_level = "周末，热门景点人多但可控"
        travel_advice = "周末出行，建议热门景点尽早出发(8点前)，避开10-15点人流高峰。"
    else:
        crowd_level = "工作日，游客较少"
        travel_advice = "✅ 工作日出行，景区人少体验佳，是理想的选择！"

    # 附近有节假日？(前后7天)
    nearby_holiday = ""
    for offset in range(-7, 8):
        if offset == 0:
            continue
        nd = d.fromordinal(d.toordinal() + offset)
        nd_str = nd.strftime("%Y-%m-%d")
        if nd_str in _HOLIDAYS_2026 and "前夕" not in _HOLIDAYS_2026[nd_str]:
            nearby_holiday = f"{offset}天后是{_HOLIDAYS_2026[nd_str]}" if offset > 0 else f"{-offset}天前是{_HOLIDAYS_2026[nd_str]}"
            break

    result = {
        "date": date_str,
        "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()],
        "is_holiday": is_holiday,
        "is_weekend": is_weekend,
        "holiday_name": holiday_name,
        "crowded": crowded,
        "crowd_level": crowd_level,
        "travel_advice": travel_advice,
        "nearby_holiday": nearby_holiday,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
