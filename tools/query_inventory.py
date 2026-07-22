"""酒店 / 门票 / 车辆库存查询工具 —— 基于知识库的真实数据"""

from langchain_core.tools import tool

# ---- 酒店数据库 (按城市 + 档次) ----
_HOTELS = {
    "北京": {
        "奢华": [
            {"name": "王府井文华东方酒店", "stars": 5, "price": 2800, "location": "王府井", "feature": "俯瞰故宫"},
            {"name": "北京宝格丽酒店", "stars": 5, "price": 3800, "location": "亮马桥", "feature": "意式奢华"},
            {"name": "颐和安缦", "stars": 5, "price": 4500, "location": "颐和园旁", "feature": "皇家园林私享"},
        ],
        "舒适": [
            {"name": "北京三里屯洲际酒店", "stars": 5, "price": 1400, "location": "三里屯", "feature": "夜生活便利"},
            {"name": "北京国贸大酒店", "stars": 5, "price": 1600, "location": "国贸CBD", "feature": "云端夜景"},
            {"name": "北京王府井希尔顿", "stars": 5, "price": 1200, "location": "王府井", "feature": "步行到故宫"},
        ],
        "经济": [
            {"name": "全季酒店(王府井店)", "stars": 3, "price": 450, "location": "王府井", "feature": "性价比高"},
            {"name": "如家精选(前门店)", "stars": 3, "price": 350, "location": "前门", "feature": "近天安门"},
            {"name": "汉庭酒店(西单店)", "stars": 3, "price": 300, "location": "西单", "feature": "交通便利"},
        ],
    },
    "上海": {
        "奢华": [
            {"name": "上海外滩华尔道夫酒店", "stars": 5, "price": 2500, "location": "外滩", "feature": "百年建筑"},
            {"name": "上海和平饭店", "stars": 5, "price": 2800, "location": "外滩", "feature": "传奇地标"},
            {"name": "上海宝格丽酒店", "stars": 5, "price": 3500, "location": "苏河湾", "feature": "当代奢华"},
        ],
        "舒适": [
            {"name": "上海外滩茂悦大酒店", "stars": 5, "price": 1400, "location": "外滩", "feature": "江景房"},
            {"name": "上海静安香格里拉", "stars": 5, "price": 1500, "location": "静安寺", "feature": "市中心"},
            {"name": "上海浦东丽思卡尔顿", "stars": 5, "price": 1800, "location": "陆家嘴", "feature": "浦江夜景"},
        ],
        "经济": [
            {"name": "全季酒店(外滩店)", "stars": 3, "price": 550, "location": "外滩附近", "feature": "步行到外滩"},
            {"name": "汉庭酒店(南京路店)", "stars": 3, "price": 350, "location": "南京路", "feature": "购物便利"},
        ],
    },
    "西安": {
        "奢华": [
            {"name": "西安索菲特传奇酒店", "stars": 5, "price": 2200, "location": "市中心", "feature": "历史建筑改造"},
            {"name": "西安W酒店", "stars": 5, "price": 1800, "location": "曲江", "feature": "现代设计"},
        ],
        "舒适": [
            {"name": "西安城墙希尔顿花园", "stars": 4, "price": 800, "location": "城墙边", "feature": "城墙景观"},
            {"name": "西安大唐不夜城亚朵", "stars": 4, "price": 550, "location": "大唐不夜城", "feature": "夜景绝佳"},
        ],
        "经济": [
            {"name": "全季酒店(钟楼店)", "stars": 3, "price": 350, "location": "钟楼", "feature": "市中心"},
            {"name": "西安七贤国际青年旅舍", "stars": 2, "price": 80, "location": "城墙内", "feature": "四合院风格"},
        ],
    },
    "成都": {
        "奢华": [
            {"name": "成都太古里博舍", "stars": 5, "price": 2200, "location": "太古里", "feature": "设计感强"},
            {"name": "成都尼依格罗酒店", "stars": 5, "price": 1500, "location": "IFS", "feature": "熊猫雕塑景观"},
        ],
        "舒适": [
            {"name": "成都春熙路希尔顿", "stars": 4, "price": 800, "location": "春熙路", "feature": "市中心核心"},
            {"name": "成都宽窄巷子亚朵", "stars": 4, "price": 550, "location": "宽窄巷子", "feature": "步行景区"},
        ],
        "经济": [
            {"name": "全季酒店(春熙路店)", "stars": 3, "price": 350, "location": "春熙路", "feature": "性价比高"},
            {"name": "成都驴友记青年旅舍", "stars": 2, "price": 60, "location": "市中心", "feature": "社交氛围好"},
        ],
    },
    "桂林": {
        "奢华": [
            {"name": "阳朔糖舍度假酒店", "stars": 5, "price": 2200, "location": "阳朔", "feature": "老糖厂改造,山景泳池"},
            {"name": "桂林香格里拉大酒店", "stars": 5, "price": 1200, "location": "桂林市区", "feature": "漓江畔"},
        ],
        "舒适": [
            {"name": "阳朔十里画廊民宿", "stars": 4, "price": 600, "location": "十里画廊", "feature": "田园山景"},
            {"name": "阳朔悦榕庄", "stars": 5, "price": 1800, "location": "阳朔", "feature": "漓江畔奢华"},
        ],
        "经济": [
            {"name": "阳朔西街客栈", "stars": 3, "price": 280, "location": "西街", "feature": "夜生活便利"},
            {"name": "桂林正阳驿站", "stars": 3, "price": 200, "location": "正阳步行街", "feature": "市中心"},
        ],
    },
    "丽江": {
        "奢华": [
            {"name": "丽江大研安缦", "stars": 5, "price": 4500, "location": "大研古城", "feature": "纳西院落"},
            {"name": "丽江悦榕庄", "stars": 5, "price": 2500, "location": "束河", "feature": "雪山景观"},
        ],
        "舒适": [
            {"name": "丽江古城英迪格", "stars": 4, "price": 900, "location": "大研古城", "feature": "茶马古道主题"},
            {"name": "丽江束河無白酒店", "stars": 4, "price": 700, "location": "束河古镇", "feature": "静谧庭院"},
        ],
        "经济": [
            {"name": "丽江古城客栈", "stars": 3, "price": 350, "location": "大研古城", "feature": "纳西风情"},
            {"name": "丽江背包十年青年旅舍", "stars": 2, "price": 50, "location": "古城边", "feature": "背包客首选"},
        ],
    },
}

# ---- 门票数据库 ----
_TICKETS = {
    "北京": [
        {"name": "故宫博物院", "price": 60, "tips": "提前7天预约，周一闭馆，旺季(4-10月)¥60/淡季¥40"},
        {"name": "八达岭长城", "price": 45, "tips": "建议早8点前到避开人流，可乘缆车¥140往返"},
        {"name": "天坛公园", "price": 15, "tips": "旺季¥15/淡季¥10，建议上午去光线好"},
        {"name": "颐和园", "price": 30, "tips": "旺季¥30/淡季¥20，园中园另收费"},
        {"name": "国家博物馆", "price": 0, "tips": "免费需提前3天预约，周一闭馆"},
    ],
    "上海": [
        {"name": "东方明珠塔", "price": 199, "tips": "含全透明悬空观光廊，夜景更佳"},
        {"name": "上海中心大厦", "price": 180, "tips": "中国第一高楼，118层观光厅"},
        {"name": "上海迪士尼乐园", "price": 475, "tips": "平日¥475/高峰¥599，需提前预约入园日期"},
        {"name": "豫园", "price": 40, "tips": "江南园林精华，周一闭馆"},
    ],
    "西安": [
        {"name": "秦始皇兵马俑", "price": 120, "tips": "世界第八大奇迹，建议请讲解员¥200/团"},
        {"name": "西安城墙", "price": 54, "tips": "可租自行车¥45环城墙骑行(13.7km)"},
        {"name": "华清宫", "price": 120, "tips": "含骊山，晚上有《长恨歌》演出¥298起"},
        {"name": "陕西历史博物馆", "price": 0, "tips": "免费需提前14天预约！周一闭馆"},
        {"name": "大雁塔", "price": 50, "tips": "登塔另付，大慈恩寺门票¥50"},
    ],
    "成都": [
        {"name": "大熊猫繁育研究基地", "price": 55, "tips": "建议早8点前到看活跃熊猫，上午10点后熊猫睡觉"},
        {"name": "都江堰", "price": 80, "tips": "世界水利工程奇迹，距成都1h车程"},
        {"name": "青城山", "price": 90, "tips": "前山¥90(道教文化)/后山¥20(自然风光)"},
        {"name": "武侯祠", "price": 50, "tips": "三国文化圣地"},
    ],
    "桂林": [
        {"name": "漓江竹筏(杨堤-兴坪)", "price": 215, "tips": "精华段，含九马画山、黄布倒影(20元人民币背景)"},
        {"name": "象鼻山", "price": 55, "tips": "桂林城徽，建议傍晚去光线最美"},
        {"name": "龙脊梯田", "price": 80, "tips": "距桂林2.5h车程，建议住一晚看日出"},
        {"name": "遇龙河漂流", "price": 200, "tips": "人工竹筏，比漓江更安静惬意"},
        {"name": "印象刘三姐", "price": 198, "tips": "张艺谋导演山水实景演出，晚上8点"},
    ],
    "丽江": [
        {"name": "玉龙雪山", "price": 100, "tips": "门票¥100+大索道¥180+环保车¥20，需提前抢索道票"},
        {"name": "束河古镇", "price": 40, "tips": "比大研古城更安静，适合发呆"},
        {"name": "泸沽湖", "price": 100, "tips": "距丽江4h车程，建议2天行程"},
    ],
    "杭州": [
        {"name": "西湖", "price": 0, "tips": "全天免费，建议骑行或步行环湖，雷峰塔¥40"},
        {"name": "灵隐寺", "price": 75, "tips": "含飞来峰¥45+灵隐寺香花券¥30"},
        {"name": "西溪湿地", "price": 80, "tips": "非诚勿扰取景地，建议坐摇橹船"},
    ],
}

# ---- 车辆数据库 ----
_VEHICLES = [
    {"type": "5座轿车", "brand": "丰田凯美瑞/大众帕萨特", "price_per_day": 500, "capacity": "3人+2行李", "suitable": "情侣/单人"},
    {"type": "7座商务车", "brand": "别克GL8", "price_per_day": 800, "capacity": "5人+4行李", "suitable": "家庭/小团"},
    {"type": "14座中巴", "brand": "丰田考斯特", "price_per_day": 1200, "capacity": "10人+8行李", "suitable": "中型团"},
    {"type": "33座大巴", "brand": "金龙/宇通", "price_per_day": 1800, "capacity": "28人+行李", "suitable": "大型团"},
]


@tool
async def query_inventory(city: str, date: str, pax: int, budget_level: str = "舒适") -> str:
    """查询目的地可预订资源。

    返回指定城市的酒店(按预算档次)、热门景点门票和车辆租赁信息。

    Args:
        city: 城市名 (中文：北京/上海/西安/成都/桂林/丽江/杭州...)
        date: 日期 (YYYY-MM-DD)
        pax: 出行人数
        budget_level: 预算档次 (经济/舒适/奢华)

    Returns:
        JSON: {"hotels": [...], "tickets": [...], "vehicles": [...], "pax": int}
    """
    import json

    # 酒店
    city_hotels = _HOTELS.get(city, {}).get(budget_level)
    if not city_hotels:
        # fallback: 找任意档次的
        for level in ["舒适", "经济", "奢华"]:
            city_hotels = _HOTELS.get(city, {}).get(level)
            if city_hotels:
                break
        if not city_hotels:
            city_hotels = [
                {"name": f"{city}中心酒店", "stars": 4, "price": 500, "location": "市中心", "feature": "推荐"},
            ]

    # 门票
    tickets = _TICKETS.get(city, [
        {"name": f"{city}热门景点", "price": 100, "tips": "请参考当地旅游信息"},
    ])

    # 车辆
    vehicles = []
    for v in _VEHICLES:
        if pax <= 3 and v["type"] == "5座轿车":
            vehicles.append(v)
        elif pax <= 5 and v["type"] == "7座商务车":
            vehicles.append(v)
        elif pax <= 10 and v["type"] == "14座中巴":
            vehicles.append(v)
        elif pax <= 28 and v["type"] == "33座大巴":
            vehicles.append(v)
    if not vehicles:
        vehicles.append(_VEHICLES[-1])  # 大巴兜底

    # 计算人均预算参考
    avg_hotel = sum(h["price"] for h in city_hotels[:2]) / min(2, len(city_hotels))
    avg_ticket = sum(t["price"] for t in tickets[:3]) / min(3, len(tickets))

    return json.dumps({
        "city": city,
        "date": date,
        "pax": pax,
        "budget_level": budget_level,
        "hotels": city_hotels,
        "tickets": tickets,
        "vehicles": vehicles,
        "summary": {
            "avg_hotel_per_night": round(avg_hotel),
            "avg_ticket_per_attraction": round(avg_ticket),
            "vehicle_recommended": vehicles[0]["type"],
            "vehicle_price_per_day": vehicles[0]["price_per_day"],
        },
    }, ensure_ascii=False, indent=2)
