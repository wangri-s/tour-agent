"""套餐检索工具 — Milvus 语义检索 + MySQL 结构化数据联合查询

用于 SalesAgent 的套餐推荐:
  1. 从行程/用户需求提取查询特征
  2. Milvus 语义匹配 → 拿到 package_id
  3. MySQL 查完整套餐数据 → 返回结构化套餐信息
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


async def _search_packages_rag(query: str, top_k: int = 5) -> list[dict]:
    """Milvus 语义搜索套餐"""
    try:
        from services.vector_store import milvus_store, embedding_service
        from services.redis_cache import redis_cache

        # 检查缓存
        import hashlib
        cache_key = hashlib.md5(f"pkg:{query}:{top_k}".encode()).hexdigest()[:12]
        cached = await redis_cache.get_tool_cache("package_search", cache_key)
        if cached:
            return json.loads(cached)

        # Embedding
        query_vector = await embedding_service.embed_query(query)
        if query_vector is None:
            return []

        # 切换到套餐 collection 搜索
        original_collection = milvus_store.collection_name
        milvus_store.collection_name = "package_knowledge"
        try:
            await milvus_store.connect()
            docs = await milvus_store.search(
                query_vector=query_vector,
                top_k=top_k,
                score_threshold=0.3,
            )
        finally:
            milvus_store.collection_name = original_collection

        await redis_cache.cache_tool_result("package_search", cache_key, json.dumps(docs, ensure_ascii=False))
        return docs or []

    except Exception as e:
        logger.warning(f"[PackageSearch] RAG 检索失败: {e}")
        return []


async def _query_packages_mysql(package_ids: list[str]) -> list[dict]:
    """MySQL 批量查询套餐详情"""
    if not package_ids:
        return []

    try:
        from services.mysql_store import mysql_store

        if not mysql_store._pool:
            await mysql_store.connect()
        if not mysql_store._pool:
            return []

        placeholders = ",".join(["%s"] * len(package_ids))
        sql = f"""
            SELECT package_id, name, city, days, nights,
                   budget_min, budget_max, hotel_level, package_level,
                   themes, highlights, inclusions, suitable_for,
                   min_pax, season_note, cover_desc
            FROM tour_packages
            WHERE package_id IN ({placeholders}) AND status = 'active'
        """

        async with mysql_store._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, package_ids)
                rows = await cur.fetchall()

        packages = []
        for row in rows:
            packages.append({
                "package_id": row[0],
                "name": row[1],
                "city": row[2],
                "days": row[3],
                "nights": row[4],
                "budget_min": float(row[5]),
                "budget_max": float(row[6]),
                "hotel_level": row[7],
                "package_level": row[8],
                "themes": row[9],
                "highlights": row[10],
                "inclusions": json.loads(row[11]) if isinstance(row[11], str) else row[11],
                "suitable_for": row[12] or "",
                "min_pax": row[13],
                "season_note": row[14] or "",
                "cover_desc": row[15] or "",
            })

        return packages

    except Exception as e:
        logger.warning(f"[PackageSearch] MySQL 查询失败: {e}")
        return []


@tool
async def search_tour_packages(
    query: str = "",
    city: str = "",
    days: int = 0,
    budget: float = 0,
    theme: str = "",
    package_level: str = "",
    top_k: int = 5,
) -> str:
    """搜索旅游套餐产品 — RAG语义匹配 + MySQL精确查询

    Args:
        query: 自然语言查询 (如"北京文化深度游"、"成都美食火锅")
        city: 目的地城市筛选 (可选)
        days: 行程天数筛选 (可选)
        budget: 人均预算筛选 (可选)
        theme: 主题筛选 (可选: 文化/美食/自然/摄影/亲子/蜜月/商务/冰雪)
        package_level: 套餐等级 (可选: 经济版/标准版/奢华版)
        top_k: 返回数量

    Returns:
        JSON格式套餐列表，包含名称/价格/天数/亮点/包含项目等完整信息
    """
    # 构建搜索查询
    search_parts = []
    if query:
        search_parts.append(query)
    if city:
        search_parts.append(city)
    if theme:
        search_parts.append(f"{theme}主题")
    if package_level:
        search_parts.append(package_level)

    search_query = " ".join(search_parts) if search_parts else "旅游套餐"

    # 1. RAG 语义搜索
    rag_results = await _search_packages_rag(search_query, top_k=top_k)

    # 2. MySQL 查详情
    package_ids = [r.get("doc_id", "").replace("pkg-", "PKG-").upper() for r in rag_results]
    # 也尝试从 title/package_id 提取
    for r in rag_results:
        title = r.get("title", "")
        # 从标题提取 PKG-XXX
        import re
        match = re.search(r'PKG-\d+', title, re.IGNORECASE)
        if match and match.group().upper() not in package_ids:
            package_ids.append(match.group().upper())

    if not package_ids:
        # 降级: 直接用MySQL关键词搜索
        return await _fallback_mysql_search(city, days, budget, package_level)

    packages = await _query_packages_mysql(package_ids)

    # 3. 按预算/天数二次筛选
    if budget > 0:
        packages = [p for p in packages if p["budget_min"] <= budget <= p["budget_max"] * 1.3]
    if days > 0:
        packages = [p for p in packages if abs(p["days"] - days) <= 2]

    # 4. 格式化返回
    result = {
        "count": len(packages),
        "packages": packages,
        "search_query": search_query,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _fallback_mysql_search(
    city: str = "",
    days: int = 0,
    budget: float = 0,
    package_level: str = "",
) -> str:
    """MySQL 降级搜索 (Milvus 不可用时)"""
    try:
        from services.mysql_store import mysql_store

        if not mysql_store._pool:
            await mysql_store.connect()
        if not mysql_store._pool:
            return json.dumps({"count": 0, "packages": [], "note": "MySQL 不可用"})

        conditions = ["status = 'active'"]
        params: list[Any] = []

        if city:
            conditions.append("city LIKE %s")
            params.append(f"%{city}%")
        if days > 0:
            conditions.append("ABS(days - %s) <= 2")
            params.append(days)
        if budget > 0:
            conditions.append("budget_min <= %s AND budget_max >= %s")
            params.extend([budget, budget])
        if package_level:
            conditions.append("package_level = %s")
            params.append(package_level)

        where = " AND ".join(conditions)
        sql = f"""
            SELECT package_id, name, city, days, nights,
                   budget_min, budget_max, hotel_level, package_level,
                   themes, highlights, suitable_for, cover_desc
            FROM tour_packages
            WHERE {where}
            ORDER BY budget_min ASC
            LIMIT 5
        """

        async with mysql_store._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

        packages = []
        for row in rows:
            packages.append({
                "package_id": row[0],
                "name": row[1],
                "city": row[2],
                "days": row[3],
                "nights": row[4],
                "budget_min": float(row[5]),
                "budget_max": float(row[6]),
                "hotel_level": row[7],
                "package_level": row[8],
                "themes": row[9],
                "highlights": row[10] or "",
                "suitable_for": row[11] or "",
                "cover_desc": row[12] or "",
            })

        return json.dumps({
            "count": len(packages),
            "packages": packages,
            "search_query": f"city={city},days={days},budget={budget}",
            "note": "MySQL 降级搜索",
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"[PackageSearch] MySQL降级搜索失败: {e}")
        return json.dumps({"count": 0, "packages": [], "error": str(e)})
