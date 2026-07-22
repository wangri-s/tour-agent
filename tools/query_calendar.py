"""节假日 / 周末判断工具"""

from langchain_core.tools import tool


@tool
async def query_calendar(date: str) -> str:
    """查询指定日期是否为节假日 / 周末

    Args:
        date: 日期 (YYYY-MM-DD)

    Returns:
        JSON: {"date": str, "is_holiday": bool, "is_weekend": bool, "holiday_name": str}
    """
    import json
    from datetime import date as dt_date, timedelta

    # TODO: 接入真实节假日库 (chinese-calendar / 国务院公告)

    try:
        d = dt_date.fromisoformat(date)
        is_weekend = d.weekday() >= 5  # 周六=5, 周日=6
    except (ValueError, TypeError):
        is_weekend = False
        d = dt_date.today()

    # 简易节假日判断（仅含固定日期的大型节假日）
    holiday_map = {
        "01-01": "元旦",
        "05-01": "劳动节",
        "10-01": "国庆节",
    }
    month_day = d.strftime("%m-%d")
    holiday_name = holiday_map.get(month_day, "")

    return json.dumps({
        "date": date,
        "is_holiday": bool(holiday_name),
        "is_weekend": is_weekend,
        "holiday_name": holiday_name,
        "crowded": bool(holiday_name) or is_weekend,
    }, ensure_ascii=False)
