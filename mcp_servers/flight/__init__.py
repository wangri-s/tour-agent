"""Amadeus Self-Service API — 国际机票实时查询

完全免费 (test environment):
  - 注册: https://developers.amadeus.com/
  - 免费额度: 2,000 calls/month (test), 无限制 (production 需审核)
  - 覆盖: 全球400+航司, 实时价格

API 流程:
  1. POST /v1/security/oauth2/token → access_token (30min有效)
  2. GET /v2/shopping/flight-offers → 搜索航班

文档: https://developers.amadeus.com/self-service/category/flights
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Amadeus API 端点
AMADEUS_AUTH_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_FLIGHT_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
AMADEUS_AIRPORT_URL = "https://test.api.amadeus.com/v1/reference-data/locations"

# Token 缓存 (30分钟有效)
_token_cache: dict[str, Any] = {}

# 主要国际机场 IATA 代码 — 飞中国航线常用
AIRPORT_IATA: dict[str, str] = {
    # 中国主要口岸机场
    "北京": "PEK", "北京大兴": "PKX", "上海": "PVG", "上海虹桥": "SHA",
    "广州": "CAN", "深圳": "SZX", "成都": "CTU", "成都天府": "TFU",
    "重庆": "CKG", "西安": "XIY", "昆明": "KMG", "杭州": "HGH",
    "厦门": "XMN", "南京": "NKG", "武汉": "WUH", "长沙": "CSX",
    "青岛": "TAO", "大连": "DLC", "哈尔滨": "HRB", "沈阳": "SHE",
    "桂林": "KWL", "三亚": "SYX", "海口": "HAK", "拉萨": "LXA",
    "乌鲁木齐": "URC", "郑州": "CGO", "天津": "TSN", "福州": "FOC",
    # 国际主要出发城市
    "纽约": "JFK", "洛杉矶": "LAX", "旧金山": "SFO", "芝加哥": "ORD",
    "伦敦": "LON", "巴黎": "CDG", "法兰克福": "FRA", "东京": "NRT",
    "首尔": "ICN", "新加坡": "SIN", "曼谷": "BKK", "迪拜": "DXB",
    "悉尼": "SYD", "墨尔本": "MEL", "多伦多": "YYZ", "温哥华": "YVR",
    "莫斯科": "SVO", "米兰": "MXP", "马德里": "MAD", "阿姆斯特丹": "AMS",
}


def get_airport_code(city: str) -> str | None:
    """根据中文城市名获取 IATA 代码"""
    # 精确匹配
    if city in AIRPORT_IATA:
        return AIRPORT_IATA[city]
    # 模糊匹配 (如 "北京" 匹配 "北京大兴")
    for name, code in AIRPORT_IATA.items():
        if city in name or name in city:
            return code
    return None


async def _get_access_token(api_key: str, api_secret: str) -> str | None:
    """获取 Amadeus OAuth2 access token (缓存30分钟)"""
    cache_key = f"{api_key}:{api_secret}"
    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]
        if datetime.now() < token_data["expires_at"]:
            return token_data["token"]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                AMADEUS_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": api_key,
                    "client_secret": api_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

            token = data.get("access_token")
            expires_in = data.get("expires_in", 1800)
            _token_cache[cache_key] = {
                "token": token,
                "expires_at": datetime.now() + timedelta(seconds=expires_in - 60),
            }
            logger.info("[Amadeus] Token 获取成功")
            return token

    except Exception as e:
        logger.error(f"[Amadeus] Token 获取失败: {e}")
        return None


async def search_flights(
    origin: str,              # 出发城市 (中文) 或 IATA代码
    destination: str,          # 到达城市 (中文) 或 IATA代码
    departure_date: str,       # 出发日期 YYYY-MM-DD
    return_date: str = "",     # 返程日期 (可选)
    adults: int = 1,
    max_results: int = 5,
) -> dict[str, Any]:
    """搜索国际机票 — Amadeus Flight Offers Search

    Args:
        origin: 出发城市 (如 "纽约"、"伦敦"、"JFK")
        destination: 到达城市 (如 "北京"、"上海"、"PEK")
        departure_date: 出发日期
        return_date: 返程日期 (单程可不填)
        adults: 成人人数
        max_results: 最大结果数

    Returns:
        {
            "flights": [{price, currency, airline, departure, arrival, duration, stops}, ...],
            "search_info": {origin, destination, date, ...}
        }
    """
    api_key = os.getenv("AMADEUS_API_KEY", "")
    api_secret = os.getenv("AMADEUS_API_SECRET", "")

    if not api_key or not api_secret:
        return {
            "error": "Amadeus API 未配置",
            "help": "请在 https://developers.amadeus.com/ 免费注册，获取 API Key 和 Secret",
            "register_url": "https://developers.amadeus.com/",
            "setup": "将 AMADEUS_API_KEY 和 AMADEUS_API_SECRET 添加到 .env 文件",
        }

    # 解析机场代码
    origin_code = get_airport_code(origin) or origin.upper()
    dest_code = get_airport_code(destination) or destination.upper()

    # 获取 Token
    token = await _get_access_token(api_key, api_secret)
    if not token:
        return {"error": "Amadeus 认证失败", "detail": "请检查 API Key 和 Secret 是否正确"}

    # 构建查询参数
    params: dict[str, Any] = {
        "originLocationCode": origin_code,
        "destinationLocationCode": dest_code,
        "departureDate": departure_date,
        "adults": adults,
        "max": max_results,
        "currencyCode": "CNY",
    }
    if return_date:
        params["returnDate"] = return_date

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                AMADEUS_FLIGHT_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析航班
        flights = []
        for offer in data.get("data", []):
            itinerary = offer.get("itineraries", [{}])[0]
            segments = itinerary.get("segments", [])
            first_seg = segments[0] if segments else {}
            last_seg = segments[-1] if segments else {}

            price_info = offer.get("price", {})
            flights.append({
                "price": float(price_info.get("grandTotal", 0)),
                "currency": price_info.get("currency", "CNY"),
                "airline": first_seg.get("carrierCode", "?"),
                "departure": first_seg.get("departure", {}).get("at", ""),
                "arrival": last_seg.get("arrival", {}).get("at", ""),
                "departure_airport": first_seg.get("departure", {}).get("iataCode", ""),
                "arrival_airport": last_seg.get("arrival", {}).get("iataCode", ""),
                "duration": itinerary.get("duration", ""),
                "stops": len(segments) - 1,
                "segments": len(segments),
                "aircraft": first_seg.get("aircraft", {}).get("code", ""),
            })

        # 排序
        flights.sort(key=lambda x: x["price"])

        logger.info(
            f"[Amadeus] {origin_code}→{dest_code} {departure_date}: "
            f"{len(flights)} 个航班, 最低 ¥{flights[0]['price']:.0f}"
        )

        return {
            "flights": flights,
            "search_info": {
                "origin": origin_code,
                "destination": dest_code,
                "departure_date": departure_date,
                "return_date": return_date or "单程",
                "adults": adults,
                "total_results": len(flights),
            },
            "source": "Amadeus (实时)",
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"[Amadeus] API 错误: {e.response.status_code} - {e.response.text[:200]}")
        return {"error": f"航班查询失败 (HTTP {e.response.status_code})", "detail": str(e)}

    except Exception as e:
        logger.error(f"[Amadeus] 查询失败: {e}")
        return {"error": f"查询失败: {str(e)[:200]}"}


# 常用航线参考价格 (API 不可用时的降级数据)
FALLBACK_FLIGHTS: dict[str, dict] = {
    "JFK-PEK": {"price": 5200, "airline": "CA", "duration": "PT14H", "stops": 0},
    "LAX-PEK": {"price": 4800, "airline": "CA", "duration": "PT13H", "stops": 0},
    "SFO-PVG": {"price": 4500, "airline": "UA", "duration": "PT13H30M", "stops": 0},
    "LON-PEK": {"price": 5500, "airline": "CA", "duration": "PT11H", "stops": 0},
    "CDG-PVG": {"price": 5100, "airline": "AF", "duration": "PT11H30M", "stops": 0},
    "FRA-PEK": {"price": 4900, "airline": "LH", "duration": "PT10H", "stops": 0},
    "NRT-PEK": {"price": 2800, "airline": "CA", "duration": "PT4H", "stops": 0},
    "ICN-PEK": {"price": 1800, "airline": "CA", "duration": "PT2H30M", "stops": 0},
    "SIN-PVG": {"price": 2500, "airline": "SQ", "duration": "PT5H30M", "stops": 0},
    "BKK-PEK": {"price": 2200, "airline": "CA", "duration": "PT5H", "stops": 0},
    "DXB-PEK": {"price": 3800, "airline": "EK", "duration": "PT7H30M", "stops": 0},
    "SYD-PEK": {"price": 5200, "airline": "CA", "duration": "PT12H", "stops": 0},
}


async def get_flight_price(
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
    adults: int = 1,
) -> dict[str, Any]:
    """获取机票价格 — API优先 + 降级参考价

    用于 trip_planner/quote_agent 查询大交通费用。
    """
    # 默认日期: 查最近30天
    if not departure_date:
        departure_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    result = await search_flights(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        max_results=3,
    )

    # API 失败 → 降级
    if "error" in result:
        origin_code = get_airport_code(origin) or origin.upper()
        dest_code = get_airport_code(destination) or destination.upper()
        route_key = f"{origin_code}-{dest_code}"
        fallback = FALLBACK_FLIGHTS.get(route_key)

        if fallback:
            result["fallback"] = {
                "note": "API 不可用，使用航线参考均价",
                "reference_price": fallback["price"],
                "currency": "CNY",
                "airline": fallback["airline"],
                "stops": fallback["stops"],
            }
            result["source"] = "参考数据 (离线)"
        else:
            result["fallback"] = {
                "note": "API 不可用且无该航线参考数据",
                "estimate": "建议按人均 ¥4,000-6,000 估算国际机票",
            }

    return result
