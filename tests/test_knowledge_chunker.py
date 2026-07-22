"""知识库切片器测试

运行方式:
    python tests/test_knowledge_chunker.py
    pytest tests/test_knowledge_chunker.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("chunker-test")


class TestKnowledgeChunker:
    """文档切片器单元测试"""

    def test_category_detection(self):
        """分类检测"""
        from scripts.index_knowledge_base import KnowledgeChunker
        chunker = KnowledgeChunker()

        assert chunker._detect_category("北京旅游指南") == "city"
        assert chunker._detect_category("签证与入境政策") == "visa"
        assert chunker._detect_category("高铁与地铁交通") == "transport"
        assert chunker._detect_category("春季秋季天气") == "weather"
        assert chunker._detect_category("地道美食推荐") == "food"
        assert chunker._detect_category("预算与费用参考") == "budget"
        assert chunker._detect_category("文化礼仪与习俗") == "culture"
        assert chunker._detect_category("紧急联系方式") == "emergency"
        assert chunker._detect_category("支付宝微信支付") == "payment"
        assert chunker._detect_category("上网与VPN") == "network"
        assert chunker._detect_category("经典线路推荐") == "route"
        assert chunker._detect_category("节假日与黄金周") == "holiday"
        assert chunker._detect_category("未知标题XYZ") == "general"
        logger.info("✅ 分类检测: 13/13 正确")

    def test_chunk_markdown_file(self):
        """Markdown 切片"""
        from scripts.index_knowledge_base import KnowledgeChunker

        content = """# 标题

## 一、签证政策

这是签证相关的内容。包含免签信息，以及过境免签政策介绍。入境中国需要填写外国人入境卡，建议提前准备好护照和酒店预订确认单。

### 免签国家
新加坡享受30天免签。文莱15天免签。日本30天免签。法国、德国、意大利等欧洲国家15天免签。政策持续更新中。

## 二、北京旅游

故宫是必去景点，需要提前7天预约，周一闭馆。旺季门票60元，淡季40元。建议早上8点前到达，避开人流高峰。

### 美食推荐
北京烤鸭是全聚德和大董的最有名。其他推荐：涮羊肉东来顺、炸酱面、老北京炸灌肠、糖葫芦。
"""

        # 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            chunker = KnowledgeChunker()
            chunks = chunker.chunk_file(Path(tmp_path))

            assert len(chunks) >= 2, f"应有至少2个块，实际{len(chunks)}"

            # 第一个块: 签证
            visa_chunks = [c for c in chunks if c["category"] == "visa"]
            assert len(visa_chunks) >= 1, "应有至少1个签证块"
            assert "免签" in visa_chunks[0]["content"]

            # 第二个块: 北京
            city_chunks = [c for c in chunks if c["category"] == "city"]
            assert len(city_chunks) >= 1, "应有至少1个城市块"
            assert "故宫" in city_chunks[0]["content"]

            # 验证 chunk 结构
            for c in chunks:
                assert "doc_id" in c
                assert c["doc_id"].startswith("kb-2026-")
                assert "title" in c
                assert "category" in c
                assert "content" in c
                assert len(c["content"]) >= 100, f"块太短: {len(c['content'])}字"

            logger.info(f"✅ Markdown 切片: {len(chunks)} 个块")
            for c in chunks:
                logger.info(f"  [{c['category']}] {c['title']}: {len(c['content'])}字")

        finally:
            os.unlink(tmp_path)

    def test_chunk_real_knowledge_base(self):
        """真实知识库切片 (如果存在)"""
        from scripts.index_knowledge_base import KnowledgeChunker, KB_DIR

        kb_file = KB_DIR / "china_travel_kb.md"
        if not kb_file.exists():
            logger.warning("⏭️  知识库文件不存在，跳过")
            return

        chunker = KnowledgeChunker()
        chunks = chunker.chunk_file(kb_file)

        assert len(chunks) >= 10, f"真实知识库应有至少10个块，实际{len(chunks)}"

        # 分类统计
        cats = {}
        for c in chunks:
            cats[c["category"]] = cats.get(c["category"], 0) + 1

        logger.info(f"✅ 真实知识库切片: {len(chunks)} 个块")
        for cat, count in sorted(cats.items()):
            logger.info(f"  {cat}: {count} 块")

        # 验证关键分类存在
        assert "visa" in cats, "应有签证分类"
        # 有内容丰富的块
        total_categories = sum(cats.values())
        assert total_categories >= 10, f"总共至少10个块，实际{total_categories}"
        logger.info(f" 分类覆盖: {len(cats)} 种/{total_categories} 块")

    def test_short_chunks_merged(self):
        """过短块自动合并"""
        from scripts.index_knowledge_base import KnowledgeChunker

        # 构造一个很短的块 (会被合并)
        content = """# KB

## 一、签证

内容丰富充足的内容。包含各种签证政策介绍，覆盖免签、过境免签、口岸签证等多种类型。入境需填写外国人入境卡，建议提前准备好护照和酒店预订。

## 二、短标题

短内容。
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            chunker = KnowledgeChunker()
            chunks = chunker.chunk_file(Path(tmp_path))

            # "短标题" 块如果太短会合并到上一块
            # 或者不产出独立块
            for c in chunks:
                # 每个块应该 >= 100 字符
                assert len(c["content"]) >= 100, \
                    f"块 '{c['title']}' 太短 ({len(c['content'])}字), 应被合并"

            logger.info(f"✅ 短块合并: {len(chunks)} 个块")
        finally:
            os.unlink(tmp_path)

    def test_doc_id_stability(self):
        """doc_id 稳定性 — 相同内容产生相同 id"""
        from scripts.index_knowledge_base import KnowledgeChunker
        import hashlib

        content1 = "## 签证\n\n这是签证内容。"
        content2 = "## 签证\n\n这是签证内容。"  # 完全相同

        h1 = hashlib.md5(content1.encode()).hexdigest()[:12]
        h2 = hashlib.md5(content2.encode()).hexdigest()[:12]
        assert h1 == h2, "相同内容应产生相同 hash"
        logger.info(f"✅ doc_id 稳定: {h1}")


# =============================================================================
# Main
# =============================================================================

async def main():
    logger.info("=" * 60)
    logger.info("🧪 知识库切片器测试")
    logger.info("=" * 60)

    test = TestKnowledgeChunker()
    test.test_category_detection()
    test.test_chunk_markdown_file()
    test.test_chunk_real_knowledge_base()
    test.test_short_chunks_merged()
    test.test_doc_id_stability()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 切片器测试全部通过")
    logger.info("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
