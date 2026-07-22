# 实现方案详解

本文档记录项目每一步的实现方案、技术选型及使用的功能特性。

---

## 1. 仓库与项目管理

### 1.1 仓库命名

- **方案**：选用 `tour-agent`，简洁、语义清晰，tour + agent 直指「旅游智能体」
- **功能**：GitHub 空仓库初始化，`git clone` 到本地开发目录

### 1.2 版本控制

- **方案**：Git 单分支 `main`，首 commit 包含完整骨架
- **功能**：`.gitignore` 排除 `__pycache__`、`.env`、IDE 配置、checkpoint 文件

---

## 2. LangGraph 编排层 (`graph/`)

### 2.1 State 设计 (`state.py`)

- **方案**：基于 `langgraph.graph.MessagesState` 扩展为 `OverallState`
- **功能特性**：
  - **Pydantic v2 `BaseModel`**：`TripNeed`、`TripDraft`、`Quote` 用 Pydantic 建模，自带类型校验
  - **枚举类 `StrEnum`**：`Channel`、`Branch`、`IntentLevel`、`NextAction` 用枚举约束状态空间
  - **`TypedDict`**：`PartialState` 用作节点返回值类型标注，节点只需返回部分字段
  - **`add_messages` Reducer**：`messages` 字段用 LangGraph 内置 reducer 自动追加消息而非覆盖
  - **业务方法**：`TripNeed.is_complete()` 五必填校验，`missing_fields()` 返回缺失字段名

### 2.2 Graph Builder (`builder.py`)

- **方案**：`StateGraph(OverallState)` 构建有向图，13 节点 + 条件边
- **功能特性**：
  - **`add_node()`**：注册 13 个节点函数
  - **`add_edge()`**：固定边（线性链路）
  - **`add_conditional_edges()`**：5 组条件边，根据 State 动态决定下一个节点
  - **`set_entry_point()`**：入口设为 `input_guard`
  - **`MemorySaver` Checkpointer**：开发期用内存 checkpoint，支持会话中断恢复
  - **`compile()`**：返回编译后的 `CompiledStateGraph`

### 2.3 条件边路由 (`routing.py`)

- **方案**：5 个纯函数，接收 `OverallState`，返回目标节点名字符串
- **功能特性**：
  - **`route_after_intent`**：意图路由分发到四类分支或转人工
  - **`route_after_service`**：客服完成 → END / human / 重新分类
  - **`route_after_sales`**：销售完成 → quote(high) / ops(mid/low) / human
  - **`route_requirements`**：必填检查 → trip_planner 追问 / intent_scorer 评分
  - **`route_revision`**：修订决策 → revision_loop / quote_agent / ops / human

### 2.4 13 个节点实现 (`graph/nodes/`)

每个节点 = 一个 `async def` 函数，接收 `OverallState`，返回 `PartialState`。

| 节点 | 实现方案 | 关键功能 |
|------|---------|---------|
| `input_guard` | 正则脱敏 + 长度截断 | `re.sub()` PII 掩码，4000 字硬截断 |
| `session_context` | UUID 兜底 + 语言默认值 | `uuid.uuid4()` 生成 session_id |
| `intent_router` | 关键词拦截 + 模型调用降级 | 投诉/退款等关键词直接转人工；GPT-4o-mini 做四分类 |
| `customer_service` | 委托 `CustomerServiceAgent` | 调用 Agent → 返回 reply + need_human |
| `sales_agent` | 委托 `SalesAgent` | 调用 Agent → 返回 reply + intent_level |
| `operations_agent` | 委托 `OperationsAgent` | 调用 Agent → 返回 reply |
| `trip_planner` | 委托 `TripPlannerAgent` | 首次生成 version+=1，追问不增加版本 |
| `intent_scorer` | 委托 `IntentScorerAgent` | 独立评分 → next_action (revise/accept/give_up) |
| `revision_loop` | 纯计数器 | `revision_count += 1`，硬上限由路由控制 |
| `quote_agent` | 委托 `QuoteAgent` | 生成结构化 Quote |
| `human_handoff` | 字符串模板拼交接摘要 | 生成客户画像 + 草案状态 + 跟进建议 |
| `operations_sync` | `try/except` 非阻断写入 | 调用 `update_crm` + `send_capi`，失败不抛异常 |

---

## 3. Agent 业务层 (`agents/`)

### 3.1 BaseAgent 抽象 (`base.py`)

- **方案**：ABC 抽象基类，封装 LLM 调用
- **功能特性**：
  - **`abstractmethod system_prompt()`**：子类必须实现，返回该 Agent 的 system prompt
  - **`call_llm()`**：封装 `LLMGateway.chat()` 调用
  - 预留 tools 绑定与结构化输出扩展点

### 3.2 IntentRouterAgent

- **方案**：轻量模型做结构化输出，GPT-4o-mini / 本地 7B
- **功能特性**：
  - **`json.loads()` 解析**：LLM 输出四类概率 + need_human
  - **兜底逻辑**：解析失败默认进入 `service`

### 3.3 CustomerServiceAgent

- **方案**：多语言客服，绑定 `search_faq` + `check_handoff` 工具
- **功能特性**：
  - 取最近 10 轮消息为上下文
  - 支持 FAQ 检索与转人工评估

### 3.4 SalesAgent

- **方案**：主动销售引导，绑定 `quote_price` + `query_inventory`
- **功能特性**：
  - **`_score_intent()`**：关键词评分 → high/mid/low
  - high 关键词：签约、支付、定金、sign、pay、deposit
  - mid 关键词：考虑、再看看、优惠、consider、discount

### 3.5 OperationsAgent

- **方案**：后端运营处理，绑定 `update_crm` + `send_capi`
- **功能特性**：
  - 完成运营任务后强制调 `update_crm`

### 3.6 TripPlannerAgent

- **方案**：行程定制核心 Agent，绑定天气/日历/库存三个工具
- **功能特性**：
  - **`plan()` 方法**：组装 need + draft 上下文发给 LLM
  - **`_parse_draft()`**：从 LLM 输出解析为 `TripDraft`
  - 生成约束（交通 ≤2.5h、先查天气）由 prompt 控制

### 3.7 IntentScorerAgent

- **方案**：独立评分节点，不绑定工具
- **功能特性**：
  - 输入：need + draft + revision_count + 最后消息
  - 输出：intent_level + next_action + need_human
  - JSON 解析 + 默认 mid/give_up 兜底

### 3.8 QuoteAgent

- **方案**：报价生成，绑定 `quote_price` 工具
- **功能特性**：
  - **`_parse_quote()`**：从 LLM 输出中提取 JSON 构造 `Quote`
  - 解析失败返回 None，不阻断流程

---

## 4. Tools 工具层 (`tools/`)

全部 8 个工具用 **LangChain `@tool` 装饰器**封装，方便后续切 MCP 协议。

| 工具 | 实现方案 | 数据来源 |
|------|---------|---------|
| `search_faq` | 内存字典 + 模糊匹配 | MVP 硬编码，Phase 2 换 Milvus/pgvector |
| `check_handoff` | 关键词 + 轮次双维度评分 | 本地逻辑，无外部依赖 |
| `get_weather` | Mock 返回固定 JSON | Phase 2 换和风天气 / OpenWeatherMap |
| `query_calendar` | `datetime.weekday()` 判断周末 + 固定节假日字典 | Phase 2 换 chinese-calendar 库 |
| `query_inventory` | Mock 酒店 / 门票 / 车辆数据 | Phase 2 接 PMS / 供应商 API |
| `quote_price` | 按预算档位分三段计价 | MVP 简易算法，Phase 2 接真实报价引擎 |
| `update_crm` | `logging.info()` 占位 + JSON 序列化 | Phase 3 接 Salesforce / HubSpot |
| `send_capi` | 渠道映射 + `logging.info()` 占位 | Phase 3 接 Meta CAPI / Google Ads / TikTok |

### 工具设计原则

- **`async def`**：全部异步，兼容 LangGraph 的 async 节点
- **类型注解**：每个参数有明确类型，LangChain 自动生成 schema
- **占位实现**：MVP 阶段返回 mock 数据，接口不变，后续只替换内部逻辑
- **非阻断**：`update_crm` 和 `send_capi` 在 `operations_sync` 中用 `try/except` 包裹

---

## 5. Prompts 提示词层 (`prompts/`)

- **方案**：每个 Agent 一份独立的 system prompt，存为字符串常量
- **设计原则**：
  - 中英双语指令（适配入境游场景）
  - 结构化输出要求（JSON 格式）
  - 明确的工具使用指引
  - 语气约束（warm / professional / patient）

---

## 6. Services 服务层 (`services/`)

### 6.1 LLMGateway

- **方案**：OpenAI 兼容 API 网关
- **功能特性**：
  - **`AsyncOpenAI` SDK**：异步调用，支持 `gpt-4o` / `gpt-4o-mini`
  - **`_format_tools()`**：LangChain Tool → OpenAI function schema 转换
  - **环境变量配置**：`LLM_MODEL`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`
  - **错误兜底**：异常时返回 `[LLM Error]` 字符串，不抛异常
  - 预留 Langfuse callback 扩展点

### 6.2 Database

- **方案**：PostgreSQL 抽象层，MVP 占位
- **功能特性**：
  - `connect()` / `close()` — 连接池管理
  - `execute()` / `fetch()` — SQL 执行与查询
  - Phase 3 接入 asyncpg + pgvector

### 6.3 Cache

- **方案**：Redis 缓存抽象，MVP 占位
- **功能特性**：
  - `get()` / `set()` / `delete()` — 基础 KV 操作
  - `get_customer_profile()` / `set_customer_profile()` — 客户画像专用接口
  - 默认 TTL 3600s，客户画像 30 天

### 6.4 MessageQueue

- **方案**：消息队列抽象，MVP 占位
- **功能特性**：
  - `publish()` / `subscribe()` — 发布订阅
  - `enqueue()` — 异步任务入队
  - 用途：异步 CRM 写入、CAPI 批量回传、长任务

---

## 7. API 入口 (`main.py`)

### 7.1 框架选型

- **方案**：FastAPI + Uvicorn
- **功能特性**：
  - **`lifespan` 上下文**：启动时编译 Graph，关闭时清理
  - **CORS 中间件**：开发期全开
  - **Pydantic v2 请求/响应模型**：`ChatRequest` + `ChatResponse`
  - **`/chat` 接口**：接收 5 个必填参数，调用 `graph.ainvoke()`
  - **`thread_id`**：复用 `session_id`，Checkpoint 自动关联历史
  - **`/health` 健康检查**

### 7.2 请求流程

```
POST /chat {session_id, customer_id, channel, message, language}
  → 构造 OverallState + HumanMessage
  → graph.ainvoke(state, config={"configurable": {"thread_id": session_id}})
  → 提取 final_reply / draft / quote / branch / need_human
  → 返回 ChatResponse
```

---

## 8. 测试 (`tests/`)

### 8.1 测试框架

- **方案**：pytest + pytest-asyncio
- **功能特性**：
  - `TestTripNeed`：4 个用例覆盖完整/不完整/部分必填场景
  - `TestRouting`：10 个用例覆盖 5 组条件边所有分支
  - `TestGraphBuild`：验证 Graph 编译 + 关键节点存在

### 8.2 测试重点

- `is_complete()` 逻辑
- `missing_fields()` 返回正确字段名
- 路由在 human / high / mid / low / revise / accept / give_up 下的正确跳转
- 修订次数超限拦截

---

## 9. 关键设计决策总结

| 决策点 | 方案 | 原因 |
|--------|------|------|
| State 基类 | `MessagesState` | LangGraph 内置，自带消息 reducer |
| 数据模型 | Pydantic v2 `BaseModel` | 类型安全、序列化、校验 |
| 意图路由模型 | GPT-4o-mini | 低成本、低延迟，复杂场景再升级 |
| Checkpoint | MemorySaver → PostgresSaver | 开发期零依赖，生产期持久化 |
| 工具封装 | LangChain `@tool` | 标准装饰器，方便切 MCP |
| LLM 调用 | OpenAI 兼容 API | 灵活切换服务商 |
| 错误处理 | try/except 非阻断 | `operations_sync` 写 CRM/CAPI 失败不抛异常 |
| 修订上限 | 硬编码 3 次 | 路由函数 `revision_count < 3` 判断 |
| API 框架 | FastAPI | 异步原生、Pydantic 集成、自动文档 |
| 项目结构 | 六层分离 | graph / agents / tools / services / prompts / tests 解耦 |

---

## 10. 旅游定制 Agent 深度实现 (v0.2.0)

### 10.1 千问模型接入

- **方案**：阿里云 DashScope OpenAI 兼容 API
- **模型分层**：

| 模型 | 用途 | 特点 |
|------|------|------|
| `qwen-turbo` | 意图路由 + 需求提取 | 轻量快速，成本极低 |
| `qwen-plus` | 客服/销售/运营 Agent | 主力模型，性价比最优 |
| `qwen-max` | 旅游定制行程生成 | 旗舰推理，复杂长文本 |

- **网关升级**：
  - 新增 `chat_with_tools()` 多轮工具调用循环（最多 5 轮），自动处理 tool_calls → 执行 → 回传
  - 支持 LangChain Tool → OpenAI function schema 自动转换
  - Token 用量日志 + 错误兜底
  - 预置三档实例：`gateway_default` / `gateway_router` / `gateway_planner`

### 10.2 中国入境游知识库

- **文件**：`knowledge/china_travel_kb.md`
- **规模**：20 城市 × 200+ 景点 × 100+ 美食推荐
- **维度覆盖**：
  - 签证与入境政策（免签/过境免签/口岸）
  - 城市深度指南（北京/上海/西安/成都/桂林/云南/杭州/苏州/重庆/广州/厦门/哈尔滨/拉萨/深圳/张家界）
  - 跨城市经典线路（6 条推荐路线）
  - 交通速查表（城市对飞机/高铁时间+票价）
  - 实用信息（货币/支付/上网/App/文化礼仪/应急）
  - 节假日 2026 完整日历
  - 行程定制核心约束（交通时间/体力分配/预算参考/天气应对）

### 10.3 增强的工具层

#### search_faq — FAQ 知识检索
- **方案**：内建 50+ 条结构化 FAQ，按关键词精确+模糊匹配
- **覆盖**：签证、免签、支付、上网、交通、天气、节假日、12 城市指南、线路推荐、预算、礼仪、应急
- **打分机制**：精确匹配=1.0，内容匹配=0.7，关键词匹配=0.4

#### get_weather — 天气查询
- **方案**：10 个城市 × 12 个月真实气候数据（高温/低温/降雨天数/穿衣/旅游适宜度）
- **附加输出**：季节性提示 + 综合旅游建议
- **兜底**：未知城市使用默认气候模板

#### query_calendar — 日历查询
- **方案**：2026 年完整中国节假日数据库 + 拥挤度评级
- **输出**：节假日/周末/工作日 + 拥挤度文字 + 出行建议 + 附近节假日预警
- **评级体系**：极度拥挤(国庆/春节)、非常拥挤(劳动节)、较拥挤(清明/端午)、中度、工作日

#### query_inventory — 库存查询
- **方案**：6 城市(北京/上海/西安/成都/桂林/丽江/杭州) × 3 档次(奢华/舒适/经济) 酒店+门票+车辆
- **智能匹配**：根据人数自动推荐合适车型（5座/7座/14座/33座）
- **汇总输出**：均价 + 推荐车型 + 预算摘要

### 10.4 TripPlannerAgent 完整流程

```
用户消息 → [qwen-turbo 提取需求]
              ↓
        必填项齐全? ──否──→ 追问客户
              ↓ 是
    ┌─────────┼─────────┐
    ↓         ↓          ↓
get_weather  calendar  search_faq
    ↓         ↓          ↓
    └─────────┼─────────┘
              ↓
       query_inventory
              ↓
    组装上下文 → [qwen-max 生成行程]
              ↓
     解析 TripDraft + 构建回复
```

**六步流程**：
1. **需求提取**：qwen-turbo 结构化提取 destination/days/date/pax/budget/theme/pace
2. **并行查询**：天气 + 日历 + FAQ 知识库
3. **库存查询**：根据预算档次匹配酒店/门票/车辆
4. **上下文组装**：将需求 + 全部工具结果拼接为 4000+ token 的详细 prompt
5. **生成行程**：qwen-max 输出完整 Markdown 行程（每日安排 + 费用预估 + 天气 + 贴士）
6. **解析输出**：正则提取费用 + 每日亮点 + 天气摘要 → TripDraft

**验证结果**（4 个测试用例）：
| 用例 | 行程长度 | 预估费用 | 验证 |
|------|---------|---------|------|
| 北京 5 日 | 2,152 字 | ¥32,650/人 | ✅ |
| 成都 3 日 | 1,994 字 | ¥4,775/人 | ✅ |
| 西安 4 日 | 1,399 字 | - | ✅ |
| 桂林 4 日 | 2,043 字 | ¥15,550/人 | ✅ |

### 10.5 System Prompt 升级

- **角色**：15 年资深中国入境游规划师
- **约束嵌入**：
  - 节奏控制（轻松/适中/紧凑三档）
  - 交通约束（每日景点间 ≤2.5h）
  - 预算匹配（经济/舒适/奢华三档）
  - 天气应对（雨季室内、夏季避开中午、冬季冰火平衡）
  - 节假日提醒（国庆/春节酒店翻 3-5 倍）
- **输出格式**：严格 Markdown 模板（概览 → 每日行程 → 费用预估 → 天气 → 贴士 → 应急）
- **预约提醒清单**：故宫(7天)、国博(3天)、陕历博(14天)、布达拉宫(7天)、迪士尼、鼓浪屿

### 10.6 意图路由器

- **模型**：`qwen-turbo`，temperature=0.1 保证一致性
- **验证**：5/5 分类正确（planner 0.9 / service 0.75-0.85 / 全部正确路由）
- **性能**：单次调用 ~300 tokens in, ~65 tokens out，延迟 ~2s

---

## 11. RAG + 三层记忆系统 (v0.3.0)

### 11.1 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                     MemoryOrchestrator                        │
│                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │ Short-Term      │  │ Working         │  │ Long-Term     │ │
│  │ (Redis)         │  │ (Kafka)         │  │ (MySQL)       │ │
│  │                 │  │                 │  │               │ │
│  │ 会话上下文 30m  │  │ Agent 事件流    │  │ 消息归档 永久 │ │
│  │ 客户热缓存 24h  │  │ 异步任务分发    │  │ 客户画像 永久 │ │
│  │ 频率限制 1m     │  │ 跨Agent通信     │  │ 行程记录 永久 │ │
│  │ 工具缓存 10m    │  │ 分析埋点        │  │ RAG 反馈 永久 │ │
│  └─────────────────┘  └─────────────────┘  └───────────────┘ │
│                            ↕                                  │
│                    Kafka → MySQL 事件桥接                     │
└──────────────────────────────────────────────────────────────┘
```

### 11.2 真正的 RAG 实现

**之前 (search_faq)**：Python `dict` + 关键词字符串匹配

**现在 (rag_search)**：DashScope text-embedding-v3 + Milvus 向量数据库

| 维度 | 旧版 (Keyword) | 新版 (RAG) |
|------|---------------|-----------|
| 检索方式 | `query in key` 字符串匹配 | 1024维向量 COSINE 相似度 |
| 语义理解 | ❌ "便宜酒店" 匹配不到 "经济住宿" | ✅ 语义向量自动关联 |
| 多语言 | ❌ 中文query查英文key不行 | ✅ 跨语言向量对齐 |
| 可扩展 | ❌ 硬编码50条FAQ | ✅ Milvus 支持百万级 |
| 降级策略 | N/A | Milvus不可用→自动回退关键词 |
| 结果缓存 | ❌ 无 | ✅ Redis 缓存 10min TTL |

**流程**：
```
用户查询 "北京雨季怎么办"
  → [DashScope Embedding → 1024维向量]
  → [Milvus ANN 搜索 travel_knowledge Collection]
  → [COSINE ≥ 0.3 过滤]
  → [返回: 北京天气指南(0.87), 室内景点推荐(0.82), 雨季穿衣建议(0.75)]
  → [Redis 缓存 10min]
```

**降级链路**：
```
Milvus连接失败 → Embedding失败 → 自动降级到 search_faq 关键词匹配
```

### 11.3 DashScope Embedding

- **模型**：`text-embedding-v3` (1024维)
- **调用方式**：直接 HTTP (urllib)，不依赖 OpenAI SDK
- **批量处理**：每批 ≤25 条，自动分批
- **text_type 区分**：document (知识库) / query (用户查询)
- **重试**：最多 3 次，间隔 1s/2s/3s

### 11.4 知识库索引

- **脚本**：`scripts/index_knowledge_base.py`
- **切片策略**：
  - `##` 二级标题 → 文档边界
  - 块大小 100-1500 字符
  - 自动分类检测 (visa/city/food/transport/culture/emergency 等 16 类)
  - 过短块 (<100字符) 自动合并到上一块
- **索引模式**：
  - 全量：`python scripts/index_knowledge_base.py`
  - 增量：`python scripts/index_knowledge_base.py --incremental`
  - 重建：`python scripts/index_knowledge_base.py --rebuild`

### 11.5 三层记忆数据流

#### 读取 (Recall)
```
用户请求
  → Redis 短时记忆 (热数据, 最快)
    → 命中 → 返回 + 续期 TTL
    → 未命中 → MySQL 长时记忆 (冷数据)
      → 有数据 → 回填 Redis + 返回
      → 无数据 → 返回空
```

#### 写入 (Remember)
```
新消息到达
  → Redis 立即写入 (设置 TTL)
  → Kafka 发布事件 (异步, 不阻塞)
  → Kafka Consumer → MySQL 持久化 (后台)
```

### 11.6 基础设施

| 服务 | 端口 | 用途 |
|------|------|------|
| Milvus | 19530 | 向量数据库 (RAG) |
| Etcd | 2379 | Milvus 元数据 |
| MinIO | 9000/9001 | Milvus 对象存储 |
| Redis | 6379 | 短时记忆 |
| Kafka | 9092 | 工作记忆 |
| Kafka-UI | 8080 | Kafka 管理界面 |
| MySQL | 3306 | 长时记忆 |

### 11.7 新增文件清单

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | 全部基础设施一键编排 |
| `deploy/init.sql` | MySQL 6 张表初始化 |
| `deploy/redis.conf` | Redis 持久化配置 |
| `services/vector_store.py` | MilvusStore + EmbeddingService |
| `services/redis_cache.py` | Redis 短时记忆 (完整实现) |
| `services/kafka_broker.py` | Kafka 工作记忆 (完整实现) |
| `services/mysql_store.py` | MySQL 长时记忆 (完整实现) |
| `services/memory/__init__.py` | 三层记忆模块入口 |
| `services/memory/short_term.py` | 短时记忆业务封装 |
| `services/memory/working.py` | 工作记忆业务封装 |
| `services/memory/long_term.py` | 长时记忆业务封装 |
| `services/memory/orchestrator.py` | 三层编排器 + 事件桥接 |
| `tools/rag_search.py` | RAG 语义检索工具 |
| `scripts/index_knowledge_base.py` | 知识库索引脚本 |

### 11.8 更新文件清单

| 文件 | 变更内容 |
|------|---------|
| `main.py` | v0.3.0, 集成 MemoryOrchestrator, 消息自动归档 |
| `agents/trip_planner.py` | search_faq → rag_search |
| `tools/__init__.py` | 导出 rag_search |
| `requirements.txt` | pymilvus, redis[hiredis], aiokafka, aiomysql |
| `.env.example` | MILVUS_HOST, MYSQL_URL, KAFKA_BOOTSTRAP_SERVERS |

---

## 12. 关键设计决策总结

| 决策点 | 方案 | 原因 |
|--------|------|------|
| State 基类 | `MessagesState` | LangGraph 内置，自带消息 reducer |
| 数据模型 | Pydantic v2 `BaseModel` | 类型安全、序列化、校验 |
| 意图路由模型 | qwen-turbo (千问) | 低成本、低延迟，DashScope 原生 |
| Checkpoint | MemorySaver → PostgresSaver | 开发期零依赖，生产期持久化 |
| 工具封装 | LangChain `@tool` | 标准装饰器，方便切 MCP |
| LLM 调用 | DashScope OpenAI 兼容 | 千问三档模型分层 (turbo/plus/max) |
| **RAG 检索引擎** | **Milvus + DashScope Embedding** | **语义向量检索，1024维，COSINE 相似度** |
| **短时记忆** | **Redis (hiredis)** | **会话热数据 30min TTL，LRU 淘汰** |
| **工作记忆** | **Kafka (KRaft)** | **事件流 + 异步任务，gzip 压缩，ack=all** |
| **长时记忆** | **MySQL 8.0 (aiomysql)** | **消息归档+画像+行程+事件持久化** |
| **记忆编排读** | **Redis→miss→MySQL→回填Redis** | **Cache-Aside 模式** |
| **记忆编排写** | **Redis→Kafka→MySQL** | **热数据同步 + 异步持久化** |
| **服务降级** | **RAG 不可用→关键词回退** | **Milvus/Embedding 失败不阻塞业务** |
| 错误处理 | try/except 非阻断 | `operations_sync` 写 CRM/CAPI 失败不抛异常 |
| 修订上限 | 硬编码 3 次 | 路由函数 `revision_count < 3` 判断 |
| API 框架 | FastAPI | 异步原生、Pydantic 集成、自动文档 |
| 项目结构 | 六层分离 + 记忆层 | graph/agents/tools/services/prompts/tests + memory |
