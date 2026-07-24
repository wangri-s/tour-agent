# tour-agent

基于 LangGraph 的入境定制游 Multi-Agent 智能平台。

## 架构概览

```
用户消息 → input_guard → session_context → intent_router
                                                ↓
                              ┌─────────────────┼─────────────────┬─────────────────┐
                              ↓                 ↓                  ↓                  ↓
                      customer_service    sales_agent      operations_agent    trip_planner
                              ↓                 ↓                  ↓                  ↓
                        after_service    intent_score      operations_sync    requirements
                              ↓                 ↓                                  ↓
                        END / human    quote / ops                          trip_planner
                                         / human                                  ↓
                                                                           intent_scorer
                                                                                 ↓
                                                                         revision_decision
                                                                         ↓       ↓       ↓
                                                                     revise   accept  give_up
                                                                                 ↓
                                                                           quote_agent
                                                                                 ↓
                                                                         operations_sync
                                                                                 ↓
                                                                                END
```

## 四类 Agent

| Agent | 分支 | 职责 | 触发示例 |
|-------|------|------|---------|
| 🏖️ 旅游定制 | `planner` | 根据人数/预算/天气/时间定制行程 | "北京5天2人预算8000" |
| 💬 智能客服 | `service` | FAQ、签证政策、订单查询、投诉转人工 | "签证怎么办理" |
| 💰 销售 | `sales` | 产品推介、报价、签约引导 | "这个多少钱？能优惠吗" |
| 📋 运营 | `operations` | 商家入驻、订单履约、售后工单、退款 | "取消订单，退款" |

## 技术栈

| 层级 | 技术 |
|------|------|
| 编排框架 | LangGraph (StateGraph + PostgresSaver) |
| LLM 网关 | DashScope 千问 (qwen-turbo/plus/max) |
| 路由模型 | qwen-turbo (temperature=0.1, 12 few-shot) |
| 规划模型 | qwen-max (8000 tokens, 六步生成) |
| 向量检索 | Milvus + DashScope text-embedding-v3 (1024维) |
| 短时记忆 | Redis (会话上下文 TTL 30min, 客户热缓存 24h) |
| 工作记忆 | Kafka (7 Topic, 12 事件类型, 保留 7 天) |
| 长时记忆 | MySQL (6 表: 消息/画像/行程/事件/反馈/知识库) |
| Checkpoint | **PostgresSaver** (跨重启恢复, 多实例共享) |
| 可观测性 | LangSmith (自动) + Langfuse (自定义 Span) |
| 上下文压缩 | 三层窗口 (近期10轮/中期30轮/长期) + LLM 渐进式摘要 |
| 前端 | Vue 3 + Pinia + Vite + marked (暗色主题) |
| API | FastAPI + **SSE 流式输出** |

## 项目结构

```
tour-agent/
├── main.py                        # FastAPI: /chat + /chat/stream + /health
├── graph/                         # LangGraph 编排层
│   ├── state.py                   # State 定义 (MessagesState + Pydantic)
│   ├── builder.py                 # 14 节点 + 条件边组装
│   ├── routing.py                 # 5 个条件边路由函数
│   ├── state_helpers.py           # State 安全访问辅助
│   └── nodes/                     # 14 个节点
├── agents/                        # 7 个 Agent
│   ├── base.py                    # 基类 (call_llm + call_llm_stream)
│   ├── intent_router.py           # 意图路由 (qwen-turbo)
│   ├── trip_planner.py            # 旅游定制 (六步 + 预算约束)
│   ├── customer_service.py        # 智能客服
│   ├── sales_agent.py             # 销售
│   ├── operations_agent.py        # 运营
│   ├── intent_scorer.py           # 意向评分 (三路径)
│   └── quote_agent.py             # 报价 (国内/入境自适应)
├── prompts/                       # 6 个 Agent System Prompt
├── tools/                         # 10 个 LangChain Tool
├── services/                      # 基础设施
│   ├── llm_gateway.py             # LLM 网关 (chat + chat_stream)
│   ├── stream_context.py          # 流式上下文 (ContextVar + Queue)
│   ├── context_compressor.py      # 上下文压缩 (三层窗口)
│   ├── checkpoint_store.py        # PostgresSaver
│   ├── observability.py           # Langfuse 追踪
│   ├── vector_store.py            # Milvus 向量存储
│   ├── redis_cache.py             # Redis 缓存
│   ├── kafka_broker.py            # Kafka 消息队列
│   ├── mysql_store.py             # MySQL 持久化
│   └── memory/                    # 三层记忆
│       ├── orchestrator.py        # 编排器 (L1→L2→L3 读写策略)
│       ├── short_term.py          # 短时记忆 (Redis)
│       ├── working.py             # 工作记忆 (Kafka)
│       └── long_term.py           # 长时记忆 (MySQL)
├── frontend/                      # Vue 3 前端
│   └── src/
│       ├── App.vue                # 根布局 [Sidebar] [Chat] [Detail]
│       ├── api/index.js           # fetch + SSE ReadableStream
│       ├── stores/chat.js         # Pinia: 消息/会话/流式/历史
│       └── components/
│           ├── StatusBar.vue       # 服务状态 + 记忆层标签
│           ├── HistorySidebar.vue  # 对话历史 (280px/44px)
│           ├── ChatPanel.vue       # 消息列表 + 流式光标
│           ├── DraftCard.vue       # 行程草案 Markdown
│           ├── QuoteTable.vue      # 报价单 + 进度条
│           └── SettingsPanel.vue   # 会话/渠道/语言设置
├── tests/                         # 测试
│   ├── test_trip_planner_e2e.py   # 端到端
│   └── test_full_suite.py         # 全功能套件 (21 项)
├── knowledge/                     # 知识库 (20 城市)
├── deploy/                        # init.sql
├── docker-compose.yml             # 7 个基础设施容器
├── requirements.txt
├── progress.md                    # 项目进度 (步骤 1-21)
└── .env.example
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+
- Docker Desktop (Windows/Mac) 或 Docker Engine (Linux)

### 2. 克隆项目

```bash
git clone https://github.com/wangri-s/tour-agent.git
cd tour-agent
```

### 3. 安装依赖

```bash
# Python 后端
pip install -r requirements.txt

# 前端
cd frontend && npm install && cd ..
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少配置：

```ini
# 必填: DashScope API Key (阿里云千问)
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# 可选: LangSmith 追踪
LANGCHAIN_API_KEY=lsv2_xxxxxxxx
```

### 5. 启动基础设施 (Docker)

```bash
# 一键启动全部 7 个服务
docker compose up -d

# 查看状态
docker compose ps
```

端口映射：

| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | `:5432` | LangGraph Checkpoint 持久化 |
| Redis | `:6379` | 短时记忆 (会话上下文) |
| Kafka | `:29092` | 工作记忆 (Agent 事件流) |
| MySQL | `:3307` | 长时记忆 (消息归档) |
| Milvus | `:19530` | 向量检索 (RAG) |
| MinIO | `:9000` | Milvus 对象存储 |
| etcd | `:2379` | Milvus 元数据 |

### 6. 索引知识库 (首次)

```bash
python scripts/index_knowledge_base.py
```

> 将 `knowledge/china_travel_kb.md` 中的 20 个城市信息向量化写入 Milvus。

### 7. 启动应用

```bash
# 终端 1: 后端 (端口 8002)
python main.py

# 终端 2: 前端 (端口 3000)
cd frontend && npx vite --host
```

打开浏览器访问 `http://localhost:3000`。

### 8. 验证

```bash
# 健康检查
curl http://127.0.0.1:8002/health | python -m json.tool

# 非流式对话
curl -X POST http://127.0.0.1:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","customer_id":"c1","channel":"web","message":"你好","language":"zh"}'

# 流式对话 (SSE)
curl -N -X POST http://127.0.0.1:8002/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s2","customer_id":"c1","channel":"web","message":"成都3天美食推荐","language":"zh"}'

# 全功能测试
python tests/test_full_suite.py
```

## API 接口

### POST /chat
非流式对话，返回 JSON。

**请求：**
```json
{
  "session_id": "sess-001",
  "customer_id": "c-001",
  "channel": "web",
  "message": "北京5天游2人预算8000",
  "language": "zh"
}
```

**响应：**
```json
{
  "reply": "为您定制了行程 ✨\n💰 预估人均费用：¥4,935\n...",
  "draft": { "version": 1, "itinerary_md": "...", "estimated_cost": 4935 },
  "quote": { "flights": 740, "hotels": 2467, "total": 4935 },
  "branch": "planner",
  "need_human": false
}
```

### POST /chat/stream
流式对话，SSE 事件流。

| 事件 | 说明 |
|------|------|
| `token` | LLM 逐字生成 |
| `branch` | 路由分支 (planner/service/sales/operations) |
| `draft` | 行程草案 JSON |
| `quote` | 报价单 JSON |
| `reply` | 非流式兜底回复 |
| `done` | 流结束 |
| `error` | 错误信息 |

### GET /health
返回服务状态、功能开关、记忆层连接状态。

## 意图路由规则

8 条优先级规则链 (命中即停)：

1. 投诉/情绪激动 → `service` + `need_human=true`
2. 商家/商户 → `operations`
3. 含取消/修改/退款动作词 → `operations`
4. 含预订/付款/多少钱/优惠 → `sales`
5. 含想去/推荐/攻略/景点 → `planner`
6. 仅查询订单状态 → `service`
7. 政策/签证/FAQ → `service`
8. 兜底 → `service`

## 流式输出架构

```
浏览器 ←─ SSE (text/event-stream) ──→ /chat/stream
                                         │
                                    asyncio.Queue (ContextVar)
                                         │
                              ┌──────────┴──────────┐
                         event_generator()    run_graph() 后台
                              (SSE 推送)      (LangGraph.ainvoke)
                                                   │
                                         agents → ("token", text)
```

## 预算约束

双层兜底确保行程费用不超用户预算：

1. **Prompt 层**：每项分硬上限（酒店≤40%/天、餐饮≤15%/天…），LLM 按具体数字规划
2. **后处理层**：`estimated_cost > budget * 1.2` → 强制截断到 `budget * 0.95`

验证：4 档预算 (¥2k/3k/5k/8k) 全部控制在 5% 误差内。

## 已知问题

- Windows 保留端口段 `9026-9125`，Kafka 和 Milvus metrics 需使用非标准端口
- 前端需刷新页面才能看到旧会话的历史消息（localStorage 已存，但需重新挂载）

## License

MIT
