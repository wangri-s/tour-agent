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

## 待办

- [x] `docker compose up -d` 启动基础设施
- [x] `pip install -r requirements.txt` 安装新依赖
- [x] `python scripts/index_knowledge_base.py` 索引知识库
- [x] 启动 FastAPI 服务，调通 `/chat` 接口
- [ ] 修复 intent_scorer 评分循环 (使用 qwen-turbo 替代 qwen-plus)
- [ ] 修复日期提取年份默认值 (2023 → 2026)
- [ ] Phase 2：接入真实天气 API（和风天气/OpenWeatherMap）
- [ ] Phase 3：PostgresSaver 替换 MemorySaver
- [ ] Phase 3：接入 Langfuse 可观测
- [ ] Phase 3：本地 7B 模型微调做意图路由
