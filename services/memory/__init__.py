"""三层记忆系统 — 统一编排

架构:
┌─────────────────────────────────────────────────────────┐
│                    MemoryOrchestrator                    │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │ Short-Term   │  Working     │  Long-Term           │ │
│  │ (Redis)      │  (Kafka)     │  (MySQL)             │ │
│  │              │              │                      │ │
│  │ • 会话上下文  │ • 事件流     │ • 消息归档           │ │
│  │ • 客户热缓存  │ • 异步任务   │ • 客户画像           │ │
│  │ • 频率限制    │ • Agent通信  │ • 行程记录           │ │
│  │ • 工具缓存    │ • 分析埋点   │ • RAG反馈            │ │
│  │ TTL: 5m-24h  │ TTL: 实时    │ TTL: 永久            │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
└─────────────────────────────────────────────────────────┘

数据流:
  读取: Redis (短时) → miss → MySQL (长时) → 回填 Redis
  写入: Redis (先写) → Kafka (事件) → MySQL (异步持久)
"""

from services.memory.orchestrator import MemoryOrchestrator

__all__ = ["MemoryOrchestrator"]
