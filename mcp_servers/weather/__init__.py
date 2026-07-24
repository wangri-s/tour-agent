"""Weather MCP Server — 基于 Open-Meteo 免费天气 API

提供:
  - get_current_weather: 实时天气
  - get_forecast_7days: 7天预报
  - get_trip_weather: 行程天气 (日期范围)

数据源: Open-Meteo (免费, 无 API Key, 全球覆盖)
"""

from .server import mcp, start_server, stop_server
from .open_meteo import fetch_weather, get_weather_for_city
from .city_coords import get_coords, search_city

__all__ = ["mcp", "start_server", "stop_server", "fetch_weather", "get_weather_for_city", "get_coords", "search_city"]
