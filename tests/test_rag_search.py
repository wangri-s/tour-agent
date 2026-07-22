"""RAG 检索工具测试 —— 语义搜索 + 关键词降级

运行方式:
    python tests/test_rag_search.py
    pytest tests/test_rag_search.py -v
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("rag-test")


# =============================================================================
# 单元测试: 降级链路 (不需要外部服务)
# =============================================================================

class TestRAGFallback:
    """RAG 不可用时自动回退关键词匹配"""

    @patch("tools.rag_search.embedding_service")
    @patch("tools.rag_search.milvus_store")
    async def test_embedding_failure_falls_back(self, mock_milvus, mock_embedding):
        """Embedding 失败 → 关键词回退"""
        from tools.rag_search import rag_search

        # 模拟 Embedding 失败
        mock_embedding.embed_query = AsyncMock(return_value=None)

        result = await rag_search.ainvoke({"query": "北京故宫攻略", "top_k": 3})
        data = json.loads(result)

        assert len(data) > 0, "降级应返回结果"
        # 关键词匹配应该找到"北京"相关条目
        titles = [d["title"] for d in data]
        assert any("北京" in t or "故宫" in t for t in titles), f"应匹配到北京相关内容，实际: {titles}"
        logger.info(f"✅ 降级测试通过: {len(data)} 条结果")

    @patch("tools.rag_search.embedding_service")
    @patch("tools.rag_search.milvus_store")
    async def test_milvus_down_falls_back(self, mock_milvus, mock_embedding):
        """Milvus 连接失败 → Embedding 可用 → 回退关键词"""
        from tools.rag_search import rag_search

        # Embedding 成功但 Milvus 返回空
        mock_embedding.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_milvus.ensure_connected = AsyncMock(return_value=True)
        mock_milvus.search = AsyncMock(return_value=[])  # 无结果

        result = await rag_search.ainvoke({"query": "上海美食推荐", "top_k": 3})
        data = json.loads(result)

        assert len(data) > 0
        assert any("上海" in d["content"] or "美食" in d["content"] for d in data)
        logger.info(f"✅ Milvus无结果降级: {len(data)} 条")

    @patch("tools.rag_search.redis_cache")
    @patch("tools.rag_search.embedding_service")
    @patch("tools.rag_search.milvus_store")
    async def test_cache_hit(self, mock_milvus, mock_embedding, mock_redis):
        """Redis 缓存命中 → 直接返回，不调 Embedding"""
        from tools.rag_search import rag_search

        cached = json.dumps(
            [{"doc_id": "c1", "title": "测试", "content": "haha", "score": 0.99}],
            ensure_ascii=False,
        )
        mock_redis.get_tool_cache = AsyncMock(return_value=cached)

        result = await rag_search.ainvoke({"query": "测试查询", "top_k": 3})
        data = json.loads(result)

        assert len(data) == 1
        assert data[0]["title"] == "测试"
        assert data[0]["score"] == 0.99

        # Embedding 不应被调用
        mock_embedding.embed_query.assert_not_called()
        logger.info("✅ 缓存命中测试通过")


class TestKeywordFallback:
    """关键词降级的各种查询场景"""

    @staticmethod
    async def _search(query: str, top_k: int = 3) -> list[dict]:
        from tools.rag_search import _keyword_fallback
        result = await _keyword_fallback(query, top_k)
        return json.loads(result)

    async def test_visa_query(self):
        data = await self._search("中国签证怎么办理")
        assert len(data) > 0
        titles = " ".join(d["title"] for d in data)
        assert any(kw in titles for kw in ["签证", "入境", "免签"]), f"应匹配签证: {titles}"
        logger.info(f"✅ 签证查询: {len(data)} 条")

    async def test_city_query(self):
        data = await self._search("北京旅游攻略", top_k=3)
        assert any("北京" in d["title"] for d in data), "应精确匹配北京"
        logger.info(f"✅ 城市查询: {len(data)} 条")

    async def test_no_match_returns_help(self):
        data = await self._search("xyz123完全不存在的查询")
        assert len(data) == 1
        assert data[0]["title"] == "帮助"
        logger.info("✅ 无匹配返回帮助")

    async def test_budget_query(self):
        data = await self._search("旅行预算 费用", top_k=3)
        assert any(
            kw in " ".join(d["title"] for d in data) for kw in ["预算", "费用"]
        ), f"应匹配预算: {[d['title'] for d in data]}"
        logger.info(f"✅ 预算查询: {len(data)} 条")


# =============================================================================
# 集成测试: 真实 Embedding (需要 DashScope API Key)
# =============================================================================

async def test_real_embedding():
    """测试真实 Embedding API 调用"""
    from services.vector_store import embedding_service

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key or "xxx" in api_key:
        logger.warning("⏭️  跳过 (无 API Key)")
        return

    logger.info("🧪 测试 DashScope Embedding API...")
    vectors = await embedding_service.embed(["北京是中国的首都", "上海是金融中心"])

    assert len(vectors) == 2, f"应返回2个向量，实际{len(vectors)}"
    assert len(vectors[0]) == 1024, f"向量维度应为1024，实际{len(vectors[0])}"
    # 验证确实有值 (非全0)
    assert sum(abs(v) for v in vectors[0]) > 0.01, "向量不应全为0"
    logger.info(f"✅ Embedding API 正常: {len(vectors)}条 × {len(vectors[0])}维")

    # 查询向量
    query_vec = await embedding_service.embed_query("北京有什么好玩的")
    assert query_vec is not None
    assert len(query_vec) == 1024
    logger.info("✅ 查询向量化正常")


# =============================================================================
# Main
# =============================================================================

async def main():
    logger.info("=" * 60)
    logger.info("🧪 RAG 检索测试")
    logger.info("=" * 60)

    # --- 单元测试 (无依赖) ---
    logger.info("\n📦 单元测试: 降级链路")
    test = TestRAGFallback()
    await test.test_embedding_failure_falls_back()
    await test.test_milvus_down_falls_back()
    await test.test_cache_hit()

    logger.info("\n📦 单元测试: 关键词回退")
    kt = TestKeywordFallback()
    await kt.test_visa_query()
    await kt.test_city_query()
    await kt.test_no_match_returns_help()
    await kt.test_budget_query()

    # --- 集成测试 (需要 API Key) ---
    logger.info("\n📦 集成测试: 真实 Embedding")
    await test_real_embedding()

    logger.info("\n" + "=" * 60)
    logger.info("✅ RAG 检索测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
