# tour-agent

基于 LangGraph 的入境定制游 Multi-Agent 智能平台。支持多旅行社 Prompt 版本管理、实时天气查询、流式对话、RAG 语义检索、三层记忆系统。

## 架构概览

```
用户消息 → input_guard → session_context → query_rewrite → intent_router
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

## 功能特性

### 🏖️ 四类 Agent
| Agent | 分支 | 职责 | 触发示例 |
|-------|------|------|---------|
| 旅游定制 | `planner` | 六步生成行程 + 预算约束 + 天气感知 | "北京5天2人预算8000" |
| 智能客服 | `service` | FAQ、签证政策、订单查询、投诉转人工 | "签证怎么办理" |
| 销售 | `sales` | 产品推介、报价、签约引导 | "这个多少钱？能优惠吗" |
| 运营 | `operations` | 商家入驻、订单履约、售后工单、退款 | "取消订单，退款" |

### 🌤️ 实时天气 (MCP Server)
- 基于 **Open-Meteo** 免费 API，无需 API Key，10,000次/天
- FastMCP 协议，4 个工具：当前天气、7天预报、行程天气、城市搜索
- 45 个城市内置坐标 (30中国 + 15国际) + Geocoding 在线查找
- 智能穿衣建议 + 出行影响评估 (WMO 天气代码)

### 🏢 多旅行社 Prompt 管理
- 3 家预设旅行社：标准版 / 奢华版 / 经济版
- **YAML 一行切换默认旅行社**：`settings.default_agency`
- 前端下拉框切换 + localStorage 持久化
- 每家旅行社独立品牌身份，LLM 准确回答"我是XX的旅行顾问"
- 三层身份注入：System Prompt + 消息级注入 + 回复后处理正则兜底

### ✏️ 查询改写
- 双层策略：规则表 (0ms, 20常见错别字 + 40拼音城市) + LLM 纠错 (qwen-turbo, 3s超时)
- "背景"→"北京", "洗安"→"西安", "hangzhou"→"杭州"

### 📋 上下文保持
- 同会话内 Agent 切换不丢上下文 (planner→service→planner)
- 非行程关键词排除列表，防止身份问题误入 planner
- 历史需求恢复：正则从历史消息中提取 TripNeed

### 🧠 三层记忆 + 中期摘要
- **短期** (Redis)：会话上下文 30min TTL, 客户热缓存 24h
- **中期** (Redis+MySQL)：每 5 轮触发 LLM 摘要压缩，过期从 MySQL 恢复
- **长期** (MySQL)：消息归档、客户画像、行程 CRUD
- **工作记忆** (Kafka)：12 种事件类型，6 个 Topic，异步持久化

### 📦 统一 YAML 配置
- **单一配置文件** `config/tour_agent.yaml` (~480行)
- 15 个配置段：LLM、Embedding、Milvus、检索、分块、缓存、限流、天气…
- `${ENV_VAR:-default}` 环境变量语法
- 点号路径访问：`config.get("milvus.search_params.nprobe")`
- `POST /admin/prompts/reload` 热加载，无需重启

## 技术栈

| 层级 | 技术 |
|------|------|
| 编排框架 | LangGraph (StateGraph + 14节点管线) |
| LLM 网关 | DashScope 千问 (qwen-turbo/plus/max), OpenAI 兼容协议 |
| 路由模型 | qwen-turbo (temperature=0.1, 12 few-shot) |
| 规划模型 | qwen-max (8K context, 六步生成 + budget约束) |
| 向量检索 | Milvus 2.4 + DashScope text-embedding-v3 (1024维) |
| 短时记忆 | Redis (9项 TTL 可配, hiredis 解析器) |
| 工作记忆 | Kafka (6 Topic, 12 事件类型, KRaft 模式) |
| 长时记忆 | MySQL 8.0 (6 表, aiomysql 连接池) |
| Checkpoint | MemorySaver (开发) / PostgresSaver (生产, Linux) |
| 天气服务 | Open-Meteo (免费, MCP 协议, FastMCP) |
| 上下文压缩 | 三层窗口 (近期10轮/中期30轮/长期) + LLM 渐进式摘要 |
| 可观测性 | LangSmith (自动) + Langfuse (自定义 Span) |
| 前端 | Vue 3 + Pinia + Vite + marked (暗色主题) |
| API | FastAPI + **SSE 流式输出** |

## 项目结构

```
tour-agent/
├── main.py                          # FastAPI: /chat + /chat/stream + /admin + /health
├── config/
│   └── tour_agent.yaml              # 统一配置 (15段, ~480行, 热加载)
├── graph/                           # LangGraph 编排层
│   ├── state.py                     # State 定义 (MessagesState + Pydantic)
│   ├── builder.py                   # 14 节点 + 条件边装配
│   ├── routing.py                   # 5 个条件边路由函数
│   └── nodes/                       # 14 个节点 (含 query_rewrite)
├── agents/                          # 7 个 Agent
│   ├── base.py                      # 基类 (LLM调用 + 流式 + 身份注入)
│   ├── intent_router.py             # 意图路由 (qwen-turbo + 关键词预判)
│   ├── trip_planner.py              # 旅游定制 (六步 + 预算约束 + 复述检测)
│   ├── customer_service.py          # 智能客服
│   ├── sales_agent.py               # 销售
│   ├── operations_agent.py          # 运营
│   ├── intent_scorer.py             # 意向评分 (三路径)
│   └── quote_agent.py               # 报价 (国内/入境自适应)
├── prompts/                         # Agent System Prompt + 版本管理
├── tools/                           # 12 个 LangChain Tool
│   ├── rag_search.py                # RAG 语义检索
│   ├── mcp_weather.py               # MCP 天气查询
│   └── ...
├── services/                        # 基础设施
│   ├── config_loader.py             # 统一配置加载器 (单例, 热加载)
│   ├── prompt_manager.py            # Prompt 版本管理 + 品牌注入
│   ├── llm_gateway.py               # LLM 网关 (chat + chat_stream + 工具调用)
│   ├── stream_context.py            # 流式上下文 (ContextVar + Queue)
│   ├── context_compressor.py        # 上下文压缩 (可配阈值)
│   ├── checkpoint_store.py          # PostgresSaver (Windows降级MemorySaver)
│   ├── observability.py             # Langfuse 追踪
│   ├── vector_store.py              # Milvus + Embedding (可配参数)
│   ├── redis_cache.py               # Redis 缓存 (TTL可配)
│   ├── kafka_broker.py              # Kafka 消息队列
│   ├── mysql_store.py               # MySQL 持久化
│   └── memory/                      # 三层记忆 + 中期摘要
│       ├── orchestrator.py          # 编排器 (L1→L2→L3 读写策略)
│       ├── short_term.py            # 短时记忆 (Redis)
│       ├── mid_term.py              # 中期摘要 (每5轮压缩)
│       ├── working.py               # 工作记忆 (Kafka)
│       └── long_term.py             # 长时记忆 (MySQL)
├── mcp_servers/                     # MCP 服务器
│   └── weather/                     # Open-Meteo 天气 MCP
│       ├── server.py                # FastMCP (4 tools)
│       ├── open_meteo.py            # API 客户端
│       ├── city_coords.py           # 45城市坐标 + 别名
│       └── weather_codes.py         # WMO 天气代码
├── frontend/                        # Vue 3 前端
│   └── src/
│       ├── App.vue                  # 根布局 [Sidebar] [Chat] [Detail]
│       ├── api/index.js             # fetch + SSE ReadableStream + agency API
│       ├── stores/chat.js           # Pinia: 消息/会话/流式/历史/旅行社
│       └── components/
│           ├── StatusBar.vue         # 服务状态 + 记忆层标签
│           ├── HistorySidebar.vue    # 对话历史 (280px/44px)
│           ├── ChatPanel.vue         # 消息列表 + 流式光标
│           ├── DraftCard.vue         # 行程草案 Markdown
│           ├── QuoteTable.vue        # 报价单 + 进度条
│           └── SettingsPanel.vue     # 会话/旅行社/渠道/语言设置
├── scripts/
│   └── index_knowledge_base.py      # 知识库向量化索引
├── knowledge/
│   └── china_travel_kb.md           # 20 城市知识库
├── deploy/
│   └── init.sql                     # MySQL 建表
├── docker-compose.yml               # 7 个基础设施容器
├── requirements.txt
├── progress.md                      # 项目进度 (步骤 1-33)
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

### 4. 配置

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

> 其他所有配置在 `config/tour_agent.yaml` 中，支持 `${ENV_VAR:-default}` 语法读取环境变量。

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

# 查看旅行社配置
curl http://127.0.0.1:8002/admin/prompts | python -m json.tool

# 非流式对话 (指定旅行社)
curl -X POST http://127.0.0.1:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","customer_id":"c1","agency_id":"luxury_travel","channel":"web","message":"成都3天2人","language":"zh"}'

# 流式对话 (SSE)
curl -N -X POST http://127.0.0.1:8002/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s2","customer_id":"c1","agency_id":"budget_travel","channel":"web","message":"西安2天美食推荐","language":"zh"}'
```

## API 接口

### POST /chat
非流式对话，返回 JSON。

**请求：**
```json
{
  "session_id": "sess-001",
  "customer_id": "c-001",
  "agency_id": "luxury_travel",
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
| `token` | LLM 逐字生成 (实时推送) |
| `branch` | 路由分支 (planner/service/sales/operations) |
| `draft` | 行程草案 JSON |
| `quote` | 报价单 JSON |
| `reply` | 非流式兜底回复 |
| `done` | 流结束标记 |
| `error` | 错误信息 |

### GET /health
返回服务状态、功能开关、记忆层连接状态、RAG 状态。

### GET /admin/prompts
列出所有旅行社及 prompt 版本。

### GET /admin/prompts/{agency_id}
查看指定旅行社的完整 prompt 文本。

### POST /admin/prompts/reload
热加载配置（修改 `config/tour_agent.yaml` 后调用，无需重启）。

## 配置指南

### 切换默认旅行社

编辑 `config/tour_agent.yaml`：

```yaml
settings:
  default_agency: luxury_travel   # default | luxury_travel | budget_travel
```

热加载生效：

```bash
curl -X POST http://127.0.0.1:8002/admin/prompts/reload
```

### 新增旅行社

在 `config/tour_agent.yaml` 的 `agencies:` 段添加：

```yaml
agencies:
  my_travel:
    agency_id: my_travel
    brand_name: 星辰定制旅行社
    prompt_versions:
      trip_planner: v2_luxury    # 选已有版本
    output_style:
      tone: luxury
      include_brand_header: true
      brand_header: "✨ 星辰定制 · 专属旅行管家"
```

### 修改 Prompt

直接在 `prompts.trip_planner.v1_standard.text:` 下编辑文本，保存后热加载即可。

### 修改 RAG 检索参数

```yaml
retrieval:
  top_k: 5                # 返回结果数
  score_threshold: 0.3    # 相似度阈值

milvus:
  search_params:
    nprobe: 16            # 搜索精度 (越大越精确越慢)
```

## 意图路由规则

8 条优先级规则链 (命中即停)：

1. 投诉/情绪激动 → `service` + `need_human=true`
2. 参数补全 OR 行程上下文 → `planner` (跳过LLM)
3. 非行程关键词 (旅行社/你是谁/退款…) → 排除 planner
4. 商家/商户 → `operations`
5. 含取消/修改/退款动作词 → `operations`
6. 含预订/付款/多少钱/优惠 → `sales`
7. 含想去/推荐/攻略/景点 → `planner`
8. 兜底 → `service`

## 预算约束

双层兜底确保行程费用不超用户预算：

1. **Prompt 层**：每项分硬上限（酒店≤40%/天、餐饮≤15%/天…），LLM 按具体数字规划
2. **后处理层**：`estimated_cost > budget * 1.2` → 强制截断到 `budget * 0.95`

验证：4 档预算 (¥2k/3k/5k/8k) 全部控制在 5% 误差内。

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

## 全功能测试

```bash
# 覆盖 10 项核心功能
# 健康检查 / Admin API / 3家旅行社身份 / 行程规划 / 纠错 / 跨Agent保持 / 流式
```

最近测试结果 (2026-07-25)：

| # | 测试项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | Health Check | ✅ | Redis/Kafka/MySQL 全在线 |
| 2 | Admin API | ✅ | 3家旅行社正确列出 |
| 3-5 | 身份识别 | ✅ | 3家旅行社各返回正确品牌名 |
| 6-7 | 行程规划 | ✅ | 奢华版+经济版均正常生成 |
| 8 | 纠错改写 | ✅ | "背景"→"北京" |
| 9 | 跨Agent保持 | ✅ | planner→service→planner 3326字复述 |
| 10 | 流式 SSE | ✅ | token 逐字推送正常 |

## 已知问题

- Windows 保留端口段 `9026-9125`，Kafka 和 Milvus metrics 需使用非标准端口
- Windows `ProactorEventLoop` 不兼容 psycopg async → 自动降级 MemorySaver (Linux 自动启用 PostgresSaver)
- 前端刷新后需重新挂载历史消息 (localStorage 已存)

## License

MIT
