"""FAQ 知识库检索工具 —— 接 Milvus / pgvector"""

from langchain_core.tools import tool


@tool
async def search_faq(query: str, top_k: int = 5) -> str:
    """检索 FAQ 知识库

    Args:
        query: 用户问题
        top_k: 返回条数上限

    Returns:
        JSON 格式的相关 FAQ 条目
    """
    # TODO MVP: 内存字典；第二阶段接入向量库
    _mock_faqs = {
        "签证": "中国对54国实行72/144小时过境免签，部分国家享受15天免签政策。具体请参考国家移民管理局最新公告。",
        "退款": "出发前7天以上全额退款，3-7天退50%，3天以内不退。特殊情况请联系客服。",
        "保险": "所有行程均含基础旅行保险，覆盖医疗运送、行程延误、行李丢失。可升级为豪华保险计划。",
        "支付": "支持微信支付、支付宝、Visa、MasterCard、银联。入境游客可使用国际信用卡在线支付。",
        "高铁": "中国高铁网络覆盖主要旅游城市，时速300km/h。建议购买一等座，空间更舒适。",
    }

    results = []
    for key, value in _mock_faqs.items():
        if query.lower() in key.lower() or query.lower() in value.lower()[:20]:
            results.append({"title": key, "content": value})

    if not results:
        # fallback: return all
        results = [{"title": k, "content": v} for k, v in list(_mock_faqs.items())[:top_k]]

    import json
    return json.dumps(results[:top_k], ensure_ascii=False)
