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

## 四类 Agent 职责

| Agent | 分支 | 职责 | 触发示例 |
|-------|------|------|---------|
| 🏖️ 旅游定制 | `planner` | 根据人数/预算/天气/时间定制行程 | "北京5天2人预算8000" |
| 💬 智能客服 | `service` | FAQ、签证政策、订单查询、投诉转人工 | "签证怎么办理" |
| 💰 销售 | `sales` | 产品推介、报价、签约引导 | "这个多少钱？能优惠吗" |
| 📋 运营 | `operations` | 商家入驻、订单履约、售后工单、退款 | "取消订单，退款" |

## 技术栈

| 层级 | 技术 |
|------|------|
| 编排框架 | LangGraph (StateGraph + Checkpoint) |
| LLM 网关 | DashScope 千问 (qwen-turbo/plus/max) |
| 路由模型 | qwen-turbo (temperature=0.1) |
| 规划模型 | qwen-max (8000 tokens) |
| 向量检索 | Milvus + DashScope text-embedding-v3 |
| 短时记忆 | Redis (会话上下文、客户热缓存) |
| 工作记忆 | Kafka (Agent 事件流、异步任务) |
| 长时记忆 | MySQL (消息归档、客户画像、行程 CRUD) |
| 可观测性 | LangSmith (自动) + Langfuse (自定义 Span) |
| 上下文压缩 | 三层窗口 + LLM 渐进式摘要 |
| 前端 | Vue 3 + Pinia + Vite + marked |
| API | FastAPI + SSE 流式输出 |

## 项目结构

```
tour-agent/
├── main.py                        # FastAPI 入口: /chat + /chat/stream + /health
├── graph/                         # LangGraph 编排层
│   ├── state.py                   # State 定义 (OverallState + Pydantic 模型)
│   ├── builder.py                 # Graph Builder (14 节点 + 条件边)
│   ├── routing.py                 # 条件边路由函数 (5 个)
│   ├── state_helpers.py           # State 安全访问辅助
│   └── nodes/                     # 14 个节点实现
├── agents/                        # 业务 Agent (7 个)
│   ├── base.py                    # Agent 基类 (LLM 调用 + 流式)
│   ├── intent_router.py           # 意图路由器 (qwen-turbo)
│   ├── customer_service.py        # 智能客服
│   ├── sales_agent.py             # 销售 Agent
│   ├── operations_agent.py        # 运营 Agent
│   ├── trip_planner.py            # 旅游定制 Agent (六步生成)
│   ├── intent_scorer.py           # 意向评分 (三路径)
│   └── quote_agent.py             # 报价 Agent (国内/入境自适应)
├── prompts/                       # 6 个 Agent System Prompts
├── tools/                         # 10 个 LangChain Tools
├── services/                      # 基础设施
│   ├── llm_gateway.py             # LLM 网关 (chat + chat_stream)
│   ├── stream_context.py          # 流式上下文 (ContextVar + Queue)
│   ├── context_compressor.py      # 上下文压缩 (三层窗口)
│   ├── observability.py           # Langfuse 追踪
│   ├── vector_store.py            # Milvus 向量存储
│   ├── redis_cache.py             # Redis 缓存
│   ├── kafka_broker.py            # Kafka 消息队列
│   ├── mysql_store.py             # MySQL 持久化
│   ├── checkpoint_store.py        # PostgresSaver
│   └── memory/                    # 三层记忆
│       ├── orchestrator.py        # 编排器 (L1→L2→L3)
│       ├── short_term.py          # 短时记忆 (Redis)
│       ├── working.py             # 工作记忆 (Kafka)
│       └── long_term.py           # 长时记忆 (MySQL)
├── frontend/                      # Vue 3 前端
│   └── src/
│       ├── App.vue                # 根布局 [Sidebar] [Chat] [Detail]
│       ├── api/index.js           # API: fetch + SSE ReadableStream
│       ├── stores/chat.js         # Pinia Store: 消息/会话/流式
│       └── components/
│           ├── StatusBar.vue       # 顶栏: 服务状态/Redis/MySQL 标签
│           ├── HistorySidebar.vue  # 左侧: 对话历史 (280px/44px)
│           ├── ChatPanel.vue       # 中央: 消息列表 + 流式光标
│           ├── DraftCard.vue       # 右侧: 行程草案 Markdown
│           ├── QuoteTable.vue      # 右侧: 报价单分项表格
│           └── SettingsPanel.vue   # 弹窗: 会话/渠道/语言设置
├── tests/                         # 测试
│   ├── test_trip_planner_e2e.py   # 端到端测试
│   ├── test_full_suite.py         # 全功能测试套件
│   └── ...
├── knowledge/                     # 知识库 (20 城市)
├── scripts/                       # 脚本 (知识库索引等)
├── deploy/                        # 部署 (docker-compose, SQL)
├── requirements.txt
├── progress.md                    # 项目进度 (步骤 1-19)
└── .env.example
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/wangri-s/tour-agent.git
cd tour-agent

# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend && npm install && cd ..

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY
```

### 2. 启动基础设施 (Docker)

```bash
# 启动记忆系统 (Redis + Kafka + MySQL + Milvus)
docker compose up -d etcd minio milvus redis kafka mysql

# 索引知识库到 Milvus
python scripts/index_knowledge_base.py
```

### 3. 启动服务

```bash
# 终端 1: 启动后端 (端口 8002)
python main.py

# 终端 2: 启动前端 (端口 3000)
cd frontend && npx vite --host
```

### 4. 测试

```bash
# 健康检查
curl http://127.0.0.1:8002/health

# 非流式对话
curl -X POST http://127.0.0.1:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","customer_id":"c1","channel":"web","message":"北京5天2人预算8000","language":"zh"}'

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

**请求体：**
```json
{
  "session_id": "sess-001",
  "customer_id": "c-001",
  "channel": "web",
  "message": "北京5天游2人预算8000",
  "language": "zh"
}
```

**响应体：**
```json
{
  "reply": "为您定制了行程...",
  "draft": { "version": 1, "itinerary_md": "...", "estimated_cost": 4935, ... },
  "quote": { "flights": 740, "hotels": 2467, "total": 4935, ... },
  "branch": "planner",
  "need_human": false
}
```

### POST /chat/stream
流式对话，SSE 事件流。

**SSE 事件类型：**

| 事件 | 说明 | 数据 |
|------|------|------|
| `token` | LLM 逐字生成 | `{"text": "北"}` |
| `branch` | 路由分支 | `{"branch": "planner"}` |
| `draft` | 行程草案 | `{"version": 1, "itinerary_md": "...", "estimated_cost": 4935, ...}` |
| `quote` | 报价单 | `{"flights": 740, "hotels": 2467, "total": 4935, ...}` |
| `reply` | 非流式兜底 | `{"text": "完整回复"}` |
| `done` | 流结束 | `{"status": "ok"}` |
| `error` | 错误 | `{"error": "..."}` |

### GET /health
健康检查，返回服务状态、功能开关、记忆层连接状态。

## 意图路由规则

8 条优先级规则链，命中即停：

1. 投诉/情绪激动/要求转人工 → `service` + `need_human=true`
2. 商家/商户身份 → `operations`
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
                                         agents 推送 ("token", text)
```

## 功能验证

```
全功能测试: 21 tests
  1. Health Check ................ 5/5 PASS
  2. Intent Routing .............. 11/11 PASS
  3. Trip Draft Generation ....... 1/1 PASS (cost=¥4,935)
  4. Domestic Trip ............... 1/1 PASS (🚄高铁/动车)
  5. Streaming SSE ............... 2/2 PASS (token-level)
  6. Quote Generation ............ 1/1 PASS (total=¥2,974)
```

## License

MIT
