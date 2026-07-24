"""三层记忆系统 — 统一编排

架构:
┌──────────────────────────────────────────────────────────────┐
│                    MemoryOrchestrator                         │
│  ┌──────────────┬──────────┬──────────────┬────────────────┐ │
│  │ Short-Term   │ Mid-Term │  Working     │  Long-Term     │ │
│  │ (Redis)      │ (Redis)  │  (Kafka)     │  (MySQL)       │ │
│  │              │          │              │                │ │
│  │ • 会话上下文  │•隔5轮压缩│ • 事件流     │ • 消息归档     │ │
│  │ • 客户热缓存  │•渐进摘要 │ • 异步任务   │ • 客户画像     │ │
│  │ • 频率限制    │•旧会话恢复│ • Agent通信  │ • 行程记录     │ │
│  │ • 工具缓存    │TTL:30天  │ • 分析埋点   │ • RAG反馈      │ │
│  │ TTL:5m-24h   │          │ TTL: 实时    │ TTL: 永久      │ │
│  └──────────────┴──────────┴──────────────┴────────────────┘ │
└──────────────────────────────────────────────────────────────┘

数据流:
  读取: Redis (短时) → miss → MySQL (长时) → 回填 Redis
  写入: Redis (先写) → Kafka (事件) → MySQL (异步持久)
  压缩: 每 5 轮 → LLM 摘要 → Redis mid_term (30天)
"""

from services.memory.orchestrator import MemoryOrchestrator

__all__ = ["MemoryOrchestrator"]
