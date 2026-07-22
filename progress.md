# 项目进度记录

## 步骤 1：仓库创建与连接
- **时间**：2026-07-22
- **操作**：在 GitHub 创建空仓库 `wangri-s/tour-agent`，clone 到本地 `e:\Desktop\ai\旅游多agent`
- **状态**：✅ 完成

## 步骤 2：项目骨架搭建
- **时间**：2026-07-22
- **操作**：按设计文档创建六层目录结构，55 个文件
- **详情**：见 [implementation-plan.md](implementation-plan.md)
- **状态**：✅ 完成

### 2.1 graph/ 编排层（17 文件）
- [x] `state.py` — OverallState + TripNeed + TripDraft + Quote 模型
- [x] `builder.py` — LangGraph StateGraph 组装（13 节点 + 条件边）
- [x] `routing.py` — 5 个条件边路由函数
- [x] `nodes/input_guard.py` — 入参保护（截断 + PII 脱敏）
- [x] `nodes/session_context.py` — 会话初始化
- [x] `nodes/intent_router.py` — 意图路由器
- [x] `nodes/customer_service.py` — 智能客服节点
- [x] `nodes/sales_agent.py` — 销售 Agent 节点
- [x] `nodes/operations_agent.py` — 运营 Agent 节点
- [x] `nodes/trip_planner.py` — 旅游定制节点
- [x] `nodes/intent_scorer.py` — 意向评分节点
- [x] `nodes/revision_loop.py` — 修订计数器
- [x] `nodes/quote_agent.py` — 报价节点
- [x] `nodes/human_handoff.py` — 人工接管节点
- [x] `nodes/operations_sync.py` — 终态汇聚节点

### 2.2 agents/ 业务 Agent 层（8 文件）
- [x] `base.py` — BaseAgent 抽象基类
- [x] `intent_router.py` — 意图路由器 Agent
- [x] `customer_service.py` — 智能客服 Agent
- [x] `sales_agent.py` — 销售 Agent
- [x] `operations_agent.py` — 运营 Agent
- [x] `trip_planner.py` — 旅游定制 Agent
- [x] `intent_scorer.py` — 意向评分 Agent
- [x] `quote_agent.py` — 报价 Agent

### 2.3 tools/ 工具层（8 文件）
- [x] `search_faq.py` — FAQ 检索
- [x] `check_handoff.py` — 转人工评估
- [x] `get_weather.py` — 天气查询
- [x] `query_calendar.py` — 节假日查询
- [x] `query_inventory.py` — 库存查询
- [x] `quote_price.py` — 报价计算
- [x] `update_crm.py` — CRM 写入
- [x] `send_capi.py` — CAPI 事件回传

### 2.4 prompts/ 提示词层（7 文件）
- [x] `intent_router.py` — 意图路由 prompt
- [x] `customer_service.py` — 客服 prompt
- [x] `sales_agent.py` — 销售 prompt
- [x] `operations_agent.py` — 运营 prompt
- [x] `trip_planner.py` — 定制 prompt
- [x] `intent_scorer.py` — 评分 prompt
- [x] `quote_agent.py` — 报价 prompt

### 2.5 services/ 服务层（4 文件）
- [x] `llm_gateway.py` — LLM 网关
- [x] `database.py` — 数据库抽象
- [x] `cache.py` — Redis 缓存
- [x] `message_queue.py` — 消息队列

### 2.6 根目录配置（5 文件）
- [x] `main.py` — FastAPI `/chat` 入口
- [x] `requirements.txt` — 依赖清单
- [x] `.env.example` — 环境变量模板
- [x] `.gitignore` — Git 忽略规则
- [x] `README.md` — 项目说明

### 2.7 tests/ 测试层（2 文件）
- [x] `test_state.py` — State 模型 + 路由逻辑单元测试

## 步骤 3：推送到 GitHub
- **时间**：2026-07-22
- **操作**：`git add -A` → `git commit` → `git push -u origin main`
- **状态**：✅ 完成

---

## 待办

- [ ] MVP 阶段：安装依赖，跑通 `/chat` 接口
- [ ] MVP 阶段：接入真实 OpenAI API，验证意图路由 + 客服 + 定制三条链路
- [ ] Phase 2：接入向量库 (Milvus/pgvector) 做 FAQ RAG
- [ ] Phase 2：接入真实天气 API 与库存 API
- [ ] Phase 3：PostgresSaver 替换 MemorySaver
- [ ] Phase 3：接入 Langfuse 可观测
