"""城市坐标数据库 — 中文城市名 → (纬度, 经度, 英文名)

数据覆盖:
  - 30 个中国境内热门旅游城市
  - 15 个国际城市 (日韩/东南亚/欧美/中东)
  - 支持别名模糊匹配

Open-Meteo API 需要经纬度坐标，这里提供完整的映射表。
"""

from __future__ import annotations

from typing import NamedTuple


class CityCoord(NamedTuple):
    lat: float
    lon: float
    name_en: str  # 英文名


# 中国城市 (30个热门旅游目的地)
CHINA_CITIES: dict[str, CityCoord] = {
    "北京": CityCoord(39.9042, 116.4074, "Beijing"),
    "上海": CityCoord(31.2304, 121.4737, "Shanghai"),
    "西安": CityCoord(34.3416, 108.9398, "Xi'an"),
    "成都": CityCoord(30.5728, 104.0668, "Chengdu"),
    "桂林": CityCoord(25.2736, 110.2900, "Guilin"),
    "广州": CityCoord(23.1291, 113.2644, "Guangzhou"),
    "深圳": CityCoord(22.5431, 114.0579, "Shenzhen"),
    "杭州": CityCoord(30.2741, 120.1551, "Hangzhou"),
    "苏州": CityCoord(31.2990, 120.5853, "Suzhou"),
    "南京": CityCoord(32.0603, 118.7969, "Nanjing"),
    "重庆": CityCoord(29.5630, 106.5516, "Chongqing"),
    "昆明": CityCoord(25.0389, 102.7183, "Kunming"),
    "丽江": CityCoord(26.8721, 100.2299, "Lijiang"),
    "大理": CityCoord(25.5894, 100.2256, "Dali"),
    "拉萨": CityCoord(29.6500, 91.1000, "Lhasa"),
    "厦门": CityCoord(24.4798, 118.0894, "Xiamen"),
    "三亚": CityCoord(18.2528, 109.5120, "Sanya"),
    "哈尔滨": CityCoord(45.8038, 126.5350, "Harbin"),
    "张家界": CityCoord(29.1170, 110.4784, "Zhangjiajie"),
    "黄山": CityCoord(30.1344, 118.1673, "Huangshan"),
    "武汉": CityCoord(30.5928, 114.3055, "Wuhan"),
    "天津": CityCoord(39.3434, 117.3616, "Tianjin"),
    "青岛": CityCoord(36.0671, 120.3826, "Qingdao"),
    "大连": CityCoord(38.9140, 121.6147, "Dalian"),
    "长沙": CityCoord(28.2282, 112.9388, "Changsha"),
    "郑州": CityCoord(34.7466, 113.6254, "Zhengzhou"),
    "洛阳": CityCoord(34.6197, 112.4539, "Luoyang"),
    "贵阳": CityCoord(26.6470, 106.6302, "Guiyang"),
    "呼和浩特": CityCoord(40.8424, 111.7490, "Hohhot"),
    "乌鲁木齐": CityCoord(43.8256, 87.6168, "Urumqi"),
}

# 国际城市 (15个主要客源国 + 热门目的地)
INTERNATIONAL_CITIES: dict[str, CityCoord] = {
    "东京": CityCoord(35.6762, 139.6503, "Tokyo"),
    "京都": CityCoord(35.0116, 135.7681, "Kyoto"),
    "大阪": CityCoord(34.6937, 135.5023, "Osaka"),
    "首尔": CityCoord(37.5665, 126.9780, "Seoul"),
    "济州": CityCoord(33.4996, 126.5312, "Jeju"),
    "曼谷": CityCoord(13.7563, 100.5018, "Bangkok"),
    "清迈": CityCoord(18.7883, 98.9853, "Chiang Mai"),
    "普吉": CityCoord(7.8804, 98.3923, "Phuket"),
    "新加坡": CityCoord(1.3521, 103.8198, "Singapore"),
    "吉隆坡": CityCoord(3.1390, 101.6869, "Kuala Lumpur"),
    "巴厘岛": CityCoord(-8.3405, 115.0920, "Bali"),
    "伦敦": CityCoord(51.5074, -0.1278, "London"),
    "巴黎": CityCoord(48.8566, 2.3522, "Paris"),
    "纽约": CityCoord(40.7128, -74.0060, "New York"),
    "迪拜": CityCoord(25.2048, 55.2708, "Dubai"),
}

# 中国城市别名 (支持简称、拼音、英文名)
CITY_ALIASES: dict[str, str] = {
    # 北京别名
    "beijing": "北京", "bj": "北京", "北平": "北京",
    # 上海
    "shanghai": "上海", "sh": "上海", "魔都": "上海",
    # 西安
    "xian": "西安", "xi'an": "西安",
    # 成都
    "chengdu": "成都", "cd": "成都",
    # 桂林
    "guilin": "桂林", "gl": "桂林", "阳朔": "桂林",
    # 广州
    "guangzhou": "广州", "gz": "广州",
    # 深圳
    "shenzhen": "深圳", "sz": "深圳",
    # 杭州
    "hangzhou": "杭州", "hz": "杭州",
    # 南京
    "nanjing": "南京", "nj": "南京",
    # 重庆
    "chongqing": "重庆", "cq": "重庆",
    # 昆明
    "kunming": "昆明", "km": "昆明",
    # 丽江
    "lijiang": "丽江", "lj": "丽江",
    # 拉萨
    "lasa": "拉萨", "lhasa": "拉萨",
    # 厦门
    "xiamen": "厦门", "xm": "厦门",
    # 三亚
    "sanya": "三亚", "sy": "三亚",
    # 哈尔滨
    "haerbin": "哈尔滨", "harbin": "哈尔滨", "hrb": "哈尔滨",
    # 张家界
    "zhangjiajie": "张家界", "zjj": "张家界",
    # 黄山
    "huangshan": "黄山", "hs": "黄山",
    # 武汉
    "wuhan": "武汉", "wh": "武汉",
    # 天津
    "tianjin": "天津", "tj": "天津",
    # 青岛
    "qingdao": "青岛", "qd": "青岛",
    # 大理
    "dali": "大理", "dl": "大理",
    # 洛阳
    "luoyang": "洛阳", "ly": "洛阳",
}

# 合并全部城市
ALL_CITIES: dict[str, CityCoord] = {**CHINA_CITIES, **INTERNATIONAL_CITIES}


def get_coords(city: str) -> CityCoord | None:
    """根据城市名获取经纬度

    Args:
        city: 城市名 (中文名、拼音、英文名、简称)

    Returns:
        CityCoord(lat, lon, name_en) 或 None

    Example:
        >>> get_coords("北京")
        CityCoord(39.9042, 116.4074, "Beijing")
        >>> get_coords("bj")
        CityCoord(39.9042, 116.4074, "Beijing")
        >>> get_coords("tokyo")
        CityCoord(35.6762, 139.6503, "Tokyo")
    """
    if not city:
        return None

    key = city.strip()

    # 精确匹配中文名
    if key in ALL_CITIES:
        return ALL_CITIES[key]

    # 别名匹配 (大小写不敏感)
    lower = key.lower()
    if lower in CITY_ALIASES:
        resolved = CITY_ALIASES[lower]
        return ALL_CITIES.get(resolved)

    # 模糊匹配: 英文名大小写不敏感
    for cname, coord in ALL_CITIES.items():
        if coord.name_en.lower() == lower:
            return coord

    # 模糊匹配: 包含关系
    for cname, coord in ALL_CITIES.items():
        if key in cname or cname in key:
            return coord

    return None


def search_city(query: str, limit: int = 10) -> list[dict]:
    """模糊搜索城市

    Args:
        query: 搜索词
        limit: 返回数量上限

    Returns:
        [{"name": "北京", "lat": 39.9, "lon": 116.4, "name_en": "Beijing"}, ...]
    """
    results = []
    q = query.strip().lower()

    for cname, coord in ALL_CITIES.items():
        if q in cname.lower() or q in coord.name_en.lower():
            results.append({
                "name": cname,
                "lat": coord.lat,
                "lon": coord.lon,
                "name_en": coord.name_en,
            })
            if len(results) >= limit:
                break

    return results


def get_all_city_names() -> list[str]:
    """返回所有支持的城市名列表"""
    return list(ALL_CITIES.keys())
