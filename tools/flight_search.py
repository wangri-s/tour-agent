"""机票实时查询工具 — Amadeus API (免费) + 参考价降级

用法:
    # 查国际机票
    result = await search_flight_price.ainvoke({
        "origin": "纽约",
        "destination": "北京",
        "departure_date": "2026-10-15",
    })

    # 查往返
    result = await search_flight_price.ainvoke({
        "origin": "伦敦",
        "destination": "上海",
        "departure_date": "2026-10-01",
        "return_date": "2026-10-15",
    })

数据源:
  - 优先: Amadeus Self-Service API (免费, 需注册)
    注册: https://developers.amadeus.com/
    配置: .env 中设置 AMADEUS_API_KEY + AMADEUS_API_SECRET
  - 降级: 12条主要航线参考均价 (离线可用)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_flight_price(
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
    adults: int = 1,
) -> str:
    """查询国际机票实时价格。

    支持全球主要城市往返中国。用于生成行程报价时获取真实机票价格。

    Args:
        origin: 出发城市 (中文名如"纽约"、"伦敦"、或IATA代码如"JFK")
        destination: 到达城市 (中文名如"北京"、"上海"、或IATA代码如"PEK")
        departure_date: 出发日期 YYYY-MM-DD (缺省默认30天后)
        return_date: 返程日期 YYYY-MM-DD (单程不填)
        adults: 成人人数 (默认1)

    Returns:
        JSON 格式航班价格信息:
        {flights: [{price, airline, departure, arrival, stops}, ...], source: "Amadeus"|"参考数据"}
    """
    try:
        from mcp_servers.flight import get_flight_price

        result = await get_flight_price(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
        )

        # 格式化输出
        output = {
            "query": f"{origin} → {destination}",
            "date": departure_date or "30天后",
            "adults": adults,
        }

        if "error" in result:
            output["status"] = "error"
            output["error"] = result.get("error", "")
            output["help"] = result.get("help", "")
            output["register_url"] = result.get("register_url", "")
            if "fallback" in result:
                output["fallback"] = result["fallback"]
        else:
            output["status"] = "ok"
            output["source"] = result.get("source", "Amadeus")
            output["flights"] = result.get("flights", [])

        return json.dumps(output, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"[FlightSearch] 查询失败: {e}")
        return json.dumps({
            "status": "error",
            "error": str(e)[:200],
            "fallback": {"note": "建议按人均 ¥4,000-6,000 估算国际机票"}
        }, ensure_ascii=False)
