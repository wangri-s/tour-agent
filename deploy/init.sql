-- =============================================================================
-- tour-agent 长时记忆 MySQL 初始化
-- 同步创建于 deploy/init.sql，MySQL 容器首次启动自动执行
-- =============================================================================

CREATE DATABASE IF NOT EXISTS tourai
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE tourai;

-- -------------------------------------------------------------------------
-- 1. 会话记录 (Conversation Memory)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS conversations (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(64)     NOT NULL COMMENT '会话唯一标识',
    customer_id     VARCHAR(64)     NOT NULL COMMENT '客户标识',
    channel         VARCHAR(32)     NOT NULL DEFAULT 'web' COMMENT '渠道: web/wechat/whatsapp/messenger/tiktok',
    language        VARCHAR(10)     NOT NULL DEFAULT 'zh' COMMENT '语言偏好',
    role            VARCHAR(16)     NOT NULL COMMENT '角色: user/assistant/system/tool',
    content         TEXT            NOT NULL COMMENT '消息内容',
    branch          VARCHAR(32)     DEFAULT NULL COMMENT '当前 Agent 分支',
    intent_scores   JSON            DEFAULT NULL COMMENT '意图分类分数',
    metadata_json   JSON            DEFAULT NULL COMMENT '扩展元数据',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',

    INDEX idx_session   (session_id),
    INDEX idx_customer  (customer_id),
    INDEX idx_created   (created_at),
    INDEX idx_channel   (channel)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息记录';

-- -------------------------------------------------------------------------
-- 2. 客户画像 (User Profile Memory)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS customer_profiles (
    id                  BIGINT          AUTO_INCREMENT PRIMARY KEY,
    customer_id         VARCHAR(64)     NOT NULL UNIQUE COMMENT '客户唯一标识',
    name                VARCHAR(128)    DEFAULT '' COMMENT '客户名称',
    nationality         VARCHAR(64)     DEFAULT '' COMMENT '国籍',
    preferred_language  VARCHAR(10)     DEFAULT 'zh' COMMENT '首选语言',
    contact_email       VARCHAR(256)    DEFAULT '' COMMENT '邮箱',
    contact_phone       VARCHAR(32)     DEFAULT '' COMMENT '电话',
    preferences_json    JSON            DEFAULT NULL COMMENT '偏好: {budget_range, pace, themes, dietary, ...}',
    travel_history_json JSON            DEFAULT NULL COMMENT '历史行程摘要',
    total_bookings      INT             DEFAULT 0 COMMENT '累计订单数',
    total_spent         DECIMAL(12,2)   DEFAULT 0 COMMENT '累计消费 CNY',
    tags                JSON            DEFAULT NULL COMMENT '标签: [luxury, family, solo, ...]',
    first_seen_at       DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '首次接触',
    last_seen_at        DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近活动',
    notes               TEXT            DEFAULT NULL COMMENT '内部备注',

    INDEX idx_nationality (nationality),
    INDEX idx_last_seen   (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户画像';

-- -------------------------------------------------------------------------
-- 3. 行程记录 (Trip Memory)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trips (
    id                  BIGINT          AUTO_INCREMENT PRIMARY KEY,
    trip_uid            VARCHAR(64)     NOT NULL UNIQUE COMMENT '行程唯一标识',
    customer_id         VARCHAR(64)     NOT NULL COMMENT '客户标识',
    session_id          VARCHAR(64)     DEFAULT '' COMMENT '关联会话',
    status              VARCHAR(32)     NOT NULL DEFAULT 'draft' COMMENT '状态: draft/confirmed/paid/in_progress/completed/cancelled',
    version             INT             DEFAULT 1 COMMENT '修订版本',
    destination         VARCHAR(128)    NOT NULL COMMENT '目的地',
    days                INT             NOT NULL COMMENT '天数',
    arrival_date        DATE            DEFAULT NULL COMMENT '抵达日期',
    pax                 INT             DEFAULT 1 COMMENT '人数',
    budget_per_person   DECIMAL(10,2)   DEFAULT 0 COMMENT '人均预算 CNY',
    theme               VARCHAR(64)     DEFAULT '' COMMENT '主题偏好',
    pace                VARCHAR(32)     DEFAULT '' COMMENT '节奏偏好',
    special_requests    TEXT            DEFAULT NULL COMMENT '特殊需求',
    itinerary_md        MEDIUMTEXT      DEFAULT NULL COMMENT 'Markdown 行程正文',
    estimated_cost      DECIMAL(10,2)   DEFAULT 0 COMMENT '预估人均费用',
    weather_summary     VARCHAR(256)    DEFAULT '' COMMENT '天气摘要',
    highlights_json     JSON            DEFAULT NULL COMMENT '每日亮点',
    quote_json          JSON            DEFAULT NULL COMMENT '报价明细',
    feedback            TEXT            DEFAULT NULL COMMENT '客户反馈',
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_customer  (customer_id),
    INDEX idx_session   (session_id),
    INDEX idx_status    (status),
    INDEX idx_dest      (destination),
    INDEX idx_created   (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行程记录';

-- -------------------------------------------------------------------------
-- 4. Agent 事件流 (Event Memory — Kafka 的备份/查询)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_events (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    event_id        VARCHAR(64)     NOT NULL UNIQUE COMMENT '事件唯一 ID (Kafka offset)',
    event_type      VARCHAR(64)     NOT NULL COMMENT '事件类型: intent_detected/trip_generated/quote_created/human_handoff/...',
    session_id      VARCHAR(64)     NOT NULL,
    customer_id     VARCHAR(64)     NOT NULL,
    agent_name      VARCHAR(64)     DEFAULT '' COMMENT '触发 Agent',
    payload_json    JSON            NOT NULL COMMENT '事件负载',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_session   (session_id),
    INDEX idx_type      (event_type),
    INDEX idx_created   (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 事件流';

-- -------------------------------------------------------------------------
-- 5. FAQ 反馈 (RAG 质量跟踪)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS faq_feedback (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    query           VARCHAR(512)    NOT NULL COMMENT '用户查询',
    retrieved_docs  JSON            DEFAULT NULL COMMENT '检索到的文档 IDs + scores',
    was_helpful     BOOLEAN         DEFAULT NULL COMMENT '是否有帮助',
    user_feedback   TEXT            DEFAULT NULL COMMENT '用户文字反馈',
    session_id      VARCHAR(64)     DEFAULT '',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_helpful (was_helpful),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='FAQ/RAG 质量反馈';

-- -------------------------------------------------------------------------
-- 6. 知识库文档 (文档元数据管理)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_docs (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    doc_uid         VARCHAR(128)    NOT NULL UNIQUE COMMENT '文档唯一标识',
    title           VARCHAR(256)    NOT NULL COMMENT '文档标题',
    category        VARCHAR(64)     DEFAULT '' COMMENT '分类: visa/city/food/transport/culture/emergency',
    source_file     VARCHAR(512)    DEFAULT '' COMMENT '源文件路径',
    chunk_count     INT             DEFAULT 0 COMMENT '切片数量',
    milvus_collection VARCHAR(128)  DEFAULT 'travel_knowledge' COMMENT 'Milvus 集合名',
    status          VARCHAR(32)     DEFAULT 'active' COMMENT '状态: active/outdated/archived',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_category (category),
    INDEX idx_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库文档元数据';
