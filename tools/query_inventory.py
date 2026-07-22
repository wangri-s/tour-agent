"""酒店 / 门票 / 车辆库存查询工具 —— 接 PMS 或供应商 API"""

from langchain_core.tools import tool


@tool
async def query_inventory(city: str, date: str, pax: int) -> str:
    """查询目的地可售资源

    Args:
        city: 城市名
        date: 日期 (YYYY-MM-DD)
        pax: 人数

    Returns:
        JSON: {"hotels": [...], "tickets": [...], "vehicles": [...]}
    """
    # TODO: 接入 PMS / 供应商 API
    import json

    return json.dumps({
        "city": city,
        "date": date,
        "hotels": [
            {"name": f"{city}迎宾馆", "stars": 4, "available": True, "price_per_night": 480},
            {"name": f"{city}国际酒店", "stars": 5, "available": True, "price_per_night": 980},
            {"name": f"{city}青年旅舍", "stars": 2, "available": True, "price_per_night": 120},
        ],
        "tickets": [
            {"name": f"{city}故宫/博物馆", "price": 60, "available": True},
            {"name": f"{city}主题乐园", "price": 280, "available": True},
        ],
        "vehicles": [
            {"type": "7座商务车", "price_per_day": 800, "available": True},
            {"type": "14座中巴", "price_per_day": 1200, "available": True},
        ],
    }, ensure_ascii=False)
