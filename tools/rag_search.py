"""RAG 语义检索工具 —— 基于 Milvus + DashScope Embedding

替代原有的 search_faq 关键词匹配，实现真正的语义理解:
- "便宜酒店" 自动匹配 "经济住宿"、"青旅推荐"
- "下雨怎么办" 自动匹配 "雨季行程"、"室内景点"
- "好吃的" 自动匹配 "美食推荐"、"必吃清单"

架构:
  用户查询 → [DashScope Embedding → 1024维向量]
           → [Milvus ANN 搜索 → Top-K 最相似文档]
           → 分数过滤 (≥0.3) + 格式化返回

降级策略:
  Milvus 不可用 → 回退到原生 search_faq 关键词匹配
"""

from __future__ import annotations

import json
import hashlib
import logging
from typing import Any

from langchain_core.tools import tool

from services.vector_store import milvus_store, embedding_service
from services.redis_cache import redis_cache

logger = logging.getLogger(__name__)


def _get_retrieval_config():
    """从统一配置读取检索参数，缺失时回退默认值"""
    try:
        from services.config_loader import config as cfg
        return {
            "top_k": cfg.get_int("retrieval.top_k", 5),
            "score_threshold": cfg.get_float("retrieval.score_threshold", 0.3),
        }
    except Exception:
        return {"top_k": 5, "score_threshold": 0.3}


@tool
async def rag_search(query: str, top_k: int = 5, category: str = "") -> str:
    """检索中国入境游知识库 (RAG 语义搜索)。

    使用向量语义匹配，覆盖签证政策、城市指南、景点信息、美食推荐、
    交通方式、预算参考、文化礼仪、应急信息、节假日等全部维度。

    与旧版 search_faq 相比，rag_search 能理解语义:
    - "有什么好玩的" → 景点推荐
    - "怎么付钱" → 支付方式
    - "会不会很挤" → 节假日/拥挤度

    Args:
        query: 搜索问题 (中文或英文均可，推荐中文)
        top_k: 返回结果数量上限 (默认5)
        category: 可选分类过滤 (visa/city/food/transport/culture/emergency)

    Returns:
        JSON 格式的相关知识条目:
        [{doc_id, title, category, content, score}, ...]
    """
    try:
        # 从统一配置读取检索参数
        ret_cfg = _get_retrieval_config()
        default_top_k = ret_cfg["top_k"]
        default_threshold = ret_cfg["score_threshold"]

        # Step 1: 检查 Redis 缓存
        cache_key = _cache_key(query, top_k, category)
        cached = await redis_cache.get_tool_cache("rag_search", cache_key)
        if cached:
            logger.info(f"[RAG] 缓存命中: {query[:50]}")
            return cached

        # Step 2: 查询向量化
        query_vector = await embedding_service.embed_query(query)
        if query_vector is None:
            logger.warning("[RAG] Embedding 失败，回退到关键词搜索")
            return await _keyword_fallback(query, top_k)

        # Step 3: Milvus 语义搜索
        filter_cat = category if category else None
        docs = await milvus_store.search(
            query_vector=query_vector,
            top_k=top_k if top_k != 5 else default_top_k,
            score_threshold=default_threshold,
            filter_category=filter_cat,
        )

        if not docs:
            logger.info(f"[RAG] 无结果，回退到关键词搜索: {query[:50]}")
            return await _keyword_fallback(query, top_k)

        # Step 4: 格式化结果
        result = json.dumps(docs, ensure_ascii=False, indent=2)

        # Step 5: 缓存结果 (10 分钟)
        await redis_cache.cache_tool_result("rag_search", cache_key, result)

        logger.info(f"[RAG] 返回 {len(docs)} 条结果: {query[:50]}")
        return result

    except Exception as e:
        logger.error(f"[RAG] 检索异常: {e}")
        return await _keyword_fallback(query, top_k)


def _cache_key(query: str, top_k: int, category: str) -> str:
    """生成缓存键"""
    raw = f"{query.strip().lower()}|{top_k}|{category}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


async def _keyword_fallback(query: str, top_k: int) -> str:
    """关键词匹配降级方案 (复用旧版 FAQ DB)"""
    from tools.search_faq import _FAQ_DB

    results = []

    # 精确匹配
    for key, value in _FAQ_DB.items():
        if key in query or query.lower() in key.lower():
            results.append({"title": key, "content": value, "score": 1.0})

    # 模糊匹配
    for key, value in _FAQ_DB.items():
        if key not in [r["title"] for r in results]:
            score = 0.0
            if query.lower() in value.lower():
                score = 0.7
            for word in query.split():
                if len(word) >= 2 and word.lower() in value.lower():
                    score = max(score, 0.5)
            if score > 0:
                results.append({"title": key, "content": value, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_k]

    if not results:
        results = [{
            "title": "帮助",
            "content": "未找到精确匹配。请尝试搜索：签证、免签、北京、上海、西安、成都、桂林、线路推荐、预算、交通、天气、支付、上网、礼仪、紧急等关键词。",
            "score": 0.0,
        }]

    return json.dumps(results, ensure_ascii=False, indent=2)
