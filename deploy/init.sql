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
-- 6. 中期记忆摘要 (隔 N 轮压缩持久化)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS session_summaries (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(64)     NOT NULL COMMENT '关联会话',
    round_range     VARCHAR(32)     NOT NULL COMMENT '轮次范围: 1-5, 6-10, 历史',
    summary         TEXT            NOT NULL COMMENT '压缩后的摘要文本',
    round_count     INT             DEFAULT 0 COMMENT '压缩时已完成的轮次数',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_session (session_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中期记忆摘要 (Redis 热备, 过期恢复)';

-- -------------------------------------------------------------------------
-- 7. 知识库文档 (文档元数据管理)
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

-- -------------------------------------------------------------------------
-- 8. 旅游套餐 (Tour Packages — Sales Agent 使用)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tour_packages (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    package_id      VARCHAR(32)     NOT NULL UNIQUE COMMENT '套餐编号 (PKG-001)',
    name            VARCHAR(256)    NOT NULL COMMENT '套餐名称',
    city            VARCHAR(128)    NOT NULL COMMENT '目的地城市',
    days            INT             NOT NULL COMMENT '行程天数',
    nights          INT             NOT NULL COMMENT '住宿晚数',
    budget_min      DECIMAL(10,2)   NOT NULL COMMENT '人均最低预算(CNY)',
    budget_max      DECIMAL(10,2)   NOT NULL COMMENT '人均最高预算(CNY)',
    hotel_level     VARCHAR(32)     NOT NULL COMMENT '酒店档次: 青旅/三星/四星/五星/特色民宿/温泉酒店',
    package_level   VARCHAR(32)     NOT NULL COMMENT '套餐等级: 经济版/标准版/奢华版',
    themes          VARCHAR(256)    DEFAULT '' COMMENT '主题标签(逗号分隔): 文化,美食,自然,摄影,亲子,蜜月,商务,滑雪,温泉',
    highlights      TEXT            COMMENT '行程亮点',
    inclusions      JSON            COMMENT '包含项目(JSON)',
    exclusions      TEXT            COMMENT '不含项目',
    suitable_for    VARCHAR(256)    COMMENT '适合人群',
    min_pax         INT             DEFAULT 1 COMMENT '最少成团人数',
    season_note     VARCHAR(256)    DEFAULT '' COMMENT '季节说明',
    book_days       INT             DEFAULT 7 COMMENT '建议提前预订天数',
    cover_desc      TEXT            COMMENT '套餐简介(用于RAG检索)',
    status          VARCHAR(32)     DEFAULT 'active' COMMENT '状态: active/inactive/sold_out',
    stock           INT             DEFAULT 999 COMMENT '库存',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_city   (city),
    INDEX idx_days   (days),
    INDEX idx_budget (budget_min, budget_max),
    INDEX idx_level  (package_level),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='旅游套餐产品库';

-- 初始化 20 条套餐数据
INSERT INTO tour_packages (package_id, name, city, days, nights, budget_min, budget_max, hotel_level, package_level, themes, highlights, inclusions, exclusions, suitable_for, min_pax, season_note, book_days, cover_desc) VALUES
('PKG-001','帝都风华·北京5日文化深度游','北京',5,4,3500,5000,'四星','标准版','文化,历史,亲子','故宫VIP+长城缆车+国博特展+胡同非遗+颐和园泛舟','["4晚四星酒店","机场接送","4早餐+3正餐(全聚德烤鸭+东来顺涮肉+仿膳)","持证导游","景点门票+VIP通道","旅行保险"]','大交通,个人购物,小费','首次来华游客,家庭出游,历史文化爱好者',2,'',15,'北京5天4晚文化深度游，故宫VIP+长城+国博+颐和园，含全聚德烤鸭宴'),
('PKG-002','长城星夜·北京3日尊享之旅','北京',3,2,5000,8000,'五星','奢华版','文化,蜜月,商务','长城私享日落+故宫VIP夜游+颐和安缦SPA+劳斯莱斯接送+私拍摄影','["2晚五星行政套房(颐和安缦/文华东方)","劳斯莱斯/迈巴赫专车","2早餐+2米其林正餐+长城私宴","金牌私人导游","VIP通道+闭馆特权","旅行保险+医疗运送"]','大交通,个人购物','高端商务,蜜月旅行,企业贵宾',1,'',30,'北京3天2晚奢华体验，长城私享日落香槟+故宫闭馆VIP夜游+劳斯莱斯接送'),
('PKG-003','背包北京·4日青春穷游','北京',4,3,800,1500,'青旅','经济版','文化,历史,学生','故宫学生票+免费日景点+地铁通勤+小吃扫街+清华北大校园','["3晚青旅床位(鼓楼/南锣鼓巷)","机场快线+交通卡50元","手绘美食地图+穷游攻略","学生票代预约","基础旅行保险"]','大交通,正餐,导游','学生,背包客,青年旅舍爱好者',1,'',7,'北京4天3晚青春穷游，青旅+地铁+学生票+免费景点+小吃扫街'),
('PKG-004','秦砖汉瓦·西安4日历史探秘','西安',4,3,2500,4000,'四星','标准版','文化,历史,美食','兵马俑VR+城墙骑行+陕历博VIP+华清宫长恨歌+回民街美食','["3晚四星酒店(钟楼附近)","机场/高铁接送","3早餐+2正餐(羊肉泡馍+biangbiang面)","持证导游","所有景点门票","城墙自行车","旅行保险"]','大交通,购物,自费演出票','历史文化爱好者,研学旅行,摄影爱好者',2,'',20,'西安4天3晚历史探秘，兵马俑+华清宫+陕历博VIP+城墙骑行+回民街美食'),
('PKG-005','天府食韵·成都3日美食之旅','成都',3,2,1800,3000,'特色民宿','标准版','美食,文化,休闲','熊猫基地VIP+川菜博物馆学做菜+盖碗茶+川剧变脸+苍蝇馆子','["2晚宽窄巷子精品民宿","机场/高铁接送","2早餐+1火锅宴+1小吃宴","持证导游+美食向导","熊猫基地+川菜博物馆","旅行保险"]','大交通,自费餐饮,购物','美食爱好者,情侣闺蜜游',2,'',7,'成都3天2晚美食之旅，熊猫基地+川菜博物馆+火锅宴+川剧变脸VIP'),
('PKG-006','巴适得很·成都5日慢生活','成都',5,4,2800,4500,'四星','标准版','文化,美食,自然,深度游','熊猫基地+都江堰青城山+乐山大佛+三星堆+九眼桥','["4晚四星酒店(春熙路/太古里)","机场/高铁+乐山峨眉高铁","4早餐+2正餐+1火锅宴","持证导游","所有景点门票","旅行保险"]','大交通,部分正餐,购物','深度游爱好者,文化美食兼得型,退休人群',2,'',10,'成都5天4晚慢生活深度游，都江堰+乐山大佛+三星堆+火锅+盖碗茶'),
('PKG-007','上海摩登·4日都市风情','上海',4,3,3000,5000,'四星','标准版','都市,购物,亲子','外滩游轮+上海中心观光+迪士尼全天+豫园+法租界CityWalk','["3晚四星酒店(外滩/南京路)","机场/高铁接送","3早餐+2正餐(南翔小笼包+本帮菜)","持证导游","景点门票+迪士尼快速通行","旅行保险"]','大交通,购物,部分正餐','都市体验者,购物爱好者,家庭亲子',2,'',14,'上海4天3晚都市风情，外滩+上海中心+迪士尼+法租界City Walk'),
('PKG-008','魔都之巅·上海3日奢华商务','上海',3,2,6000,10000,'五星','奢华版','商务,购物,蜜月','丽思卡尔顿+黄浦江游艇晚宴+上海中心VIP+私人导购+米其林三星','["2晚五星行政套房(丽思卡尔顿/和平饭店)","奔驰S级专车+司导","2早餐+米其林三星+游艇晚宴","金牌私人管家","景点VIP+购物私人导购","旅行保险+医疗运送"]','大交通,购物消费','商务考察,企业高管,投资考察团',1,'',14,'上海3天2晚奢华商务，丽思卡尔顿+黄浦江游艇晚宴+米其林+私人导购'),
('PKG-009','山水画卷·桂林阳朔4日','桂林',4,3,2000,3500,'四星+民宿','标准版','自然,摄影,蜜月','漓江竹筏+十里画廊骑行+龙脊梯田+印象刘三姐+遇龙河','["2晚桂林四星+1晚阳朔民宿","机场/高铁+桂林阳朔车票","3早餐+1农家宴+1啤酒鱼宴","持证导游","景点门票+演出票","旅行保险"]','大交通,自费餐饮,购物','自然风光爱好者,摄影爱好者,蜜月旅行',2,'',7,'桂林阳朔4天3晚山水画卷，漓江竹筏+龙脊梯田+印象刘三姐+骑行'),
('PKG-010','七彩云南·昆明大理丽江8日','云南',8,7,4000,7000,'四星+精品客栈','标准版','自然,文化,摄影,蜜月','石林+洱海环湖+玉龙雪山+蓝月谷+白沙扎染','["7晚住宿(昆明2+大理2+丽江3)","昆明大理丽江高铁","7早餐+3正餐","持证导游(各地分段)","所有景点门票+玉龙雪山大索道","旅行保险"]','大交通,部分正餐,购物','自然爱好者,文艺青年,蜜月旅行',2,'',15,'云南8天7晚昆明大理丽江全景，洱海+玉龙雪山+丽江古城+过桥米线'),
('PKG-011','江南水乡·杭州苏州4日','杭州+苏州',4,3,2200,3800,'四星','标准版','文化,园林,美食','西湖全景+灵隐寺+龙井采茶+拙政园+苏州博物馆','["2晚杭州+1晚苏州四星","机场/高铁+杭州苏州高铁","3早餐+2正餐(西湖醋鱼/松鼠桂鱼)","持证导游","所有景点门票","旅行保险"]','大交通,部分正餐,购物','园林爱好者,中老年游客,文化体验者',2,'',7,'杭州苏州4天3晚江南水乡，西湖+灵隐寺+龙井采茶+拙政园'),
('PKG-012','山城魔幻·重庆3日','重庆',3,2,1500,2500,'四星','标准版','美食,城市,自然','洪崖洞夜景+长江索道+武隆天生三桥+磁器口+李子坝','["2晚四星酒店(解放碑附近)","机场/高铁+武隆往返","2早餐+1正宗老火锅","持证导游","所有景点门票","旅行保险"]','大交通,部分正餐,购物','美食爱好者,城市探险者',2,'',7,'重庆3天2晚魔幻山城，洪崖洞+武隆天生三桥+李子坝+老火锅'),
('PKG-013','冰雪奇缘·哈尔滨4日','哈尔滨',4,3,2800,4500,'四星','标准版','冰雪,亲子,摄影','冰雪大世界+亚布力滑雪+中央大街+东北虎林园+铁锅炖','["3晚四星酒店(中央大街)","机场/高铁+亚布力往返","3早餐+1铁锅炖+1俄式西餐","持证导游+滑雪教练","景点门票+雪具","旅行保险"]','大交通,滑雪服租赁','冰雪体验者,南方游客,家庭亲子',2,'冬季限定(12月-2月)',20,'哈尔滨4天3晚冰雪奇缘，冰雪大世界+亚布力滑雪+中央大街+铁锅炖'),
('PKG-014','世界之巅·拉萨5日朝圣','拉萨',5,4,3500,6000,'四星','标准版','文化,朝圣,摄影','布达拉宫VIP+大昭寺+纳木错+羊卓雍措+色拉寺辩经','["4晚四星供氧酒店","机场接送+景区交通","4早餐+1藏式火锅+1尼泊尔餐","持证导游+藏族文化讲解","景点门票+布达拉宫VIP","氧气瓶+高原药品","旅行保险(含高原反应)"]','大交通,个人消费','文化朝圣者,摄影爱好者,深度旅行者',2,'高原3650m需适应',20,'拉萨5天4晚朝圣之旅，布达拉宫VIP+纳木错+羊卓雍措+色拉寺+藏式火锅'),
('PKG-015','丝绸之路·西安兰州敦煌8日','西安+兰州+敦煌',8,7,5000,8000,'四星','标准版','文化,历史,摄影,探险','兵马俑+七彩丹霞+嘉峪关+莫高窟+鸣沙山+沙漠露营','["7晚四星/当地最好酒店","全程高铁+专车","7早餐+4正餐(牛肉面/手抓羊肉/驴肉黄面)","持证导游(各地分段)","所有景点门票+莫高窟特窟","沙漠露营+骑骆驼","旅行保险"]','大交通,购物','历史文化重度爱好者,摄影家,探险者',2,'',30,'丝绸之路8天7晚西安兰州敦煌，兵马俑+莫高窟+嘉峪关+沙漠露营'),
('PKG-016','闽南风情·厦门3日轻旅行','厦门',3,2,1500,2500,'四星','标准版','文化,美食,文艺','鼓浪屿全天+南普陀+厦门大学+环岛路骑行+海鲜宴','["2晚四星酒店(中山路/轮渡)","机场/高铁+鼓浪屿船票","2早餐+1海鲜宴","持证导游","所有景点门票","旅行保险"]','大交通,购物','文艺青年,周末度假,轻旅行爱好者',2,'',7,'厦门3天2晚闽南风情，鼓浪屿+南普陀+厦大+环岛路骑行+沙茶面'),
('PKG-017','南国风情·广州深圳4日','广州+深圳',4,3,2000,3500,'四星','标准版','美食,亲子,都市','陈家祠+珠江夜游+长隆野生动物世界+世界之窗+深圳湾','["2晚广州+1晚深圳四星","机场/高铁+广深高铁","3早餐+1早茶宴+1粤菜正餐","持证导游","景点门票+长隆","旅行保险"]','大交通,购物','美食探索者,家庭亲子,商务休闲',2,'',7,'广州深圳4天3晚南国风情，早茶+长隆+世界之窗+珠江夜游'),
('PKG-018','仙境探秘·张家界3日','张家界',3,2,1800,3000,'四星','标准版','自然,探险,摄影','袁家界悬浮山+天门山玻璃栈道+大峡谷玻璃桥+黄龙洞','["2晚四星酒店(武陵源)","机场/高铁接送","2早餐+1土家宴","持证导游","景点门票+索道+电梯","旅行保险"]','大交通,自费项目,购物','自然探险者,摄影爱好者,阿凡达粉丝',2,'',10,'张家界3天2晚仙境探秘，袁家界+天门山玻璃栈道+大峡谷玻璃桥'),
('PKG-019','北国风光·长白山4日','长白山',4,3,3000,5000,'四星+温泉酒店','标准版','自然,温泉,滑雪,避暑','天池+长白瀑布+火山温泉+朝鲜族民俗村+峡谷','["3晚温泉酒店(含温泉)","机场/高铁+景区交通","3早餐+2正餐(朝鲜族料理/铁锅炖)","持证导游","景点门票+环保车+温泉","旅行保险"]','大交通,滑雪雪具(冬季)','自然爱好者,温泉养生,避暑/滑雪',2,'全年(夏避暑/冬滑雪)',14,'长白山4天3晚北国风光，天池+火山温泉+朝鲜族民俗+滑雪(冬季)'),
('PKG-020','大美新疆·北疆喀纳斯7日','新疆',7,6,4500,7500,'四星+特色木屋','标准版','自然,摄影,探险','天山天池+可可托海+喀纳斯湖+禾木晨雾+五彩滩+魔鬼城','["6晚住宿(乌鲁木齐2+可可托海1+喀纳斯木屋2+布尔津1)","全程7座商务车+司机","6早餐+4正餐(烤全羊/大盘鸡/手抓饭)","持证导游","景点门票+区间车","边境通行证代办","旅行保险"]','大交通,骑马/自费','自然摄影爱好者,自驾替代,深度探险者',3,'6-10月限定',30,'新疆北疆喀纳斯7天6晚大美之旅，天山天池+喀纳斯+禾木+烤全羊');
