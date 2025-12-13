# 数据库设计

> 模块: Database Design
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 数据库选型

### 1.1 技术栈

| 数据库 | 用途 | 版本 |
|--------|------|------|
| **PostgreSQL** | 主数据库 (业务数据) | 16.x |
| **TimescaleDB** | 时序数据 (指标、历史) | 2.x |
| **Redis** | 缓存、队列、实时状态 | 7.x |

### 1.2 数据分类

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Data Classification                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PostgreSQL (主数据库)                                                   │
│  ├── 业务实体: 赎回请求、审批工单、资产配置                               │
│  ├── 交易记录: 申购、赎回、调仓历史                                       │
│  ├── 用户数据: 持仓、权限、偏好                                          │
│  └── 系统配置: 参数、规则、阈值                                          │
│                                                                          │
│  TimescaleDB (时序数据)                                                  │
│  ├── 每日快照: NAV、AUM、流动性层级                                       │
│  ├── 风险指标: 实时风控指标历史                                          │
│  ├── 性能指标: 系统性能监控数据                                          │
│  └── 事件日志: 链上事件处理记录                                          │
│                                                                          │
│  Redis (缓存与实时)                                                      │
│  ├── 实时状态: 当前NAV、流动性、风险等级                                  │
│  ├── 会话缓存: JWT、用户会话                                             │
│  ├── 去重数据: 已处理事件ID                                              │
│  ├── 任务队列: Celery 任务数据                                           │
│  └── 分布式锁: 调仓执行锁                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. PostgreSQL Schema

### 2.1 核心业务表

#### 2.1.1 赎回请求表

```sql
-- 赎回请求表
CREATE TABLE redemption_requests (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 链上数据
    request_id NUMERIC(78) NOT NULL UNIQUE,  -- uint256
    tx_hash VARCHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    log_index INTEGER NOT NULL,

    -- 请求信息
    owner VARCHAR(42) NOT NULL,
    receiver VARCHAR(42) NOT NULL,
    shares NUMERIC(78) NOT NULL,
    gross_amount NUMERIC(78) NOT NULL,
    locked_nav NUMERIC(78) NOT NULL,
    estimated_fee NUMERIC(78) NOT NULL,

    -- 时间信息
    request_time TIMESTAMP WITH TIME ZONE NOT NULL,
    settlement_time TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 状态信息
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    channel VARCHAR(20) NOT NULL,  -- STANDARD, EMERGENCY, SCHEDULED
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    window_id NUMERIC(78),

    -- 结算信息 (结算后填充)
    actual_fee NUMERIC(78),
    net_amount NUMERIC(78),
    settlement_tx_hash VARCHAR(66),
    settled_at TIMESTAMP WITH TIME ZONE,

    -- 审批信息
    approval_ticket_id VARCHAR(50),
    approved_by VARCHAR(42),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejected_by VARCHAR(42),
    rejected_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,

    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT chk_status CHECK (status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'SETTLED', 'CANCELLED', 'REJECTED')),
    CONSTRAINT chk_channel CHECK (channel IN ('STANDARD', 'EMERGENCY', 'SCHEDULED'))
);

-- 索引
CREATE INDEX idx_redemption_owner ON redemption_requests(owner);
CREATE INDEX idx_redemption_status ON redemption_requests(status);
CREATE INDEX idx_redemption_channel ON redemption_requests(channel);
CREATE INDEX idx_redemption_settlement_time ON redemption_requests(settlement_time);
CREATE INDEX idx_redemption_request_time ON redemption_requests(request_time);
CREATE INDEX idx_redemption_requires_approval ON redemption_requests(requires_approval) WHERE requires_approval = TRUE;
CREATE UNIQUE INDEX idx_redemption_tx ON redemption_requests(tx_hash, log_index);
```

#### 2.1.2 审批工单表

```sql
-- 审批工单表
CREATE TABLE approval_tickets (
    -- 主键
    id VARCHAR(50) PRIMARY KEY,

    -- 工单类型
    ticket_type VARCHAR(30) NOT NULL,
    reference_type VARCHAR(30) NOT NULL,
    reference_id VARCHAR(100) NOT NULL,

    -- 请求信息
    requester VARCHAR(42) NOT NULL,
    amount NUMERIC(78),
    description TEXT,
    request_data JSONB,
    risk_assessment JSONB,

    -- 状态
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    required_approvals INTEGER NOT NULL DEFAULT 1,
    current_approvals INTEGER NOT NULL DEFAULT 0,
    current_rejections INTEGER NOT NULL DEFAULT 0,

    -- SLA
    sla_warning TIMESTAMP WITH TIME ZONE NOT NULL,
    sla_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    escalated_at TIMESTAMP WITH TIME ZONE,
    escalated_to TEXT[],

    -- 结果
    result VARCHAR(20),
    result_reason TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(42),

    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT chk_ticket_status CHECK (status IN ('PENDING', 'PARTIALLY_APPROVED', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED')),
    CONSTRAINT chk_ticket_result CHECK (result IN ('APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED') OR result IS NULL)
);

-- 审批记录表
CREATE TABLE approval_records (
    id VARCHAR(50) PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL REFERENCES approval_tickets(id),
    approver VARCHAR(42) NOT NULL,
    action VARCHAR(10) NOT NULL,  -- APPROVE, REJECT
    reason TEXT,
    signature VARCHAR(132),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chk_action CHECK (action IN ('APPROVE', 'REJECT'))
);

-- 索引
CREATE INDEX idx_ticket_status ON approval_tickets(status);
CREATE INDEX idx_ticket_type ON approval_tickets(ticket_type);
CREATE INDEX idx_ticket_reference ON approval_tickets(reference_type, reference_id);
CREATE INDEX idx_ticket_sla_deadline ON approval_tickets(sla_deadline);
CREATE INDEX idx_ticket_requester ON approval_tickets(requester);
CREATE INDEX idx_approval_record_ticket ON approval_records(ticket_id);
```

#### 2.1.3 资产配置表

```sql
-- 资产配置表
CREATE TABLE asset_configs (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 资产信息
    token_address VARCHAR(42) NOT NULL UNIQUE,
    token_symbol VARCHAR(20) NOT NULL,
    token_name VARCHAR(100),
    decimals SMALLINT NOT NULL DEFAULT 18,

    -- 配置信息
    tier VARCHAR(20) NOT NULL,  -- L1, L2, L3
    target_allocation NUMERIC(10, 6) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- 购买配置
    purchase_adapter VARCHAR(42),
    purchase_method VARCHAR(10) DEFAULT 'AUTO',
    max_slippage INTEGER DEFAULT 200,  -- bps
    min_purchase_amount NUMERIC(78),
    subscription_start TIMESTAMP WITH TIME ZONE,
    subscription_end TIMESTAMP WITH TIME ZONE,

    -- 元数据
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    added_tx_hash VARCHAR(66),
    removed_at TIMESTAMP WITH TIME ZONE,
    removed_tx_hash VARCHAR(66),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT chk_tier CHECK (tier IN ('L1', 'L2', 'L3')),
    CONSTRAINT chk_purchase_method CHECK (purchase_method IN ('OTC', 'SWAP', 'AUTO'))
);

-- 索引
CREATE INDEX idx_asset_tier ON asset_configs(tier);
CREATE INDEX idx_asset_active ON asset_configs(is_active);
```

#### 2.1.4 调仓记录表

```sql
-- 调仓记录表
CREATE TABLE rebalance_history (
    -- 主键
    id VARCHAR(50) PRIMARY KEY,

    -- 触发信息
    trigger_type VARCHAR(20) NOT NULL,  -- SCHEDULED, THRESHOLD, LIQUIDITY, EVENT, MANUAL
    triggered_by VARCHAR(42),

    -- 状态
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    -- 调仓前后状态
    pre_state JSONB NOT NULL,
    target_state JSONB NOT NULL,
    post_state JSONB,

    -- 调仓动作
    actions JSONB NOT NULL,  -- [{type, fromLayer, toLayer, amount, ...}]

    -- 执行信息
    estimated_gas_cost NUMERIC(78),
    actual_gas_cost NUMERIC(78),
    estimated_slippage NUMERIC(10, 6),
    actual_slippage NUMERIC(10, 6),

    -- 审批信息
    requires_approval BOOLEAN DEFAULT FALSE,
    approval_ticket_id VARCHAR(50),

    -- 执行结果
    executed_at TIMESTAMP WITH TIME ZONE,
    executed_by VARCHAR(42),
    execution_results JSONB,

    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT chk_rebalance_status CHECK (status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', 'COMPLETED', 'FAILED', 'CANCELLED'))
);

-- 索引
CREATE INDEX idx_rebalance_status ON rebalance_history(status);
CREATE INDEX idx_rebalance_trigger ON rebalance_history(trigger_type);
CREATE INDEX idx_rebalance_created ON rebalance_history(created_at);
```

#### 2.1.5 交易记录表

```sql
-- 通用交易记录表
CREATE TABLE transactions (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 链上信息
    tx_hash VARCHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    log_index INTEGER NOT NULL,
    block_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 交易类型
    event_type VARCHAR(50) NOT NULL,
    contract_address VARCHAR(42) NOT NULL,

    -- 交易参与方
    from_address VARCHAR(42),
    to_address VARCHAR(42),

    -- 金额信息
    token_address VARCHAR(42),
    amount NUMERIC(78),
    shares NUMERIC(78),
    fee NUMERIC(78),

    -- 原始数据
    raw_data JSONB,

    -- 元数据
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT uq_transaction UNIQUE (tx_hash, log_index)
);

-- 索引
CREATE INDEX idx_tx_event_type ON transactions(event_type);
CREATE INDEX idx_tx_from ON transactions(from_address);
CREATE INDEX idx_tx_to ON transactions(to_address);
CREATE INDEX idx_tx_block ON transactions(block_number);
CREATE INDEX idx_tx_timestamp ON transactions(block_timestamp);
```

### 2.2 风险与监控表

#### 2.2.1 风险事件表

```sql
-- 风险事件表
CREATE TABLE risk_events (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 事件信息
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,  -- info, warning, critical
    metric_name VARCHAR(50) NOT NULL,

    -- 阈值与实际值
    threshold_value NUMERIC(38, 18),
    actual_value NUMERIC(38, 18),

    -- 描述
    message TEXT NOT NULL,
    details JSONB,

    -- 解决状态
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(42),
    resolution_note TEXT,

    -- 通知状态
    notified BOOLEAN DEFAULT FALSE,
    notified_at TIMESTAMP WITH TIME ZONE,
    notification_channels TEXT[],

    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 约束
    CONSTRAINT chk_severity CHECK (severity IN ('info', 'warning', 'critical'))
);

-- 索引
CREATE INDEX idx_risk_event_type ON risk_events(event_type);
CREATE INDEX idx_risk_severity ON risk_events(severity);
CREATE INDEX idx_risk_resolved ON risk_events(resolved);
CREATE INDEX idx_risk_created ON risk_events(created_at);
```

### 2.3 审计日志表

```sql
-- 审计日志表
CREATE TABLE audit_logs (
    -- 主键
    id BIGSERIAL PRIMARY KEY,

    -- 操作信息
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),

    -- 操作者
    actor_address VARCHAR(42),
    actor_role VARCHAR(50),
    actor_ip VARCHAR(45),
    actor_user_agent TEXT,

    -- 变更内容
    old_value JSONB,
    new_value JSONB,

    -- 元数据
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_actor ON audit_logs(actor_address);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- 分区 (按月)
-- 建议在生产环境中使用分区表
```

---

## 3. TimescaleDB 时序表

### 3.1 每日快照表

```sql
-- 启用 TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 每日快照表
CREATE TABLE daily_snapshots (
    -- 时间键
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 基金状态
    total_assets NUMERIC(78) NOT NULL,
    total_supply NUMERIC(78) NOT NULL,
    share_price NUMERIC(78) NOT NULL,

    -- 流动性层级
    layer1_value NUMERIC(78) NOT NULL,
    layer2_value NUMERIC(78) NOT NULL,
    layer3_value NUMERIC(78) NOT NULL,
    layer1_ratio NUMERIC(10, 6) NOT NULL,
    layer2_ratio NUMERIC(10, 6) NOT NULL,
    layer3_ratio NUMERIC(10, 6) NOT NULL,

    -- 负债
    total_redemption_liability NUMERIC(78) NOT NULL,
    total_locked_shares NUMERIC(78) NOT NULL,

    -- 状态
    emergency_mode BOOLEAN NOT NULL DEFAULT FALSE,

    -- 费用
    accumulated_management_fees NUMERIC(78),
    accumulated_performance_fees NUMERIC(78),
    accumulated_redemption_fees NUMERIC(78),

    PRIMARY KEY (snapshot_time)
);

-- 转换为超表
SELECT create_hypertable('daily_snapshots', 'snapshot_time');

-- 保留策略 (保留2年数据)
SELECT add_retention_policy('daily_snapshots', INTERVAL '2 years');

-- 压缩策略 (30天后压缩)
ALTER TABLE daily_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = ''
);
SELECT add_compression_policy('daily_snapshots', INTERVAL '30 days');
```

### 3.2 资产持仓快照表

```sql
-- 资产持仓快照表
CREATE TABLE asset_holdings_snapshots (
    -- 时间键
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 资产信息
    token_address VARCHAR(42) NOT NULL,
    token_symbol VARCHAR(20) NOT NULL,
    tier VARCHAR(10) NOT NULL,

    -- 持仓数据
    balance NUMERIC(78) NOT NULL,
    price NUMERIC(38, 18) NOT NULL,
    value_usd NUMERIC(38, 18) NOT NULL,
    allocation_pct NUMERIC(10, 6) NOT NULL,

    PRIMARY KEY (snapshot_time, token_address)
);

-- 转换为超表
SELECT create_hypertable('asset_holdings_snapshots', 'snapshot_time');

-- 保留策略
SELECT add_retention_policy('asset_holdings_snapshots', INTERVAL '1 year');
```

### 3.3 风险指标时序表

```sql
-- 风险指标时序表
CREATE TABLE risk_metrics_series (
    -- 时间键
    metric_time TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 流动性指标
    l1_ratio NUMERIC(10, 6),
    l1_l2_ratio NUMERIC(10, 6),
    redemption_coverage NUMERIC(10, 6),

    -- 价格指标
    nav NUMERIC(38, 18),
    nav_change_24h NUMERIC(10, 6),

    -- 集中度指标
    max_asset_concentration NUMERIC(10, 6),
    top3_concentration NUMERIC(10, 6),

    -- 赎回指标
    pending_redemption_count INTEGER,
    pending_redemption_amount NUMERIC(78),
    daily_redemption_rate NUMERIC(10, 6),

    -- 综合评分
    risk_score INTEGER,
    risk_level VARCHAR(20),

    PRIMARY KEY (metric_time)
);

-- 转换为超表
SELECT create_hypertable('risk_metrics_series', 'metric_time');

-- 保留策略 (90天详细数据)
SELECT add_retention_policy('risk_metrics_series', INTERVAL '90 days');

-- 连续聚合 (按小时)
CREATE MATERIALIZED VIEW risk_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', metric_time) AS bucket,
    AVG(l1_ratio) AS avg_l1_ratio,
    MIN(l1_ratio) AS min_l1_ratio,
    AVG(nav) AS avg_nav,
    MAX(risk_score) AS max_risk_score
FROM risk_metrics_series
GROUP BY bucket;

-- 刷新策略
SELECT add_continuous_aggregate_policy('risk_metrics_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

### 3.4 事件处理记录表

```sql
-- 事件处理记录表
CREATE TABLE event_processing_logs (
    -- 时间键
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 事件信息
    tx_hash VARCHAR(66) NOT NULL,
    log_index INTEGER NOT NULL,
    block_number BIGINT NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    contract_address VARCHAR(42) NOT NULL,

    -- 处理状态
    status VARCHAR(20) NOT NULL,  -- SUCCESS, FAILED, SKIPPED
    processing_time_ms INTEGER,
    error_message TEXT,

    -- 重试信息
    retry_count INTEGER DEFAULT 0,

    PRIMARY KEY (processed_at, tx_hash, log_index)
);

-- 转换为超表
SELECT create_hypertable('event_processing_logs', 'processed_at');

-- 保留策略 (7天)
SELECT add_retention_policy('event_processing_logs', INTERVAL '7 days');
```

---

## 4. Redis 数据结构

### 4.1 实时状态缓存

```redis
# 基金概览缓存
fund:overview
{
  "totalAssets": "12345678000000000000000000",
  "totalSupply": "11728645000000000000000000",
  "sharePrice": "1052300000000000000",
  "layer1Liquidity": "1234567800000000000000000",
  "layer2Liquidity": "3703703400000000000000000",
  "layer3Value": "7407406800000000000000000",
  "emergencyMode": false,
  "lastUpdated": "2024-12-13T12:34:56Z"
}
TTL: 60s

# 当前风险状态
risk:status
{
  "level": "NORMAL",
  "score": 15,
  "lastUpdated": "2024-12-13T12:34:56Z"
}
TTL: 60s

# 资产价格缓存
asset:price:{token_address}
{
  "price": "1.0000",
  "source": "oracle",
  "updatedAt": "2024-12-13T12:34:56Z"
}
TTL: 300s
```

### 4.2 去重与进度

```redis
# 已处理事件 (去重)
event:processed:{tx_hash}:{log_index}
Value: "1"
TTL: 7d

# 检查点 (断点续传)
checkpoint:{contract_address}
Value: "12345678"  # 最后处理的区块号
TTL: None (持久)

# 处理进度
progress:event_listener
{
  "lastBlock": 12345678,
  "lastProcessedAt": "2024-12-13T12:34:56Z",
  "eventsProcessed": 12345
}
TTL: None
```

### 4.3 分布式锁

```redis
# 调仓执行锁
lock:rebalance:execute
Value: "{worker_id}"
TTL: 300s (5分钟)

# 审批处理锁
lock:approval:{ticket_id}
Value: "{worker_id}"
TTL: 60s
```

### 4.4 任务队列 (Celery)

```redis
# Celery 任务数据 (使用 Redis 作为 Broker)
celery                  # 默认队列
celery:high             # 高优先级队列
celery:low              # 低优先级队列

# Celery 任务结果 (使用 Redis 作为 Backend)
celery-task-meta-{task_id}
{
  "status": "SUCCESS",
  "result": {...},
  "traceback": null,
  "task_id": "xxx-xxx-xxx"
}
TTL: 86400s (1天)

# Celery Beat 调度
celery-beat-schedule    # 定时任务调度表
```

#### Celery 配置

```python
# app/celery_config.py
from celery import Celery

celery_app = Celery(
    'paimon',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_default_queue='celery',
    task_queues={
        'high': {'exchange': 'high', 'routing_key': 'high'},
        'low': {'exchange': 'low', 'routing_key': 'low'},
    },
    task_default_retry_delay=60,
    task_max_retries=3,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

---

## 5. 数据迁移

### 5.1 SQLAlchemy ORM 模型

```python
# app/models/base.py
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Index, Integer,
    Numeric, String, Text, UniqueConstraint, ForeignKey,
    JSON, ARRAY, CheckConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# app/models/redemption.py
class RedemptionRequest(Base):
    """赎回请求表"""
    __tablename__ = "redemption_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 链上数据
    request_id: Mapped[Decimal] = mapped_column(Numeric(78, 0), unique=True, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # 请求信息
    owner: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    receiver: Mapped[str] = mapped_column(String(42), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    locked_nav: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    estimated_fee: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)

    # 时间信息
    request_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settlement_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # 状态信息
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    window_id: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)

    # 结算信息
    actual_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    settlement_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 审批信息
    approval_ticket_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint('tx_hash', 'log_index', name='uq_redemption_tx'),
        CheckConstraint(
            "status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'SETTLED', 'CANCELLED', 'REJECTED')",
            name='chk_status'
        ),
        CheckConstraint(
            "channel IN ('STANDARD', 'EMERGENCY', 'SCHEDULED')",
            name='chk_channel'
        ),
    )


# app/models/approval.py
class ApprovalTicket(Base):
    """审批工单表"""
    __tablename__ = "approval_tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # 工单类型
    ticket_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # 请求信息
    requester: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False, index=True)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_approvals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_rejections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # SLA
    sla_warning: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_to: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # 结果
    result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关联
    records: Mapped[list["ApprovalRecord"]] = relationship(
        "ApprovalRecord", back_populates="ticket", lazy="selectin"
    )

    __table_args__ = (
        Index('idx_ticket_reference', 'reference_type', 'reference_id'),
        CheckConstraint(
            "status IN ('PENDING', 'PARTIALLY_APPROVED', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED')",
            name='chk_ticket_status'
        ),
    )


class ApprovalRecord(Base):
    """审批记录表"""
    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(50), ForeignKey('approval_tickets.id'), nullable=False, index=True
    )
    approver: Mapped[str] = mapped_column(String(42), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(132), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    # 关联
    ticket: Mapped["ApprovalTicket"] = relationship(
        "ApprovalTicket", back_populates="records"
    )

    __table_args__ = (
        CheckConstraint("action IN ('APPROVE', 'REJECT')", name='chk_action'),
    )
```

### 5.2 迁移命令 (Alembic)

```bash
# 初始化 Alembic
alembic init alembic

# 创建迁移
alembic revision --autogenerate -m "init"

# 应用迁移 (生产)
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

---

## 6. 数据备份与恢复

### 6.1 备份策略

| 数据库 | 备份频率 | 保留时间 | 方式 |
|--------|----------|----------|------|
| PostgreSQL | 每日全量 + 每小时增量 | 30天 | pg_dump + WAL |
| TimescaleDB | 每日 | 90天 | pg_dump |
| Redis | 每小时 RDB + AOF | 7天 | RDB + AOF |

### 6.2 备份脚本

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups

# PostgreSQL 全量备份
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -F c -f $BACKUP_DIR/pg_$DATE.dump

# Redis RDB 备份
redis-cli -h $REDIS_HOST BGSAVE
cp /var/lib/redis/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# 上传到 S3
aws s3 cp $BACKUP_DIR s3://paimon-backups/$DATE/ --recursive

# 清理旧备份
find $BACKUP_DIR -mtime +7 -delete
```

---

## 7. 性能优化

### 7.1 索引优化建议

```sql
-- 复合索引 (常用查询)
CREATE INDEX idx_redemption_status_time
ON redemption_requests(status, settlement_time)
WHERE status IN ('PENDING', 'PENDING_APPROVAL');

-- 部分索引 (减少索引大小)
CREATE INDEX idx_ticket_pending
ON approval_tickets(sla_deadline)
WHERE status = 'PENDING';

-- 覆盖索引 (避免回表)
CREATE INDEX idx_asset_holdings_cover
ON asset_holdings_snapshots(snapshot_time, token_address)
INCLUDE (balance, value_usd, allocation_pct);
```

### 7.2 查询优化

```sql
-- 使用 EXPLAIN ANALYZE 分析查询
EXPLAIN ANALYZE
SELECT * FROM redemption_requests
WHERE status = 'PENDING'
AND settlement_time BETWEEN NOW() AND NOW() + INTERVAL '7 days';

-- 分页查询使用游标
SELECT * FROM redemption_requests
WHERE id > :last_id
ORDER BY id
LIMIT 100;
```

### 7.3 连接池配置

```python
# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

# 数据库连接配置
DATABASE_URL = "postgresql://user:password@localhost:5432/paimon"

# 创建引擎 (带连接池配置)
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 最大溢出连接数
    pool_timeout=30,        # 获取连接超时时间 (秒)
    pool_recycle=1800,      # 连接回收时间 (秒)
    pool_pre_ping=True,     # 检查连接是否存活
    echo=False,             # SQL 日志
)

# 创建会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# 依赖注入
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 异步版本 (使用 asyncpg)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

ASYNC_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/paimon"

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    bind=async_engine,
)


async def get_async_db():
    """获取异步数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
```

---

*下一节: [07-permission-management.md](./07-permission-management.md) - 权限管理设计*
