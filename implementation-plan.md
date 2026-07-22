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
