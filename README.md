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
```

## 项目结构

```
tour-agent/
├── main.py                  # FastAPI 入口 /chat
├── graph/                   # LangGraph 编排层
│   ├── state.py             # State 定义 (OverallState + Pydantic 模型)
│   ├── builder.py           # Graph Builder (节点 + 条件边组装)
│   ├── routing.py           # 条件边路由函数
│   └── nodes/               # 13 个节点实现
├── agents/                  # 业务 Agent 实现
│   ├── base.py              # Agent 基类
│   ├── intent_router.py     # 意图路由器
│   ├── customer_service.py  # 智能客服
│   ├── sales_agent.py       # 销售 Agent
│   ├── operations_agent.py  # 运营 Agent
│   ├── trip_planner.py      # 旅游定制 Agent
│   ├── intent_scorer.py     # 意向评分 Agent
│   └── quote_agent.py       # 报价 Agent
├── tools/                   # LangChain Tools
│   ├── search_faq.py        # FAQ 检索
│   ├── check_handoff.py     # 转人工评估
│   ├── get_weather.py       # 天气查询
│   ├── query_calendar.py    # 节假日查询
│   ├── query_inventory.py   # 库存查询
│   ├── quote_price.py       # 报价计算
│   ├── update_crm.py        # CRM 写入
│   └── send_capi.py         # CAPI 事件回传
├── services/                # 外部依赖
│   ├── llm_gateway.py       # LLM 网关
│   ├── database.py          # 数据库
│   ├── cache.py             # Redis 缓存
│   └── message_queue.py     # 消息队列
├── prompts/                 # System Prompts
├── tests/                   # 单元测试
├── requirements.txt
├── .env.example
└── .gitignore
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY

# 启动服务
python main.py

# 测试
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "customer_id": "c-001",
    "channel": "web",
    "message": "我想去北京玩5天，两个人，预算每人8000",
    "language": "zh"
  }'
```

## 四个 Agent 分支

| 分支 | 职责 | 关键词 |
|------|------|--------|
| `customer_service` | FAQ、签证、退改、订单查询 | 退款、签证、政策 |
| `sales_agent` | 产品推介、报价、签约引导 | 报价、多少钱、预订 |
| `operations_agent` | 商家入驻、履约、工单 | 入驻、工单、审核 |
| `trip_planner` | 行程定制、天气/日历/库存 | 去X玩、几天、行程 |

## 落地路线

- **MVP**: 客服 + 定制双分支，GPT-4o-mini 路由，MemorySaver
- **Phase 2**: RAG 知识库，真实天气/库存 API，跨会话记忆
- **Phase 3**: 四分支全开，PostgresSaver，Langfuse 可观测，本地 7B 路由

## License

MIT
