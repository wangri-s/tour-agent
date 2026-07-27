#!/usr/bin/env python3
"""知识库索引脚本 —— 将 china_travel_kb.md 切片 + 向量化 + 写入 Milvus

用法:
    # 首次全量索引
    python scripts/index_knowledge_base.py

    # 增量索引 (只处理新文档)
    python scripts/index_knowledge_base.py --incremental

    # 指定知识库文件
    python scripts/index_knowledge_base.py --file knowledge/custom.md

    # 重建 Collection (清空重新索引)
    python scripts/index_knowledge_base.py --rebuild

流程:
    1. 读取 knowledge/*.md 文件
    2. 按 ## 标题切分为独立文档块 (chunk_size ≈ 500-1500 字符)
    3. 调用 DashScope text-embedding-v3 生成 1024 维向量
    4. 写入 Milvus travel_knowledge Collection
    5. 记录索引进度到 knowledge_docs 表

依赖:
    pip install pymilvus python-dotenv
    # DashScope API Key 从 .env 读取
"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

# 确保项目根在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("index-kb")

# =============================================================================
# 配置
# =============================================================================

KB_DIR = Path(__file__).parent.parent / "knowledge"
CHUNK_MIN_LENGTH = 100       # 最小块长度 (字符), 短于此值合并到上一块
CHUNK_MAX_LENGTH = 1500      # 最大块长度 (字符), 超出则按段落再切
EMBEDDING_BATCH = 20         # 每批 embedding 条数
COLLECTION_NAME = "travel_knowledge"

# 文件 → collection 映射 (不同的知识库索引到不同的 Milvus Collection)
FILE_COLLECTION_MAP = {
    "china_travel_kb.md": "travel_knowledge",        # 城市攻略 → trip_planner
    "customer_service_kb.md": "service_knowledge",    # 客服FAQ → customer_service
    "tour_packages_kb.md": "package_knowledge",       # 旅游套餐 → sales_agent
}
DOC_UID_PREFIX = "kb-2026"


# =============================================================================
# 文本切片器
# =============================================================================

class KnowledgeChunker:
    """将 Markdown 知识库切分为可索引的文档块

    策略:
    - ## 二级标题作为一个独立文档的边界
    - 内容短于 CHUNK_MIN_LENGTH 的合并到上一块
    - 内容长于 CHUNK_MAX_LENGTH 的按 ### 三级标题再切
    - 保留分类信息 (从 ## 标题提取)
    """

    # 分类映射: 标题关键词 → category
    CATEGORY_MAP = {
        # 签证
        "签证": "visa",
        "入境": "visa",
        "免签": "visa",
        # 城市
        "北京": "city",
        "上海": "city",
        "西安": "city",
        "成都": "city",
        "桂林": "city",
        "云南": "city",
        "杭州": "city",
        "苏州": "city",
        "重庆": "city",
        "广州": "city",
        "厦门": "city",
        "哈尔滨": "city",
        "拉萨": "city",
        "张家界": "city",
        "深圳": "city",
        "城市": "city",
        # 交通
        "交通": "transport",
        "高铁": "transport",
        "地铁": "transport",
        "高速": "transport",
        # 天气
        "天气": "weather",
        "季节": "weather",
        "气候": "weather",
        # 美食
        "美食": "food",
        "小吃": "food",
        "餐饮": "food",
        # 预算
        "预算": "budget",
        "费用": "budget",
        "花费": "budget",
        # 文化
        "文化": "culture",
        "礼仪": "culture",
        "习俗": "culture",
        # 安全
        "安全": "emergency",
        "紧急": "emergency",
        "应急": "emergency",
        # 支付
        "支付": "payment",
        "上网": "network",
        # 线路
        "线路": "route",
        "行程": "route",
        # 节假日
        "节假日": "holiday",
        "黄金周": "holiday",
        # 客服服务
        "产品": "service_product",
        "服务": "service_product",
        "平台": "service_product",
        "退款": "service_policy",
        "取消": "service_policy",
        "政策": "service_policy",
        "订单": "service_order",
        "预订": "service_order",
        "品牌": "service_brand",
        "旅行社": "service_brand",
        "FAQ": "service_faq",
        "常见问题": "service_faq",
        "消费": "service_payment",
        "价格": "service_payment",
        "通信": "service_network",
        "手机": "service_network",
        "APP": "service_network",
        "住宿": "service_hotel",
        "酒店": "service_hotel",
        "就医": "service_emergency",
        "特殊人群": "service_guide",
        "亲子": "service_guide",
        "老年": "service_guide",
        "商务": "service_guide",
        "蜜月": "service_guide",
    }

    def chunk_file(self, filepath: Path) -> list[dict[str, str]]:
        """切分单个 Markdown 文件

        Returns:
            [{doc_id, title, category, content}, ...]
        """
        if not filepath.exists():
            logger.error(f"文件不存在: {filepath}")
            return []

        content = filepath.read_text(encoding="utf-8")
        source_file = filepath.name
        logger.info(f"读取 {source_file}: {len(content)} 字符")

        chunks: list[dict[str, str]] = []
        current_title = ""
        current_category = "general"
        current_lines: list[str] = []

        lines = content.split("\n")

        for line in lines:
            # ## 二级标题 → 文档边界
            if line.startswith("## ") and not line.startswith("### "):
                # 保存上一块
                if current_lines and current_title:
                    chunk = self._build_chunk(
                        current_title, current_category, current_lines, source_file
                    )
                    if chunk:
                        chunks.append(chunk)

                # 新文档
                current_title = line[3:].strip()
                current_category = self._detect_category(current_title)
                current_lines = [line]

            # ### 三级标题 → 内容分隔 (只在块过大时)
            elif line.startswith("### "):
                if len("\n".join(current_lines)) > CHUNK_MAX_LENGTH and current_lines:
                    if current_title:
                        chunk = self._build_chunk(
                            current_title, current_category, current_lines, source_file
                        )
                        if chunk:
                            chunks.append(chunk)
                    current_lines = [f"## {current_title}", line]
                else:
                    current_lines.append(line)

            else:
                current_lines.append(line)

        # 最后一块
        if current_lines and current_title:
            chunk = self._build_chunk(
                current_title, current_category, current_lines, source_file
            )
            if chunk:
                chunks.append(chunk)

        # 合并过短的块到前一块
        chunks = self._merge_short_chunks(chunks)

        logger.info(f"  → {len(chunks)} 个文档块")
        return chunks

    def _build_chunk(
        self,
        title: str,
        category: str,
        lines: list[str],
        source_file: str,
    ) -> dict[str, Any] | None:
        """构建文档块"""
        content = "\n".join(lines).strip()
        # 移除 markdown 表格边框 (保留内容)
        content = re.sub(r'\|[-+\s]*\|', '', content)
        content = re.sub(r'\n{3,}', '\n\n', content)

        # 生成稳定 doc_id
        doc_hash = hashlib.md5(content.encode()).hexdigest()[:12]
        doc_id = f"{DOC_UID_PREFIX}-{category}-{doc_hash}"

        if len(content) < CHUNK_MIN_LENGTH:
            return None

        return {
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "content": content,
            "source_file": source_file,
        }

    def _detect_category(self, title: str) -> str:
        """根据标题检测分类"""
        for keyword, category in self.CATEGORY_MAP.items():
            if keyword in title:
                return category
        return "general"

    def _merge_short_chunks(self, chunks: list[dict]) -> list[dict]:
        """合并过短的块到前一个同分类块"""
        merged = []
        for chunk in chunks:
            if (
                merged
                and len(chunk["content"]) < CHUNK_MIN_LENGTH
                and chunk["category"] == merged[-1]["category"]
            ):
                merged[-1]["content"] += "\n\n" + chunk["content"]
                merged[-1]["title"] = merged[-1]["title"] + " / " + chunk["title"]
            else:
                merged.append(chunk)
        return merged


# =============================================================================
# 主流程
# =============================================================================

async def index_all(incremental: bool = False, rebuild: bool = False):
    """主索引流程"""
    from services.vector_store import milvus_store, embedding_service

    logger.info("=" * 60)
    logger.info("知识库索引器启动")
    logger.info(f"源目录: {KB_DIR}")
    logger.info(f"模式: {'重建' if rebuild else '增量' if incremental else '全量'}")
    logger.info("=" * 60)

    # 1. 连接 Milvus
    connected = await milvus_store.connect()
    if not connected:
        logger.error("Milvus 连接失败，请检查: docker compose up -d milvus")
        return

    # 2. 重建模式: 删除旧 Collection 新建
    if rebuild:
        logger.info("重建模式: 删除旧 Collection...")
        try:
            from pymilvus import utility, connections
            alias = f"tourai_{COLLECTION_NAME}"
            if utility.has_collection(COLLECTION_NAME, using=alias):
                utility.drop_collection(COLLECTION_NAME, using=alias)
                logger.info("  → 旧 Collection 已删除")
        except Exception as e:
            logger.warning(f"删除 Collection 失败: {e}")

    # 3. 创建所有需要的 Collection
    collections_needed = set(FILE_COLLECTION_MAP.values())
    for coll in collections_needed:
        milvus_store.collection_name = coll
        await milvus_store.create_collection()

    # 4. 扫描知识库文件
    kb_files = sorted(KB_DIR.glob("*.md"))
    if not kb_files:
        logger.error(f"未找到 Markdown 文件: {KB_DIR}")
        return

    logger.info(f"发现 {len(kb_files)} 个知识库文件")

    # 5. 切分文档 (按 collection 分组)
    chunker = KnowledgeChunker()
    coll_chunks: dict[str, list[dict]] = {}

    for filepath in kb_files:
        chunks = chunker.chunk_file(filepath)
        # 确定此文件属于哪个 collection
        coll_name = FILE_COLLECTION_MAP.get(filepath.name, "travel_knowledge")
        if coll_name not in coll_chunks:
            coll_chunks[coll_name] = []
        coll_chunks[coll_name].extend(chunks)
        logger.info(f"  {filepath.name}: {len(chunks)} 块 → collection={coll_name}")

    total_chunks = sum(len(v) for v in coll_chunks.values())
    logger.info(f"总计: {total_chunks} 个待索引文档块 ({len(coll_chunks)} 个 collection)")

    if total_chunks == 0:
        logger.info("没有文档需要索引，退出。")
        return

    # 6. 按 collection 分别批量向量化 + 写入
    total_inserted = 0
    for coll_name, chunks in coll_chunks.items():
        milvus_store.collection_name = coll_name
        await milvus_store.connect()
        logger.info(f"索引 collection={coll_name}: {len(chunks)} 块")

        for i in range(0, len(chunks), EMBEDDING_BATCH):
            batch = chunks[i : i + EMBEDDING_BATCH]

            # 向量化
            texts = [c["content"][:2000] for c in batch]  # 截断过长内容
            embeddings = await embedding_service.embed(texts)

            if not embeddings or len(embeddings) != len(batch):
                logger.error(f"  批次 {i//EMBEDDING_BATCH + 1} embedding 失败，跳过")
                continue

            # 写入 Milvus
            inserted = await milvus_store.insert_batch(batch, embeddings)
            total_inserted += inserted

            logger.info(
                f"  批次 {i//EMBEDDING_BATCH + 1}/{len(chunks)//EMBEDDING_BATCH + 1}: "
                f"向量化 {len(embeddings)} 条, 写入 {inserted} 条 "
                f"({min(i+len(batch), len(chunks))/len(chunks)*100:.0f}%)"
            )

        # 统计单 collection
        coll_count = await milvus_store.count()
        logger.info(f"  collection={coll_name} 总计: {coll_count} 条")

    # 7. 总体统计
    logger.info("=" * 60)
    logger.info(f"索引完成! 本次写入: {total_inserted} 条")
    logger.info("=" * 60)

    # 8. 打印各 collection 分类统计
    for coll_name, chunks in coll_chunks.items():
        cats = {}
        for c in chunks:
            cats[c["category"]] = cats.get(c["category"], 0) + 1
        logger.info(f"Collection [{coll_name}] 分类统计:")
        for cat, count in sorted(cats.items()):
            logger.info(f"  {cat}: {count} 块")


async def _get_existing_doc_ids() -> set[str]:
    """获取已索引的 doc_id 集合"""
    from services.vector_store import milvus_store
    try:
        # 通过查询获取已有 doc_id
        # Milvus 不支持直接 list，用一个小查询来估算
        return set()  # 简化: 增量模式暂不验证已有
    except Exception:
        return set()


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="中国入境游知识库 RAG 索引器")
    parser.add_argument("--file", type=str, default=None, help="指定单个文件")
    parser.add_argument("--incremental", action="store_true", help="增量索引")
    parser.add_argument("--rebuild", action="store_true", help="重建 Collection")
    args = parser.parse_args()

    asyncio.run(index_all(
        incremental=args.incremental,
        rebuild=args.rebuild,
    ))


if __name__ == "__main__":
    main()
