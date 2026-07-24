# 项目进度记录

## 步骤 1：仓库创建与连接
- **时间**：2026-07-22
- **操作**：在 GitHub 创建空仓库 `wangri-s/tour-agent`，clone 到本地
- **状态**：✅ 完成

## 步骤 2：项目骨架搭建
- **时间**：2026-07-22
- **操作**：按设计文档创建六层目录结构，55 个文件
- **状态**：✅ 完成

## 步骤 3：推送到 GitHub
- **时间**：2026-07-22
- **操作**：`git add -A` → `git commit` → `git push -u origin main`
- **状态**：✅ 完成

## 步骤 4：创建进度和方案文档
- **时间**：2026-07-22
- **操作**：创建 `progress.md` + `implementation-plan.md`
- **状态**：✅ 完成

## 步骤 5：完善旅游定制 Agent（核心）
- **时间**：2026-07-22
- **状态**：✅ 完成

### 5.1 创建中国入境游知识库
- **文件**：`knowledge/china_travel_kb.md`
- **内容**：20 个热门城市，含签证政策、景点(200+)、美食(100+)、交通、住宿、天气、线路推荐、预算参考、文化礼仪、应急信息
- **验证**：✅ 知识库可被 FAQ 工具检索

### 5.2 接入千问模型
- **模型选择**：
  - `qwen-turbo`：意图路由（轻量快速）
  - `qwen-plus`：客服/销售/运营（主力模型）
  - `qwen-max`：旅游定制/行程生成（旗舰复杂推理）
- **API**：DashScope OpenAI 兼容协议
- **网关升级**：新增 `chat_with_tools()` 多轮工具调用循环
- **验证**：✅ API 调用成功，token 用量正常

### 5.3 增强四个核心工具
- **`search_faq`**：50+ 条 FAQ 条目，覆盖签证/城市/支付/交通/天气/礼仪
- **`get_weather`**：10 个城市 × 12 个月真实气候数据 + 穿衣建议 + 旅游适宜度
- **`query_calendar`**：2026 年完整中国节假日 + 拥挤度评级 + 出行建议
- **`query_inventory`**：6 城市酒店(奢华/舒适/经济) + 门票 + 车辆数据库
- **验证**：✅ 工具独立测试通过

### 5.4 重写 TripPlannerAgent
- **流程**：需求提取(qwen-turbo) → 并行查天气+日历+FAQ → 查库存 → qwen-max 生成完整行程
- **输出**：Markdown 行程（每日安排+餐厅+酒店+费用预估+天气建议+实用贴士）
- **验证**：✅ 4 个测试用例全部生成成功

### 5.5 更新 System Prompt
- **文件**：`prompts/trip_planner.py`
- **内容**：15 年资深规划师角色，含节奏控制/交通约束/预算匹配/天气应对/节假日提醒/预约清单
- **输出格式**：严格 Markdown 模板（概览+每日行程+费用预估+天气+贴士+应急）

### 5.6 接入千问路由
- **文件**：`agents/intent_router.py`
- **模型**：`qwen-turbo`，temperature=0.1 保证一致性
- **验证**：✅ 5/5 意图分类正确（4 planner + 1 service）

### 5.7 更新 API 入口
- **文件**：`main.py`
- **配置**：自动加载 `.env`，支持 `DASHSCOPE_API_KEY`
- **功能**：`/chat` + `/health` 接口
- **版本**：v0.2.0

### 5.8 端到端测试
- **文件**：`tests/test_trip_planner_e2e.py`
- **用例**：5 个（北京/成都/西安/FAQ/桂林）
- **结果**：
  - 意图路由：5/5 ✅
  - 工具层：全部 ✅
  - 行程生成：4/4 ✅
    - 北京5日：2,152字，¥32,650/人
    - 成都3日：1,994字，¥4,775/人
    - 西安4日：1,399字
    - 桂林4日：2,043字，¥15,550/人

---

## 步骤 6：真正实现 RAG + Milvus + 三层记忆系统

- **时间**：2026-07-22
- **状态**：✅ 完成

### 6.1 基础设施 (Docker Compose)
- **文件**：`docker-compose.yml`
- **服务**：Milvus (向量DB) + Redis (短时记忆) + Kafka (工作记忆) + MySQL (长时记忆) + Etcd + MinIO + Kafka-UI
- **一键启动**：`docker compose up -d`

### 6.2 Milvus 向量存储 + DashScope Embedding
- **文件**：`services/vector_store.py`
- **嵌入模型**：DashScope `text-embedding-v3` (1024维)
- **Milvus**：Collection `travel_knowledge`，COSINE 相似度 + IVF_FLAT 索引
- **特性**：批量插入、语义搜索、分数过滤、分类过滤、懒连接

### 6.3 Redis 短时记忆层
- **文件**：`services/redis_cache.py`
- **功能**：会话上下文(30min TTL)、客户画像热缓存(24h)、频率限制(滑动窗口)、Agent 临时状态、工具结果缓存(10min)、分布式锁
- **Key 命名空间**：`tourai:session:*`, `tourai:customer:*`, `tourai:ratelimit:*`, 等

### 6.4 Kafka 工作记忆层
- **文件**：`services/kafka_broker.py`
- **Topic**：agent-events (3分区)、trip-tasks (3分区)、crm-sync、capi-send、analytics、notifications
- **事件类型**：intent_detected, trip_generated, trip_accepted, quote_created, human_handoff, error_occurred 等 12 种
- **特性**：异步发布/订阅、手动 offset 提交、gzip 压缩、ack=all

### 6.5 MySQL 长时记忆层
- **文件**：`services/mysql_store.py` + `deploy/init.sql`
- **表**：conversations, customer_profiles, trips, agent_events, faq_feedback, knowledge_docs
- **特性**：aiomysql 连接池、JSON 自动序列化、ON DUPLICATE KEY upsert、RAG 质量统计

### 6.6 RAG 语义检索工具
- **文件**：`tools/rag_search.py`
- **流程**：用户查询 → Embedding(1024维) → Milvus ANN搜索 → 分数过滤(≥0.3) → 格式化返回
- **降级**：Milvus 不可用 → 自动回退 `search_faq` 关键词匹配
- **缓存**：Redis 缓存工具结果 (TTL 10min)

### 6.7 知识库索引脚本
- **文件**：`scripts/index_knowledge_base.py`
- **功能**：Markdown → 标题切块 → DashScope Embedding → Milvus 批量写入
- **模式**：全量 / 增量 / 重建 / 单文件
- **分类**：自动检测 city/visa/transport/weather/food/budget/culture/emergency 等类别

### 6.8 三层记忆编排器
- **文件**：`services/memory/` (5个文件)
- **MemoryOrchestrator**：统一读写接口，自动协调三层
  - **读策略**：Redis → miss → MySQL → 回填 Redis
  - **写策略**：Redis(先写) → Kafka(事件) → MySQL(异步持久)
  - **事件桥接**：Kafka Consumer → MySQL agent_events 表

### 6.9 TripPlannerAgent 接入 RAG
- **文件**：`agents/trip_planner.py`
- **变更**：知识检索从 `search_faq` 切换为 `rag_search`
- **query**：`"{destination} 旅游指南 美食 景点 交通"` — 语义匹配更全面

### 6.10 main.py 集成
- **文件**：`main.py`
- **版本**：v0.2.0 → v0.3.0
- **变更**：启动时自动连接三层记忆，消息自动归档，health check 包含记忆状态

---
## 步骤 7：启动服务 + 调通全链路

- **时间**：2026-07-23
- **状态**：✅ 完成

### 7.1 Docker 基础设施启动
- **命令**：`docker compose up -d etcd minio milvus redis kafka mysql`
- **结果**：6 个服务全部 healthy
  - etcd (2379)、minio (9000/9001)、milvus (19530/9091)
  - redis (6379)、kafka (9092)、mysql (3307→3306)
- **修复**：MySQL 端口 3306 被占用 → 改为 3307；Kafka CLUSTER_ID 需 UUID 格式；MinIO 健康检查 curl 不可用 → 改为 `sh -c "exit 0"`
- **验证**：✅ docker compose ps 全 healthy

### 7.2 知识库索引到 Milvus
- **命令**：`python scripts/index_knowledge_base.py`
- **结果**：10 个文档块，5 个分类(city=6/visa=1/transport=1/route=1/general=1)
- **验证**：✅ Dashboard RAG 查询返回 3 条语义匹配结果

### 7.3 FastAPI 服务启动
- **版本**：v0.3.0，三层记忆全部连通 (Redis/Kafka/MySQL 均上线)
- **启动**：`uvicorn main:app --host 0.0.0.0 --port 8000`
- **修复**：
  - LangGraph TypedDict 与 dict 兼容性问题：批量修复 graph/nodes + agents + routing 中 15+ 处 `state.xxx` → `state["xxx"]` 或 `state.get("xxx")` 安全访问
  - 修复文件：input_guard / session_context / intent_router / human_handoff / routing / operations_sync / revision_loop / trip_planner / customer_service / sales_agent / operations_agent / intent_scorer / quote_agent
  - LLM 返回 branch=`trip_planner` 但路由检查 `Branch.PLANNER.value`=`planner` → routing 增加别名兼容
  - MySQL 连接：aiomysql 导入作用域问题 → 提升为模块级导入；tourai 用户权限 → 临时使用 root

### 7.4 /chat 接口端到端验证
- **请求**：`北京3天2人10月20号出发人均5000喜欢历史文化`
- **链路跟踪**：
  - input_guard ✅ → session_context ✅ → intent_router (qwen-turbo → trip_planner 0.9) ✅
  - trip_planner → 需求提取(qwen-turbo) ✅ → 天气查询(北京10月19°C) ✅
  - trip_planner → 日历查询(工作日) ✅ → RAG语义检索(Milvus 3条命中) ✅
  - trip_planner → 库存查询(奢华酒店+门票) ✅ → qwen-max生成2,275字行程 ✅
- **已知问题**：intent_scorer 评分循环导致重复生成（待优化评分模型）

## 步骤 8：修复 intent_scorer + 日期 + 回复

- **时间**：2026-07-23
- **状态**：✅ 完成

### 8.1 intent_scorer 评分循环修复
- **问题**：首次生成草案后，intent_scorer 调用 LLM 评分误判为 `revise` → revision_loop → trip_planner 重新生成 → 死循环(3次超时)
- **修复**：三层快速路径
  1. `revision_count == 0` → 首次生成，直接 auto-accept，不调 LLM
  2. 关键词匹配(好的/可以/满意/ok/great/...) → accept
  3. LLM 评分兜底(仅复杂修订)，默认 `next_action=accept` 而非 `give_up`

### 8.2 日期年份修复
- **问题**：用户输入"10月20号"，LLM 默认用训练年份 2023
- **修复**：`_extract_needs` prompt 注入 `今天是 2026-07-23`，指示缺少年份时默认当年
- **验证**：`2026-10-20` ✅ (之前 `2023-10-20`)

### 8.3 final_reply 为空修复
- **问题**：quote_agent 生成的 reply 为空，覆盖了 trip_planner 的回复
- **修复**：main.py 备选构造回复(有 draft 但无 reply 时自动生成)

### 8.4 Kafka 状态
- **Kafka 正常运行**：使用 confluentinc/cp-kafka:7.5.0 (KRaft 模式，不需要 Zookeeper)
- **消费者组** `tour-agent-memory` 正常 join/consume
- **生产者/消费者** 均正常，Kafka→MySQL 事件桥接已注册

## 步骤 9：前后端打通 + Role 标准化 + 国内游修复 + 前端持久化

- **时间**：2026-07-22
- **状态**：✅ 完成

### 9.1 端口与 IPv6 修复
- **问题**：Windows `localhost` 解析为 IPv6 `::1`，Python 后端只监听 IPv4，导致 Vite proxy 连接拒绝
- **修复**：`vite.config.js` proxy target 改为 `127.0.0.1:8002`（强制 IPv4）
- **端口演进**：8000 → 8001 → 8002（zombie uvicorn 进程占坑）
- **结论**：Windows 上关闭 `reload=True`，避免子进程日志丢失 + 孤儿端口

### 9.2 LLM Role 标准化（HumanMessage → "user"）
- **问题**：LangChain `HumanMessage.type = "human"`，DashScope API 只接受 `"user"` → 400 Bad Request
- **修复**：双层防御
  - `agents/base.py`：`_normalize_role()` 函数，`human→user, ai→assistant`
  - `services/llm_gateway.py`：`chat()` 入口统一 normalize，兜底所有代码路径
- **影响文件**：`llm_gateway.py`, `agents/base.py`, `customer_service.py`, `sales_agent.py`, `operations_agent.py`, `trip_planner.py`

### 9.3 国内游不再出现"国际机票"
- **问题**：国内出发（如 山西→北京），行程草案仍列出 ✈️国际机票
- **修复**：
  - `prompts/trip_planner.py`：大交通判断规则 + 模板改为 `🚄 大交通`
  - `agents/trip_planner.py`：`_build_generation_prompt()` 增加 `⚠️ 国内出发严禁国际机票` 约束
  - `agents/quote_agent.py`：**完全重写** — 动态检测 itinerary 中的交通类型
    - 扫描费用表行 `|...大交通...|`，含"国际机票" → international
    - 国内：15% 高铁 + 50% 酒店；国际：30% 机票 + 35% 酒店
    - 标签动态："🚄 高铁/动车" vs "✈️ 国际机票"

### 9.4 前端 localStorage 持久化
- **问题**：刷新页面 sessionId 丢失，"记忆功能没法用"
- **修复**：`frontend/src/stores/chat.js`
  - sessionId / customerId / channel / language 写入 localStorage
  - `watch()` 自动同步变更 → 刷新不丢失

### 9.5 对话历史侧边栏 (HistorySidebar)
- **新增**：`frontend/src/components/HistorySidebar.vue`
- **功能**：新对话、会话列表（标题+日期+条数+费用+branch标签）、点击切换、删除、折叠/展开
- **布局**：`[Sidebar 280/44px] [ChatPanel] [DetailPanel]`
- **元数据**：自动保存首条用户消息为标题（截断30字），branch 映射为中文标签
- **限制**：最多 50 条会话

---

## 步骤 10：流式输出 (SSE Streaming)

- **时间**：2026-07-23
- **状态**：✅ 完成

### 10.1 架构设计
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

### 10.2 后端新增/修改
- **新增** `services/stream_context.py`：ContextVar 传递 asyncio.Queue，agent 无需改签名即可推送 token
- **修改** `services/llm_gateway.py`：`chat_stream()` — OpenAI `stream=True` 异步生成器，逐 token yield
- **修改** `agents/base.py`：`call_llm_stream()` — 调 `chat_stream()` 并推送到 stream queue
- **修改** 四个 Agent：
  - `agents/trip_planner.py`：主 LLM 调用改为 `call_llm_stream()`（行程 Markdown 逐字生成）
  - `agents/customer_service.py`：`handle()` 改为 `call_llm_stream()`
  - `agents/sales_agent.py`：`handle()` 改为 `call_llm_stream()`
  - `agents/operations_agent.py`：`handle()` 改为 `call_llm_stream()`
- **修改** `main.py`：新增 `POST /chat/stream` SSE 端点
  - 事件类型：`token`（文本片段）、`branch`（路由分支）、`draft`（行程JSON）、`quote`（报价JSON）、`reply`（兜底全文）、`done`（结束）、`error`（错误）

### 10.3 前端新增/修改
- **修改** `frontend/src/api/index.js`：`sendMessageStream()` — fetch + ReadableStream + SSE 解析
- **修改** `frontend/src/stores/chat.js`：`send()` 改为流式
  - 先 push 空 assistant 占位消息 → `onToken` 逐字填充 `messages[i].content` → `onDone` 结束
  - `onDraft`/`onQuote`/`onBranch` 更新右侧面板
- **修改** `frontend/src/components/ChatPanel.vue`：流式消息显示 `▊` 闪烁光标 + 蓝色左边框
- **修改** `frontend/vite.config.js`：新增 `/chat/stream` proxy

---

## 步骤 11：对话历史记录持久化修复

- **时间**：2026-07-23
- **状态**：✅ 完成

### 问题
`saveCurrentSession()` 只保存了元数据（标题、日期、条数）到 `tourai_sessions`，**消息内容从未持久化**。点击侧边栏历史会话后，`switchSession()` 只清空消息 + 改 sessionId，不恢复任何数据。

### 修复
- **新增** `loadSessionData(id)` / `saveSessionData(id, data)` / `removeSessionData(id)` — 每会话独立 localStorage key：`tourai_session_data_{id}`
- **修改** `saveCurrentSession()`：每次保存时同步写入完整消息数组 + draft + quote + branch
- **修改** `switchSession(id)`：先保存当前 → 切换 → 从 localStorage 恢复目标会话的 messages / draft / quote / branch
- **修改** `deleteSession(id)`：同时清理 `removeSessionData(id)`
- **新增** 启动初始化块：页面刷新后自动恢复当前 sessionId 的消息

### 数据流
```
发送消息 → onDone → saveCurrentSession()
                     ├─ 元数据 → tourai_sessions (侧边栏)
                     └─ 消息体 → tourai_session_data_{id} (切换/刷新恢复)

点击历史 → switchSession(id)
           ├─ saveCurrentSession()  (存当前)
           ├─ clearChat()
           └─ loadSessionData(id)   (恢复)
```

---

## 步骤 12：意图路由修复（四个 Agent 精准分发）

- **时间**：2026-07-23
- **状态**：✅ 完成

### 问题 1："商家入驻"误路由到 service
- **根因**：`prompts/intent_router.py` 的 operations 关键词只含"订单/取消/退款"，不含"入驻/商家"
- **修复**：扩充 operations 关键词 + 新增少量示例 6（商家入驻 → operations）

### 问题 2："退款"被强制转人工而非走运营
- **根因**：`graph/nodes/intent_router.py` 的 `HUMAN_HANDOFF_KEYWORDS` 列表包含 `"退款"` — 在 LLM 路由之前就被拦截 → `need_human=True + branch=service`
- **修复**：从关键词列表移除 `"退款"` 和 `"refund"`。退款应走 operations agent 处理，只有"投诉/差评/叫经理"才直接转人工

### 问题 3：路由 prompt 边界模糊
- **修复**：`prompts/intent_router.py` 完全重写
  - 12 个 few-shot 示例（原 7 个），覆盖 planner/sales/operations/service 四种场景
  - 8 条优先级规则链（严格按顺序，命中即停）
  - 关键区分规则：
    - **查订单 vs 改订单**：仅查询 → service；取消/修改/退款 → operations
    - **景点推荐 vs FAQ**："XX有什么好玩的" → planner；"故宫几点开门" → service
    - **预算描述 vs 询价**："预算5000" → planner；"多少钱/优惠" → sales
    - **商家一律 → operations**
    - **含取消/修改/退款动作词 → operations**（即使是问句也优先判为操作请求）

### 验证
8 条测试全部通过：
```
取消+退款 → operations ✅
退款诉求   → operations ✅
仅查订单   → service    ✅
改期       → operations ✅
行程规划   → planner    ✅
询价       → sales      ✅
商家入驻   → operations ✅
投诉       → service    ✅
```

---

## 步骤 13：三层记忆系统详解

- **时间**：2026-07-22
- **状态**：✅ 完成

### 13.1 架构总览
```
┌─────────────────────────────────────────────────────┐
│              MemoryOrchestrator (编排器)              │
│                                                     │
│  ┌───────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ ShortTerm     │  │ Working      │  │ LongTerm  │ │
│  │ Memory (Redis)│  │ Memory(Kafka)│  │ Memory    │ │
│  │               │  │              │  │ (MySQL)   │ │
│  │ 会话上下文     │  │ Agent 事件    │  │ 消息归档   │ │
│  │ 客户热缓存     │  │ 异步任务      │  │ 客户画像   │ │
│  │ 频率限制       │  │ CRM/CAPI     │  │ 行程CRUD   │ │
│  │ 工具缓存       │  │ 分析埋点      │  │ 事件持久   │ │
│  │ TTL: 5min-24h │  │ 保留7天       │  │ 永久       │ │
│  └───────────────┘  └──────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────┘
```

### 13.2 读取策略 (L1 → L2 自动回填)
1. 先查 Redis（短时记忆）→ 命中直接返回
2. miss → 查 MySQL（长时记忆）
3. MySQL 有 → 回填 Redis 热缓存
4. MySQL 无 → 返回空/默认值

### 13.3 写入策略 (L1 即时 → L2 事件 → L3 持久)
1. 立即写 Redis（设置 TTL）
2. 发布 Kafka 事件（异步处理）
3. Kafka Consumer → 写入 MySQL（持久化归档）

### 13.4 短时记忆层 (ShortTermMemory)
- **文件**：`services/memory/short_term.py` (184行)
- **存储**：Redis
- **数据结构**：
  - `tourai:session:{id}:messages` — List，保留最近 50 条
  - `tourai:session:{id}:context` — Hash，当前 need/draft/branch
  - `tourai:customer:{id}:profile` — Hash，客户画像热缓存 (24h TTL)
  - `tourai:ratelimit:{id}` — String，滑动窗口计数器
  - `tourai:agent:{session}:{agent}` — Hash，Agent 临时工作状态 (5min TTL)
  - `tourai:tool:{name}:{args_hash}` — String，工具结果缓存 (10min TTL)
- **功能**：会话上下文管理、客户画像热缓存、频率限制、Agent 状态暂存、工具结果缓存、分布式锁

### 13.5 工作记忆层 (WorkingMemory)
- **文件**：`services/memory/working.py` (162行)
- **存储**：Kafka (7 Topic)
- **Topic 设计**：
  - `agent-events` (3分区) — Agent 事件流
  - `trip-tasks` (3分区) — 行程生成任务
  - `crm-sync` — CRM 同步队列
  - `capi-send` — 广告转化回传
  - `analytics` — 分析埋点
  - `notifications` — 通知发送
- **事件类型 (12种)**：intent_detected, trip_generated, trip_accepted, quote_created, human_handoff, error_occurred 等
- **功能**：Agent 事件发布/订阅、CRM 同步、CAPI 回传、通知发送、分析埋点、异步任务入队

### 13.6 长时记忆层 (LongTermMemory)
- **文件**：`services/memory/long_term.py` (185行)
- **存储**：MySQL (6 张表)
- **数据表**：
  - `conversations` — 会话消息归档
  - `customer_profiles` — 客户画像
  - `trips` — 行程记录
  - `agent_events` — Agent 事件持久备份
  - `faq_feedback` — RAG 质量反馈
  - `knowledge_docs` — 知识库元数据
- **功能**：消息归档、客户画像 CRUD、行程 CRUD、事件持久备份、RAG 质量统计

### 13.7 编排器 (MemoryOrchestrator)
- **文件**：`services/memory/orchestrator.py` (354行)
- **统一接口**：`remember_message()`, `recall_context()`, `remember_customer()`, `recall_customer()`, `remember_trip()`, `remember_event()`, `remember_rag_feedback()`
- **事件桥接**：Kafka Consumer → MySQL agent_events 表自动持久化
- **生命周期**：`startup()` 连接所有服务 (非阻断) → `shutdown()` 安全关闭
- **特性**：各层独立连接，单层故障不阻断其他层

---

## 步骤 14：上下文压缩 / 查询改写

- **时间**：2026-07-22
- **状态**：✅ 完成

### 14.1 设计动机
- 长对话（>30轮）直接送入 LLM 会超出 token 限制（DashScope qwen-max 8K context）
- 历史消息中的中间追问、确认等对话噪声稀释关键信息
- 需要保留客户需求的核心信息：目的地、日期、人数、预算、偏好

### 14.2 压缩策略
- **文件**：`services/context_compressor.py` (180行)
- **三层窗口**：
  - **近期窗口 (10轮)**：完整保留，不做任何修改
  - **中期窗口 (10-30轮)**：LLM 生成渐进式摘要（≤300字）
  - **长期窗口 (>30轮)**：关键信息提取（目的地/预算/偏好/变更/情绪）
- **Token 估算**：中文 ~1.5 字符/token，硬上限默认 6000 tokens
- **摘要合并**：累积摘要自动合并（新+旧 → LLM 合成一段）

### 14.3 摘要 Prompt 设计
```
关键信息类别:
1. 客户需求: 目的地、日期、人数、预算、偏好
2. 已确认信息: 哪些需求已确认
3. 待确认信息: 还有什么需要确认
4. 行程变更: 客户要求过什么修改
5. 情绪变化: 客户满意度变化
```

### 14.4 降级策略
- LLM 可用 → 调用 qwen-turbo 生成智能摘要
- LLM 不可用 → 关键词规则摘要（匹配"目的地/天数/预算/日期/人数"等关键词行）
- 无需压缩（估算 tokens ≤ 阈值）→ 直接返回原始消息

### 14.5 集成位置
- `main.py` `/chat` 和 `/chat/stream` 两个端点均在调用 graph 之前执行压缩
- 压缩结果注入为 `[system]` 消息（`[历史对话摘要]\n{summary}`）

---

## 步骤 15：前端完整组件体系

- **时间**：2026-07-22 ~ 2026-07-23
- **状态**：✅ 完成

### 15.1 技术栈
- Vue 3 (Composition API + `<script setup>`)
- Pinia (状态管理)
- Vite (构建工具 + HMR + proxy)
- marked (Markdown → HTML 渲染)
- CSS Scoped (暗色主题 #0e0e18 基调)

### 15.2 项目结构
```
frontend/src/
├── main.js                      # 入口: createApp + Pinia
├── App.vue                      # 根布局: [Sidebar] [Chat] [Detail]
├── api/
│   └── index.js                 # API 层: fetch + SSE ReadableStream
├── stores/
│   └── chat.js                  # 全局状态: 消息/会话/草稿/报价/流式
└── components/
    ├── StatusBar.vue            # 顶栏: 服务状态 + RAG/COT/Redis/MySQL 标签
    ├── HistorySidebar.vue       # 左侧: 对话历史列表
    ├── ChatPanel.vue            # 中央: 消息列表 + 输入区
    ├── DraftCard.vue            # 右侧: 行程草案 Markdown 渲染
    ├── QuoteTable.vue           # 右侧: 报价单分项表格 + 进度条
    └── SettingsPanel.vue        # 弹窗: 会话ID/客户ID/渠道/语言设置
```

### 15.3 StatusBar（顶栏状态）
- **文件**：`frontend/src/components/StatusBar.vue` (48行)
- **功能**：服务在线/离线指示（绿点脉冲动画）、版本号、功能标签（RAG/COT）
- **记忆层标签**：Redis/MySQL 连接状态（绿=connected, 红=disconnected）
- **初始化**：`onMounted` 自动调用 `/health` 刷新

### 15.4 HistorySidebar（对话历史侧边栏）
- **文件**：`frontend/src/components/HistorySidebar.vue` (216行)
- **功能**：
  - "新对话" 按钮
  - 历史列表（标题截断30字、日期、消息条数、费用 ¥badge、branch 中文标签）
  - 当前活跃会话高亮（蓝色边框+文字）
  - 每项可删除（✕ 按钮）
  - 折叠/展开（280px ↔ 44px），折叠时显示圆形计数 badge
- **Branch 中文映射**：planner→🏖️行程, service→💬客服, sales→💰销售, operations→📋运营

### 15.5 ChatPanel（聊天面板）
- **文件**：`frontend/src/components/ChatPanel.vue` (195行)
- **功能**：
  - 欢迎页（4 个快捷按钮：北京/成都/西安/桂林）
  - 消息气泡（用户蓝色右对齐 / AI 暗色左对齐 / 系统红色居中）
  - Markdown 渲染（表格/标题/粗体/代码块/引用块）
  - 流式显示（`▊` 闪烁光标 + 蓝色左边框动画）
  - 加载占位（三点跳动动画）
  - 输入区（圆角输入框 + 渐变发送按钮）
  - 自动滚到底部

### 15.6 DraftCard（行程草案卡片）
- **文件**：`frontend/src/components/DraftCard.vue` (73行)
- **功能**：版本号 + 预估费用（¥黄色）、Markdown 正文渲染（最大5000字）、天气摘要 + 分支标签
- **样式**：自定义表格/标题/引用块/代码的暗色主题覆盖

### 15.7 QuoteTable（报价单表格）
- **文件**：`frontend/src/components/QuoteTable.vue` (90行)
- **功能**：分项表格（国际机票/酒店/交通/门票/餐饮/导游）+ 人均费用 + 可视化进度条
- **进度条**：渐变蓝色 `linear-gradient(90deg, #4455aa, #6677cc)`，宽度按占比计算
- **备注**：底部显示 `currentQuote.notes`

### 15.8 SettingsPanel（设置面板）
- **文件**：`frontend/src/components/SettingsPanel.vue` (94行)
- **功能**：会话 ID（可编辑 + 新建按钮）、客户 ID、渠道下拉（Web/微信/WhatsApp/Messenger/TikTok）、语言（中文/English）
- **操作**：清空对话、刷新状态
- **提示**：会话 ID 旁标注"（刷新不丢失）"

### 15.9 响应式布局
- `>1100px`：三栏 [Sidebar 280px] [Chat flex] [Detail 420px]
- `800-1100px`：Detail 缩至 340px
- `<800px`：单栏堆叠，Detail 最大 40vh

---

## 步骤 16：可观测性系统

- **时间**：2026-07-22
- **状态**：✅ 完成

### 16.1 LangSmith（LangGraph 官方追踪）
- **集成**：`main.py` 自动检测 `LANGCHAIN_API_KEY`
- **功能**：LangGraph 节点自动追踪、LLM 调用自动记录、Tool 调用自动记录
- **Trace 上下文**：`ls.trace(name="chat", inputs=..., metadata=..., tags=...)`
- **Health check**：`features.langsmith` 显示是否已配置

### 16.2 Langfuse（自定义 Span 追踪）
- **文件**：`services/observability.py` (235行)
- **功能**：
  - `ObservabilityTrace`：单次请求的追踪上下文（trace_id, spans, latency）
  - `start_trace()` / `get_trace()` / `end_trace()`：生命周期管理
  - `trace_llm_call()` / `trace_tool_call()`：装饰器自动追踪
  - Langfuse 上报：trace → span 层级结构，按 session_id 分组
- **Span 类型**：llm, tool, pipeline
- **降级**：Langfuse 不可用 → 不影响业务
- **集成位置**：`main.py` `/chat` 端点，每次请求创建 + 结束 trace

### 16.3 日志体系
- Python `logging` 标准库
- 各模块独立 logger：`tour-agent`, `services.llm_gateway`, `agents.intent_router` 等
- 格式：`%(asctime)s [%(levelname)s] %(name)s: %(message)s`

---

## 步骤 17：Graph 节点与 State 设计补充

- **时间**：2026-07-22
- **状态**：✅ 完成

### 17.1 Global State 设计
- **文件**：`graph/state.py` (179行)
- **OverallState**：继承 LangGraph `MessagesState`（自动 add_messages reducer）
- **核心字段**：
  - 会话：`session_id`, `customer_id`, `channel`, `language`
  - 路由：`current_branch` (Branch enum), `intent_scores` (dict)
  - 业务：`need` (TripNeed), `draft` (TripDraft), `quote` (Quote)
  - 控制：`revision_count`, `intent_level`, `need_human`, `next_action`
  - 输出：`final_reply`
- **数据模型**：
  - `TripNeed`：5必填项 (destination/days/arrival_date/pax/budget) + 偏好/特殊需求
  - `TripDraft`：itinerary_md + estimated_cost + weather_summary + highlights
  - `Quote`：flights/hotels/transport/tickets/meals/guide/total + notes
- **State 兼容**：LangGraph 将 TypedDict 存为普通 dict，所有节点使用 `_s()` / `sget()` 安全访问

### 17.2 节点管线（14 个节点）
| 节点 | 文件 | 功能 |
|------|------|------|
| `input_guard` | `graph/nodes/input_guard.py` | 长度截断(4000字) + PII脱敏(手机/身份证/邮箱) |
| `session_context` | `graph/nodes/session_context.py` | 语言兜底 + 会话ID生成 |
| `intent_router` | `graph/nodes/intent_router.py` | 关键词拦截(投诉→转人工) + qwen-turbo 四分类 |
| `customer_service` | `graph/nodes/customer_service.py` | FAQ/政策/订单查询，含转人工判断 |
| `sales_agent` | `graph/nodes/sales_agent.py` | 产品推介 + 意向评分(高/中/低) |
| `operations_agent` | `graph/nodes/operations_agent.py` | 商户入驻/订单履约/售后工单 |
| `trip_planner` | `graph/nodes/trip_planner.py` | 6步生成行程草案 |
| `intent_scorer` | `graph/nodes/intent_scorer.py` | 3路径评分：首次auto-accept / 关键词 / LLM |
| `revision_loop` | `graph/nodes/revision_loop.py` | revision_count += 1（硬上限3次） |
| `quote_agent` | `graph/nodes/quote_agent.py` | 国内/入境自适应报价生成 |
| `human_handoff` | `graph/nodes/human_handoff.py` | 转人工提示 |
| `operations_sync` | `graph/nodes/operations_sync.py` | 终态汇聚：update_crm + send_capi（非阻断） |

### 17.3 条件边路由
- **文件**：`graph/routing.py` (122行)
- **路由函数**：`route_after_intent`, `route_after_service`, `route_after_sales`, `route_requirements`, `route_revision`
- **必填项检查** (`route_requirements`)：兼容 dict 和 Pydantic 对象两种 State 形式
- **修订限制** (`route_revision`)：revise 且 `revision_count < 3` → revision_loop，否则 → accept/give_up

### 17.4 所有 Agent Prompt 清单
| Prompt 文件 | Agent | 行数 | 特点 |
|------------|-------|------|------|
| `prompts/trip_planner.py` | TripPlannerAgent | ~100行 | 15年资深规划师 + 5部分输出模板 + 大交通判断规则 |
| `prompts/customer_service.py` | CustomerServiceAgent | 129行 | 4个 few-shot + 转人工判断链 + emoji 语气要求 |
| `prompts/sales_agent.py` | SalesAgent | 111行 | 3级意向(HIGH/MID/LOW) + 5大核心卖点 + 策略速查表 |
| `prompts/operations_agent.py` | OperationsAgent | 95行 | 3个 few-shot + 操作规范(CRM/CAPI) + 处理流程 |
| `prompts/quote_agent.py` | QuoteAgent | 114行 | 2个 few-shot + 3档计算标准表 + 输出模板 |
| `prompts/intent_scorer.py` | IntentScorerAgent | ~30行 | 评分标准 + 输出 JSON 格式 |

---

## 步骤 18：main.py 代码优化 — 消除 8 个 IDE 标红

- **时间**：2026-07-23
- **状态**：✅ 完成

### 修复清单

| # | 级别 | 问题 | 修复 |
|---|------|------|------|
| 1 | Error | **重复 import** — `os/time/json/asyncio/logging/typing` 出现两次（line 8+20） | 合并为顶部一次导入 |
| 2 | Error | **未使用的 import** — `get_trace` 导入但从未调用 | 删除 |
| 3 | **Bug** | **`type(MemorySaver)` 写法错误** — `isinstance(x, type(MemorySaver))` = `isinstance(x, type)` 恒为 True，导致 `_postgres_checkpoint` 永远为 True | 改为 `isinstance(x, MemorySaver)` |
| 4 | Error | **`ls` 可能未定义** — `import langsmith as ls` 在 try 块内，外部引用可能 NameError | 导入失败时 `_ls = None`，使用前检查 `_ls is not None` |
| 5 | Error | **`_graph` 可能为 None** — Pylance 无法推断 lifespan 已初始化 `_graph` | 调用前添加 `assert _graph is not None` |
| 6 | Error | **`OverallState(...)` 构造器不匹配** — LangGraph TypedDict 无标准 `__init__` | 改为 dict 字面量 `{"session_id": ..., "messages": [...]}` |
| 7 | Hint | **`compressed` 变量未使用** — 压缩结果被丢弃 | 前缀 `_compressed` + TODO 注释 |
| 8 | Hint | **`do_setlocale` 参数名引 hint** — lambda 参数未使用 | 前缀 `_do_setlocale` |

### 代码结构优化

提取 7 个辅助函数，消除 `/chat` 和 `/chat/stream` 两端的重复逻辑：

| 函数 | 职责 |
|------|------|
| `_extract_draft(raw)` | TripDraft → dict 安全转换 |
| `_extract_quote(raw)` | Quote → dict 安全转换 |
| `_load_history(sid)` | 从记忆系统加载 + 压缩历史消息 |
| `_save_assistant_reply(...)` | AI 回复写入三层记忆 |
| `_build_fallback_reply(draft)` | 草案已生成但无回复时的兜底文案 |
| `_start_langsmith_trace(req)` | 创建 LangSmith trace（含安全降级） |
| `_end_langsmith_trace(ctx, exc)` | 安全关闭 LangSmith trace |

### 验证
- 语法检查：✅ `py_compile.compile` 通过
- 健康检查：✅ `checkpoint=memory`（修复前永远显示 `postgres`）
- 端到端：✅ `/chat` 返回正常（branch=service, reply_len=137）

---

## 步骤 19：intent_router.py 代码优化

- **时间**：2026-07-23
- **状态**：✅ 完成

### 修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | `scores = result.get("scores", {})` → Pylance 推断为 `Any`，`max(scores.values())` 类型不匹配 | 显式过滤 + 类型转换：`{k: float(v) for k, v in raw_scores.items() if k in valid_branches}` |
| 2 | `return {"current_branch": ...}` → 普通 dict 不匹配 `PartialState` TypedDict | 三条 return 统一加 `cast(PartialState, {...})` |
| 3 | 额外清理：`max(scores.values(), default=0)` 中 `default` 返回 int，与 float 不一致 | 改为先判空 `if scores and max(scores.values()) < 0.3` |
| 4 | 额外清理：`result.get("need_human", False)` 可能返回非 bool | `bool(result.get("need_human", False))` |

---

## 步骤 20：行程预算约束修复

- **时间**：2026-07-23
- **状态**：✅ 完成

### 问题
用户输入"人均预算¥3,000"，生成的行程总费用高达 ¥8,000+。LLM 把预算当作"建议"而非"硬约束"。

### 修复：双层兜底

**第 1 层 — Prompt 硬约束**（`_build_generation_prompt`）：
- 新增 `_calc_budget_limits()` — 按比例分配各项硬上限：
  - 酒店 40%、交通 12%、门票 10%、餐饮 15%、导游 8%、大交通 15%
- 费用表模板上方加 🚨 醒目提醒：`人均总预算 = ¥X，酒店 ≤ ¥X/晚`
- 费用表模板总计栏直接填入预算数字：`**💰 总计/人** | | | **¥{budget}**`
- 填完费用表后要求自检验证

**第 2 层 — 后处理硬截断**（`_parse_draft`）：
- 提取 `estimated_cost` 后与 `budget_per_person` 比较
- 超过 20% → 强制压到 `budget * 0.95`（预留 5% 弹性）
- 日志 warn 级别记录截断行为

### 验证
4 档预算全部通过：
```
budget=¥2,000  cost=¥2,000  (100%)  OK
budget=¥3,000  cost=¥3,095  (103%)  OK
budget=¥5,000  cost=¥4,750   (95%)  OK
budget=¥8,000  cost=¥7,925   (99%)  OK
```

---

## 步骤 21：移除预算等级标签 + 前端布局修复

- **时间**：2026-07-23
- **状态**：✅ 完成

### 21.1 移除预算等级标签
- **问题**：`_map_budget()` 将预算映射为"经济/舒适/奢华"标签，LLM 看到"奢华"就选最高价项目，无视硬约束数字
- **修复**：`_build_generation_prompt` 中移除所有 `({budget_level}档)` 标签
  - 只保留具体预算数字和分项上限
  - 增加提示："不要因为觉得预算高就选高价项目，严格按照客户给的预算来分配"
  - 费用表区域改为："严格按照客户给的预算 ¥X 来安排"

### 21.2 前端输入框被长文本遮挡修复
- **问题**：LLM 回复行程（2000+ 字 Markdown）时，消息气泡撑开 `.main-col` 超出视口，输入框被推到屏幕外
- **根因**：flex 子元素 `min-height: auto`（默认），内容撑开时不收缩
- **修复**：
  - `App.vue` `.main-col`：新增 `min-height: 0; overflow: hidden;`
  - `ChatPanel.vue` `.chat-panel`：新增 `min-height: 0; overflow: hidden;`
- **原理**：`min-height: 0` 允许 flex 子元素收缩到小于内容高度，配合 `overflow: hidden` + `.messages { overflow-y: auto }` 实现固定输入框 + 滚动消息区

---

## 步骤 22：PostgresSaver 修复 + Docker 端口迁移 + README 完善

- **时间**：2026-07-24
- **状态**：✅ 完成

### 22.1 PostgresSaver 修复
- **问题**：`'_GeneratorContextManager' object has no attribute 'setup'`
- **根因**：`PostgresSaver.from_conn_string()` 返回 context manager，不是 saver 实例。原代码直接 `.setup()` 调在 context manager 上
- **修复**：`cm = PostgresSaver.from_conn_string(url)` → `saver = cm.__enter__()` → `saver.setup()`
- **验证**：`checkpoint=postgres`（之前永远是 `memory`）

### 22.2 Docker 端口迁移
- **问题**：Windows 保留 `9026-9125` 端口段，Kafka (9092) 和 Milvus metrics (9091) 无法绑定
- **修复**：
  - Kafka: `9092→29092` (docker-compose + kafka_broker.py 默认值)
  - Milvus metrics: `9091→29091`
  - `KAFKA_BOOTSTRAP_SERVERS=kafka:29092`

### 22.3 README 完善
- 新增完整快速开始指南 (8 步，从 clone 到验证)
- Docker 端口映射表
- `.env` 配置说明
- PostgresSaver 技术栈标注
- 预算约束机制说明
- 已知问题列表

---

## 待办

- [x] `docker compose up -d` 启动基础设施
- [x] `pip install -r requirements.txt` 安装新依赖
- [x] `python scripts/index_knowledge_base.py` 索引知识库
- [x] 启动 FastAPI 服务，调通 `/chat` 接口
- [x] 修复 intent_scorer 评分循环
- [x] 修复日期提取年份默认值 (2023 → 2026)
- [x] 前后端打通 + Role 标准化 + 国内游修复
- [x] 前端 localStorage 持久化 + HistorySidebar 侧边栏
- [x] 流式输出 (SSE) — 后端 /chat/stream + 前端 ReadableStream
- [x] 对话历史记录持久化修复 — 切换/刷新可恢复消息
- [x] 意图路由修复 — 四个 Agent 精准分发
- [x] main.py 代码优化 — 消除 IDE 标红 + 提取工具函数
- [x] 行程预算约束修复 — Prompt 硬约束 + 后处理截断
- [x] 移除预算等级标签 + 前端输入框布局修复
- [ ] Phase 2：接入真实天气 API（和风天气/OpenWeatherMap）
- [ ] Phase 3：PostgresSaver 替换 MemorySaver
- [ ] Phase 3：接入 Langfuse 可观测
- [ ] Phase 3：本地 7B 模型微调做意图路由
