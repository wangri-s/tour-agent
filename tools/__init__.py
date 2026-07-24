from tools.search_faq import search_faq
from tools.rag_search import rag_search
from tools.weather_api import get_real_weather  # 旧版 (和风, 已弃用)
from tools.check_handoff import check_handoff
from tools.get_weather import get_weather        # 静态气候库 (降级备用)
from tools.mcp_weather import mcp_get_weather, mcp_search_city  # MCP Open-Meteo (推荐)
from tools.query_calendar import query_calendar
from tools.query_inventory import query_inventory
from tools.quote_price import quote_price
from tools.update_crm import update_crm
from tools.send_capi import send_capi

__all__ = [
    "search_faq",
    "rag_search",
    "check_handoff",
    "get_weather",
    "get_real_weather",     # 旧版 (兼容)
    "mcp_get_weather",      # MCP Open-Meteo (推荐)
    "mcp_search_city",      # 城市模糊搜索
    "query_calendar",
    "query_inventory",
    "quote_price",
    "update_crm",
    "send_capi",
]
