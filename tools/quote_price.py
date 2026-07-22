"""报价计算工具 —— 基于 draft 与 need 生成报价单"""

from langchain_core.tools import tool


@tool
async def quote_price(
    destination: str,
    days: int,
    pax: int,
    budget_per_person: float,
    itinerary_json: str = "",
) -> str:
    """生成报价单

    Args:
        destination: 目的地
        days: 行程天数
        pax: 人数
        budget_per_person: 人均预算
        itinerary_json: 行程 JSON（可选）

    Returns:
        JSON: {"flights": float, "hotels": float, "transport": float,
                "tickets": float, "meals": float, "guide": float, "total": float, "notes": str}
    """
    import json

    # 简易报价逻辑 (TODO: 接真实报价系统)
    hotel_per_night = 400 if budget_per_person < 3000 else 800 if budget_per_person < 8000 else 1500
    daily_meals = 150 if budget_per_person < 3000 else 300 if budget_per_person < 8000 else 600
    transport_daily = 200
    tickets_daily = 200
    guide_daily = 500 if budget_per_person >= 3000 else 300

    quote = {
        "flights": 2500,                        # 单程国际段估算
        "hotels": hotel_per_night * days,
        "transport": transport_daily * days,
        "tickets": tickets_daily * days,
        "meals": daily_meals * days,
        "guide": guide_daily * days,
        "notes": f"基于{destination}{days}日游{pax}人团报价，人均预算¥{budget_per_person}，价格随实际选择浮动",
    }
    quote["total"] = sum([
        quote["flights"], quote["hotels"], quote["transport"],
        quote["tickets"], quote["meals"], quote["guide"],
    ])

    return json.dumps(quote, ensure_ascii=False)
