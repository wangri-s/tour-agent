"""飞常准 VariFlight MCP 接入 — 国内机票实时价格查询

免费额度: 100次/Key
注册: https://mcp.variflight.com
配置: .env 中设置 VARIFLIGHT_API_KEY

通过 Python MCP 客户端连接飞常准 Node.js MCP Server:
  npx @variflight-ai/variflight-mcp

工具:
  - searchFlightItineraries: 搜索航班+最低票价 (中国大陆)
  - getFlightPriceByCities: 两城市间航班价格 (含舱位价)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_variflight_key() -> str:
    """获取飞常准 API Key"""
    return os.getenv("VARIFLIGHT_API_KEY", "") or os.getenv("X_VARIFLIGHT_KEY", "")


async def _call_variflight_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """通过 MCP 协议调用飞常准工具

    启动飞常准 MCP Server (Node.js 进程)，通过 stdio 通信。
    """
    api_key = _get_variflight_key()
    if not api_key:
        return {"error": "VARIFLIGHT_API_KEY 未配置", "help": "请在 https://mcp.variflight.com 注册获取"}

    try:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@variflight-ai/variflight-mcp"],
            env={"VARIFLIGHT_API_KEY": api_key},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(tool_name, params)

                # 解析 MCP 返回
                if hasattr(result, 'content') and result.content:
                    text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"raw": text, "source": "VariFlight MCP"}

                return {"error": "MCP 返回为空", "source": "VariFlight"}

    except ImportError:
        return {"error": "mcp Python 包未安装", "help": "pip install mcp"}
    except Exception as e:
        error_msg = str(e)[:300]
        logger.warning(f"[VariFlight] MCP 调用失败: {error_msg}")

        # 额度用完等常见错误
        if "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
            return {"error": "免费额度已用完 (100次/Key)", "source": "VariFlight"}
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            return {"error": "API Key 无效", "help": "请检查 VARIFLIGHT_API_KEY 是否正确"}
        return {"error": f"MCP 调用失败: {error_msg}", "source": "VariFlight"}


async def search_flights_variflight(
    origin: str,
    destination: str,
    departure_date: str,
) -> dict[str, Any]:
    """飞常准机票搜索 — MCP searchFlightItineraries

    Args:
        origin: 出发城市 IATA 代码 (如 BJS=北京, SHA=上海)
        destination: 到达城市 IATA 代码
        departure_date: 出发日期 YYYY-MM-DD

    Returns:
        {
            "flights": [{price, airline, flight_no, departure, arrival, duration, stops}],
            "source": "VariFlight (实时)",
        }
    """
    api_key = _get_variflight_key()
    if not api_key:
        return {"error": "VARIFLIGHT_API_KEY 未配置"}

    # 转换城市名 → IATA 代码 (如果传的是中文)
    origin_code = _resolve_city_code(origin)
    dest_code = _resolve_city_code(destination)

    logger.info(f"[VariFlight] 查询: {origin_code} → {dest_code} {departure_date}")

    result = await _call_variflight_tool("searchFlightItineraries", {
        "depCityCode": origin_code,
        "arrCityCode": dest_code,
        "depDate": departure_date,
    })

    if "error" in result:
        return result

    # 解析航班列表
    flights = _parse_flight_results(result)
    return {
        "flights": flights,
        "search_info": {
            "origin": origin_code,
            "destination": dest_code,
            "date": departure_date,
        },
        "source": "VariFlight (实时)",
    }


# 中国城市 → IATA 代码映射 (飞常准用三字码)
_CITY_TO_IATA: dict[str, str] = {
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "重庆": "CKG", "西安": "XIY", "昆明": "KMG",
    "杭州": "HGH", "南京": "NKG", "武汉": "WUH", "长沙": "CSX",
    "厦门": "XMN", "青岛": "TAO", "大连": "DLC", "沈阳": "SHE",
    "哈尔滨": "HRB", "三亚": "SYX", "海口": "HAK", "桂林": "KWL",
    "拉萨": "LXA", "乌鲁木齐": "URC", "郑州": "CGO", "天津": "TSN",
    "福州": "FOC", "南宁": "NNG", "贵阳": "KWE", "兰州": "LHW",
    "银川": "INC", "西宁": "XNN", "呼和浩特": "HET", "太原": "TYN",
    "石家庄": "SJW", "合肥": "HFE", "南昌": "KHN", "济南": "TNA",
}


def _resolve_city_code(city: str) -> str:
    """城市名 → IATA 三字码"""
    if len(city) == 3 and city.isalpha() and city == city.upper():
        return city  # 已经是 IATA 码
    return _CITY_TO_IATA.get(city, city.upper()[:3])


def _parse_flight_results(raw: dict | str) -> list[dict]:
    """解析飞常准返回的航班数据"""
    data = raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return []

    flights = []

    # 尝试多种可能的响应格式
    items = (
        data.get("data", []) or
        data.get("flights", []) or
        data.get("itineraries", []) or
        data.get("results", []) or
        []
    )

    # 如果是单个结果对象
    if isinstance(data, dict) and not items:
        # 可能直接返回了最低/推荐航班
        for key in ["lowestPriceFlight", "shortestDurationFlight", "recommendedFlight"]:
            if key in data and data[key]:
                items.append(data[key])

    for item in items:
        flight = {
            "price": (
                item.get("price") or
                item.get("totalPrice") or
                item.get("fare") or
                item.get("lowestPrice") or 0
            ),
            "currency": item.get("currency", "CNY"),
            "airline": item.get("airline", item.get("carrier", "")),
            "flight_no": item.get("flightNo", item.get("flightNumber", "")),
            "departure": item.get("depTime", item.get("departureTime", "")),
            "arrival": item.get("arrTime", item.get("arrivalTime", "")),
            "duration": item.get("duration", ""),
            "stops": item.get("stops", item.get("transferCount", 0)),
            "aircraft": item.get("aircraft", item.get("planeType", "")),
            "cabin": item.get("cabin", item.get("cabinClass", "")),
        }
        if flight["price"] > 0:
            flights.append(flight)

    flights.sort(key=lambda x: x["price"])
    return flights
