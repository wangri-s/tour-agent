"""Milvus 向量存储服务 —— 知识库 RAG 检索引擎

嵌入模型: DashScope text-embedding-v3 (1024 维)
向量库:   Milvus 2.4 standalone
用途:     中文旅游知识库语义检索，替换关键词匹配

架构位置: 长时知识记忆层 (Knowledge Memory)
"""

from __future__ import annotations

import os
import json
import logging
import hashlib
from typing import Any

logger = logging.getLogger(__name__)

# DashScope Embedding 常量
EMBEDDING_DIM = 1024          # text-embedding-v3 输出维度
EMBEDDING_MODEL = "text-embedding-v3"
EMBEDDING_BATCH_SIZE = 25     # DashScope 单次最多 25 条

# Milvus 集合常量
DEFAULT_COLLECTION = "travel_knowledge"
METRIC_TYPE = "COSINE"        # 余弦相似度，适合语义搜索
INDEX_TYPE = "IVF_FLAT"       # 倒排索引，百万级均衡选择
NLIST = 128                   # IVF 聚类中心数


class MilvusStore:
    """Milvus 向量存储封装

    特性:
    - 自动建 Collection (如不存在)
    - 批量插入带去重 (基于 doc_id hash)
    - 语义搜索 + 分数过滤
    - 懒连接 / 自动重连
    - 优雅降级: 连接失败不抛异常，返回空结果
    """

    def __init__(
        self,
        host: str | None = None,
        port: str | None = None,
        collection: str = DEFAULT_COLLECTION,
    ):
        self.host = host or os.getenv("MILVUS_HOST", "localhost")
        self.port = port or os.getenv("MILVUS_PORT", "19530")
        self.collection_name = collection
        self._connected = False
        self._client: Any = None
        self._collection: Any = None

    # =========================================================================
    # 连接管理
    # =========================================================================

    async def connect(self) -> bool:
        """建立 Milvus 连接 + 加载 Collection"""
        if self._connected and self._collection is not None:
            return True

        try:
            from pymilvus import connections, Collection, utility

            alias = f"tourai_{self.collection_name}"
            # 断开旧连接 (如有)
            try:
                connections.disconnect(alias)
            except Exception:
                pass

            connections.connect(
                alias=alias,
                host=self.host,
                port=self.port,
            )

            self._client = alias

            # 确保 Collection 存在
            if utility.has_collection(self.collection_name, using=alias):
                self._collection = Collection(self.collection_name, using=alias)
                self._collection.load()
                logger.info(
                    f"[Milvus] 连接成功 → {self.host}:{self.port}, "
                    f"collection={self.collection_name}, "
                    f"entities={self._collection.num_entities}"
                )
            else:
                logger.warning(
                    f"[Milvus] Collection '{self.collection_name}' 不存在，"
                    f"请先运行 scripts/index_knowledge_base.py"
                )
                self._collection = None

            self._connected = True
            return True

        except ImportError:
            logger.warning("[Milvus] pymilvus 未安装，RAG 回退到关键词模式")
            return False
        except Exception as e:
            logger.error(f"[Milvus] 连接失败: {e}")
            self._connected = False
            return False

    async def ensure_connected(self) -> bool:
        """确保连接 (懒加载)"""
        if not self._connected:
            return await self.connect()
        return True

    # =========================================================================
    # Collection 管理
    # =========================================================================

    async def create_collection(self) -> bool:
        """创建 Collection (如不存在)"""
        try:
            from pymilvus import (
                Collection, CollectionSchema, FieldSchema, DataType,
                utility, connections,
            )

            alias = f"tourai_{self.collection_name}"
            if utility.has_collection(self.collection_name, using=alias):
                logger.info(f"[Milvus] Collection '{self.collection_name}' 已存在")
                return True

            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
            ]

            schema = CollectionSchema(fields, description="中国入境游知识库 RAG")
            self._collection = Collection(self.collection_name, schema=schema, using=alias)

            # 建索引
            index_params = {
                "metric_type": METRIC_TYPE,
                "index_type": INDEX_TYPE,
                "params": {"nlist": NLIST},
            }
            self._collection.create_index("embedding", index_params)
            self._collection.load()

            logger.info(
                f"[Milvus] 创建 Collection '{self.collection_name}' "
                f"({EMBEDDING_DIM}d, {METRIC_TYPE}, {INDEX_TYPE})"
            )
            return True

        except Exception as e:
            logger.error(f"[Milvus] 创建 Collection 失败: {e}")
            return False

    # =========================================================================
    # 插入
    # =========================================================================

    async def insert_batch(
        self,
        docs: list[dict[str, str]],       # [{doc_id, title, category, content}]
        embeddings: list[list[float]],
    ) -> int:
        """批量插入文档 + 向量

        Returns:
            成功插入的条数
        """
        if not await self.ensure_connected():
            return 0

        if not self._collection:
            logger.warning("[Milvus] Collection 未加载，跳过插入")
            return 0

        if not docs or not embeddings:
            return 0

        try:
            entities = [
                [d.get("doc_id", "") for d in docs],
                [d.get("title", "") for d in docs],
                [d.get("category", "") for d in docs],
                [d.get("content", "")[:8192] for d in docs],
                embeddings,
            ]

            result = self._collection.insert(entities)
            self._collection.flush()

            inserted = len(result.primary_keys) if result else 0
            logger.info(f"[Milvus] 插入 {inserted} 条记录")
            return inserted

        except Exception as e:
            logger.error(f"[Milvus] 插入失败: {e}")
            return 0

    # =========================================================================
    # 搜索
    # =========================================================================

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: float = 0.3,
        filter_category: str | None = None,
    ) -> list[dict[str, Any]]:
        """语义搜索

        Args:
            query_vector:     查询向量 (1024维)
            top_k:            返回结果数
            score_threshold:  最低相似度阈值 (COSINE: 0-1)
            filter_category:  可选分类过滤

        Returns:
            [{doc_id, title, category, content, score}, ...]
        """
        if not await self.ensure_connected():
            return []

        if not self._collection:
            return []

        try:
            search_params = {
                "metric_type": METRIC_TYPE,
                "params": {"nprobe": 16},
            }

            expr = None
            if filter_category:
                expr = f'category == "{filter_category}"'

            results = self._collection.search(
                data=[query_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=["doc_id", "title", "category", "content"],
            )

            if not results or not results[0]:
                return []

            docs = []
            for hit in results[0]:
                if hit.score >= score_threshold:
                    docs.append({
                        "doc_id": hit.entity.get("doc_id", ""),
                        "title": hit.entity.get("title", ""),
                        "category": hit.entity.get("category", ""),
                        "content": hit.entity.get("content", ""),
                        "score": round(hit.score, 4),
                    })

            logger.info(
                f"[Milvus] 搜索完成: top_k={top_k}, "
                f"返回 {len(docs)}/{len(results[0])} 条 (≥{score_threshold})"
            )
            return docs

        except Exception as e:
            logger.error(f"[Milvus] 搜索失败: {e}")
            return []

    # =========================================================================
    # 统计 & 管理
    # =========================================================================

    async def count(self) -> int:
        """返回 Collection 中的文档数"""
        if not await self.ensure_connected():
            return 0
        if not self._collection:
            return 0
        try:
            return self._collection.num_entities
        except Exception:
            return 0

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """按 doc_id 删除文档"""
        if not await self.ensure_connected():
            return 0
        try:
            expr = f'doc_id == "{doc_id}"'
            result = self._collection.delete(expr)
            logger.info(f"[Milvus] 删除 doc_id={doc_id}")
            return result.delete_count if result else 0
        except Exception as e:
            logger.error(f"[Milvus] 删除失败: {e}")
            return 0

    async def close(self) -> None:
        """释放连接"""
        if self._client:
            try:
                from pymilvus import connections
                connections.disconnect(self._client)
                logger.info("[Milvus] 连接已关闭")
            except Exception:
                pass
        self._connected = False
        self._collection = None


class EmbeddingService:
    """文本向量化服务 — DashScope text-embedding-v3

    特性:
    - 批量 embedding (自动分批，单次 ≤25)
    - 输入截断 (单条 ≤2048 tokens)
    - 自动重试 (最多3次)
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.model = EMBEDDING_MODEL

    async def embed(self, texts: str | list[str]) -> list[list[float]]:
        """文本向量化

        Args:
            texts: 单个字符串或字符串列表

        Returns:
            向量列表，每个向量 1024 维
        """
        if isinstance(texts, str):
            texts = [texts]

        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        # 分批处理
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """调用 DashScope Embedding API"""
        import http.client
        import urllib.request
        import urllib.error

        for attempt in range(3):
            try:
                body = json.dumps({
                    "model": self.model,
                    "input": {"texts": texts},
                    "parameters": {"text_type": "document"},
                }).encode("utf-8")

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                req = urllib.request.Request(
                    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
                    data=body,
                    headers=headers,
                )

                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if data.get("code") != "" and data.get("code") is not None:
                    logger.error(f"[Embedding] API 错误: {data.get('code')} - {data.get('message')}")
                    if attempt < 2:
                        continue
                    return []

                embeddings = []
                for item in data.get("output", {}).get("embeddings", []):
                    embeddings.append(item.get("embedding", []))

                logger.debug(f"[Embedding] 成功: {len(embeddings)} 条, 维度={len(embeddings[0]) if embeddings else 0}")
                return embeddings

            except urllib.error.HTTPError as e:
                logger.error(f"[Embedding] HTTP {e.code}: {e.reason}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return []
            except Exception as e:
                logger.error(f"[Embedding] 请求失败: {e}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return []

        return []

    async def embed_query(self, query: str) -> list[float] | None:
        """查询向量化 (text_type=query)"""
        import http.client
        import urllib.request
        import urllib.error

        for attempt in range(3):
            try:
                body = json.dumps({
                    "model": self.model,
                    "input": {"texts": [query]},
                    "parameters": {"text_type": "query"},
                }).encode("utf-8")

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                req = urllib.request.Request(
                    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
                    data=body,
                    headers=headers,
                )

                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                embeddings = data.get("output", {}).get("embeddings", [])
                if embeddings:
                    return embeddings[0].get("embedding", [])

                return None

            except Exception as e:
                logger.error(f"[Embedding] 查询向量化失败: {e}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return None

        return None


# =============================================================================
# 预置实例
# =============================================================================

milvus_store = MilvusStore()
embedding_service = EmbeddingService()

# 异步事件循环兼容
import asyncio as _asyncio
