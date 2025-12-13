# 事件监听模块设计

> 模块: Event Listener
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 模块概述

### 1.1 职责

事件监听模块是后端系统的**数据入口**，负责：
- 实时监听 BSC 链上合约事件
- 解析事件数据并持久化
- 触发下游业务流程
- 保证事件处理的可靠性和幂等性

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **实时性** | 事件从出块到处理完成 < 30秒 |
| **可靠性** | 断点续传，不丢失任何事件 |
| **幂等性** | 重复处理相同事件不产生副作用 |
| **可扩展** | 支持水平扩展处理能力 |

---

## 2. 监听的事件清单

### 2.1 PNGYVault 合约事件

| 事件 | 签名 | 优先级 | 处理逻辑 |
|------|------|--------|----------|
| `DepositProcessed` | `DepositProcessed(address indexed sender, address indexed receiver, uint256 assets, uint256 shares)` | 🟢 Normal | 记录申购、更新用户持仓、更新 AUM |
| `SharesLocked` | `SharesLocked(address indexed owner, uint256 shares)` | 🟢 Normal | 更新用户锁定份额 |
| `SharesUnlocked` | `SharesUnlocked(address indexed owner, uint256 shares)` | 🟢 Normal | 更新用户锁定份额 |
| `SharesBurned` | `SharesBurned(address indexed owner, uint256 shares)` | 🟢 Normal | 更新用户持仓、总供应量 |
| `RedemptionFeeAdded` | `RedemptionFeeAdded(uint256 fee)` | 🟢 Normal | 更新手续费统计 |
| `NavUpdated` | `NavUpdated(uint256 oldNav, uint256 newNav, uint256 timestamp)` | 🟡 High | 记录 NAV 历史、触发再平衡检查 |
| `EmergencyModeChanged` | `EmergencyModeChanged(bool enabled)` | 🔴 Critical | 触发紧急预案、通知管理员 |

### 2.2 RedemptionManager 合约事件

| 事件 | 签名 | 优先级 | 处理逻辑 |
|------|------|--------|----------|
| `RedemptionRequested` | `RedemptionRequested(uint256 indexed requestId, address indexed owner, address receiver, uint256 shares, uint256 lockedAmount, uint256 estimatedFee, RedemptionChannel channel, bool requiresApproval, uint256 settlementTime, uint256 windowId)` | 🟡 High | 创建赎回记录、创建审批工单(如需要)、更新流动性预测 |
| `RedemptionSettled` | `RedemptionSettled(uint256 indexed requestId, address indexed owner, address receiver, uint256 grossAmount, uint256 fee, uint256 netAmount, RedemptionChannel channel)` | 🟢 Normal | 更新赎回状态、记录结算、更新用户持仓 |
| `RedemptionApproved` | `RedemptionApproved(uint256 indexed requestId, address indexed approver, uint256 settlementTime)` | 🟢 Normal | 更新审批状态、记录审批历史 |
| `RedemptionRejected` | `RedemptionRejected(uint256 indexed requestId, address indexed rejector, string reason)` | 🟢 Normal | 更新审批状态、通知用户 |
| `RedemptionCancelled` | `RedemptionCancelled(uint256 indexed requestId, address indexed owner)` | 🟢 Normal | 更新赎回状态 |
| `LowLiquidityAlert` | `LowLiquidityAlert(uint256 currentRatio, uint256 threshold, uint256 available, uint256 total)` | 🔴 Critical | 触发流动性预警、通知运营 |
| `CriticalLiquidityAlert` | `CriticalLiquidityAlert(uint256 currentRatio, uint256 threshold, uint256 available)` | 🔴 Critical | 触发紧急预案、暂停新赎回 |

### 2.3 AssetController 合约事件

| 事件 | 签名 | 优先级 | 处理逻辑 |
|------|------|--------|----------|
| `AssetAdded` | `AssetAdded(address indexed token, LiquidityTier tier, uint256 allocation)` | 🟢 Normal | 更新资产配置表 |
| `AssetRemoved` | `AssetRemoved(address indexed token)` | 🟢 Normal | 更新资产配置表 |
| `AssetAllocationUpdated` | `AssetAllocationUpdated(address indexed token, uint256 oldAllocation, uint256 newAllocation)` | 🟢 Normal | 更新资产配置表 |
| `AssetPurchased` | `AssetPurchased(address indexed token, LiquidityTier tier, uint256 usdtAmount, uint256 tokensReceived)` | 🟢 Normal | 记录购买交易、更新持仓 |
| `AssetRedeemed` | `AssetRedeemed(address indexed token, LiquidityTier tier, uint256 tokenAmount, uint256 usdtReceived)` | 🟢 Normal | 记录赎回交易、更新持仓 |
| `WaterfallLiquidation` | `WaterfallLiquidation(LiquidityTier tier, address indexed token, uint256 amountLiquidated, uint256 usdtReceived)` | 🟡 High | 记录清算、分析流动性消耗 |
| `BufferPoolRebalanced` | `BufferPoolRebalanced(uint256 oldBuffer, uint256 newBuffer, uint256 targetBuffer)` | 🟢 Normal | 记录缓冲池变化 |
| `ManagementFeeCollected` | `ManagementFeeCollected(uint256 feeAmount, uint256 totalAssets, uint256 period)` | 🟢 Normal | 记录管理费 |
| `PerformanceFeeCollected` | `PerformanceFeeCollected(uint256 feeAmount, uint256 profit, uint256 newHighWaterMark)` | 🟢 Normal | 记录业绩费 |

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Event Listener Architecture                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      BSC Node (RPC/WebSocket)                    │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│                                 ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Event Fetcher                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│  │  │  WebSocket  │  │   Polling   │  │  Fallback   │              │    │
│  │  │  Listener   │  │   Backup    │  │   Handler   │              │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│                                 ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Event Parser                                │    │
│  │  • ABI 解码                                                      │    │
│  │  • 参数校验                                                      │    │
│  │  • 去重检查 (txHash + logIndex)                                  │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│                                 ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Event Queue (Redis)                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│  │  │  Critical   │  │    High     │  │   Normal    │              │    │
│  │  │   Queue     │  │   Queue     │  │   Queue     │              │    │
│  │  │  (优先级0)  │  │  (优先级1)  │  │  (优先级2)  │              │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│         ┌───────────────────────┼───────────────────────┐               │
│         │                       │                       │               │
│         ▼                       ▼                       ▼               │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐         │
│  │   Vault     │        │ Redemption  │        │   Asset     │         │
│  │  Handler    │        │  Handler    │        │  Handler    │         │
│  └──────┬──────┘        └──────┬──────┘        └──────┬──────┘         │
│         │                      │                      │                 │
│         └──────────────────────┼──────────────────────┘                 │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      Downstream Services                         │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                │    │
│  │  │Database │ │  Risk   │ │Approval │ │Notific- │                │    │
│  │  │ Writer  │ │ Control │ │Workflow │ │ ation   │                │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件

#### 3.2.1 Event Fetcher (事件获取器)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ContractAddresses:
    vault: str
    redemption_manager: str
    asset_controller: str

@dataclass
class EventFetcherConfig:
    # RPC 配置
    rpc_url: str
    ws_url: str

    # 合约地址
    contracts: ContractAddresses

    # 监听配置
    start_block: int              # 起始区块
    confirmations: int = 15       # 确认数 (BSC: 15)
    batch_size: int = 1000        # 批量获取大小
    polling_interval: float = 3.0 # 轮询间隔 (秒)

    # 重连配置
    reconnect_attempts: int = 10  # 重连次数
    reconnect_delay: float = 5.0  # 重连延迟 (秒)
```

**获取策略**:
1. **主通道**: WebSocket 实时订阅
2. **备用通道**: HTTP 轮询 (当 WebSocket 断开时)
3. **补漏机制**: 定期扫描确保无遗漏

#### 3.2.2 Event Parser (事件解析器)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from enum import Enum

class EventPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"

@dataclass
class ParsedEvent:
    # 元数据
    tx_hash: str
    log_index: int
    block_number: int
    block_timestamp: int

    # 事件数据
    contract_address: str
    event_name: str
    args: dict[str, Any]

    # 处理元数据
    priority: EventPriority
    received_at: datetime
```

**解析流程**:
1. ABI 解码事件日志
2. 类型校验和转换
3. 生成唯一标识 (`${txHash}-${logIndex}`)
4. 查重判断
5. 分配优先级

#### 3.2.3 Event Queue (事件队列)

使用 Celery 实现优先级队列：

```python
from celery import Celery
from kombu import Queue

# Celery 配置
celery_app = Celery('paimon_events')

celery_app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # 任务默认配置
    task_default_retry_delay=1,  # 初始重试延迟 1s
    task_max_retries=3,
    task_acks_late=True,
    # 结果过期
    result_expires=24 * 3600,  # 24小时
)

# 优先级队列配置
celery_app.conf.task_queues = (
    Queue('critical', routing_key='critical'),  # 最高优先级
    Queue('high', routing_key='high'),
    Queue('normal', routing_key='normal'),
)

# 优先级映射
PRIORITY_MAP = {
    EventPriority.CRITICAL: 'critical',
    EventPriority.HIGH: 'high',
    EventPriority.NORMAL: 'normal',
}
```

---

## 4. 事件处理流程

### 4.1 处理流水线

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Event Processing Pipeline                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. Receive (接收)                                                        │
│     └→ 从 WebSocket/HTTP 获取原始日志                                     │
│                                                                           │
│  2. Parse (解析)                                                          │
│     └→ ABI 解码、类型转换、生成唯一ID                                     │
│                                                                           │
│  3. Deduplicate (去重)                                                    │
│     └→ 检查 Redis: `event:${txHash}:${logIndex}`                         │
│     └→ 如已存在则跳过                                                     │
│                                                                           │
│  4. Validate (校验)                                                       │
│     └→ 区块确认数检查 (≥15)                                               │
│     └→ 合约地址白名单检查                                                 │
│                                                                           │
│  5. Enqueue (入队)                                                        │
│     └→ 根据优先级入队                                                     │
│     └→ 标记去重键 (TTL: 7天)                                             │
│                                                                           │
│  6. Process (处理)                                                        │
│     └→ 路由到对应 Handler                                                 │
│     └→ 执行业务逻辑                                                       │
│                                                                           │
│  7. Persist (持久化)                                                      │
│     └→ 写入数据库                                                         │
│     └→ 更新处理进度                                                       │
│                                                                           │
│  8. Trigger (触发)                                                        │
│     └→ 触发下游服务                                                       │
│     └→ 发送通知(如需要)                                                   │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Handler 示例

#### RedemptionRequested Handler

```python
import structlog
from datetime import datetime, timedelta
from celery import shared_task
from decimal import Decimal

from app.services.redemption import RedemptionService
from app.services.approval import ApprovalService
from app.services.notification import NotificationService
from app.services.risk import RiskService
from app.models.event import ParsedEvent

logger = structlog.get_logger()

# 通道映射
CHANNEL_MAP = {0: 'STANDARD', 1: 'EMERGENCY', 2: 'SCHEDULED'}

def map_channel(channel: int) -> str:
    return CHANNEL_MAP.get(channel, 'UNKNOWN')

def calculate_sla(channel: int) -> datetime:
    """计算 SLA 截止时间: 紧急通道 4 小时，标准通道 24 小时"""
    hours = 4 if channel == 1 else 24
    return datetime.utcnow() + timedelta(hours=hours)


@shared_task(bind=True, queue='high', max_retries=3)
def handle_redemption_requested(self, event_data: dict):
    """处理 RedemptionRequested 事件"""
    event = ParsedEvent(**event_data)
    args = event.args

    request_id = args['requestId']
    owner = args['owner']
    receiver = args['receiver']
    shares = args['shares']
    locked_amount = args['lockedAmount']
    estimated_fee = args['estimatedFee']
    channel = args['channel']
    requires_approval = args['requiresApproval']
    settlement_time = args['settlementTime']
    window_id = args.get('windowId')

    # 初始化服务
    redemption_service = RedemptionService()
    approval_service = ApprovalService()
    notification_service = NotificationService()
    risk_service = RiskService()

    try:
        # 1. 创建赎回记录
        redemption = redemption_service.create(
            request_id=int(request_id),
            owner=owner,
            receiver=receiver,
            shares=Decimal(shares),
            gross_amount=Decimal(locked_amount),
            estimated_fee=Decimal(estimated_fee),
            channel=map_channel(channel),
            requires_approval=requires_approval,
            settlement_time=datetime.fromtimestamp(int(settlement_time)),
            window_id=int(window_id) if window_id else None,
            tx_hash=event.tx_hash,
            block_number=event.block_number,
            status='PENDING_APPROVAL' if requires_approval else 'PENDING',
        )

        # 2. 如需审批，创建工单
        if requires_approval:
            approval_service.create_ticket(
                ticket_type='REDEMPTION',
                reference_id=str(request_id),
                requester=owner,
                amount=Decimal(locked_amount),
                channel=map_channel(channel),
                sla_deadline=calculate_sla(channel),
            )

            # 通知审批人
            notification_service.notify_approvers(
                notification_type='NEW_REDEMPTION_APPROVAL',
                request_id=str(request_id),
                amount=locked_amount,
                channel=map_channel(channel),
                requester=owner,
            )

        # 3. 更新流动性预测
        risk_service.update_liquidity_forecast(
            expected_outflow=Decimal(locked_amount),
            settlement_time=datetime.fromtimestamp(int(settlement_time)),
        )

        # 4. 记录日志
        logger.info(
            'Redemption request processed',
            request_id=str(request_id),
            owner=owner,
            amount=str(locked_amount),
            channel=map_channel(channel),
            requires_approval=requires_approval,
        )

    except Exception as exc:
        logger.error('Failed to process redemption request', error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

---

## 5. 可靠性保障

### 5.1 断点续传

```python
from abc import ABC, abstractmethod
from typing import Optional
import redis.asyncio as redis

class CheckpointManager(ABC):
    """检查点管理抽象类"""

    @abstractmethod
    async def save_checkpoint(self, contract_address: str, block_number: int) -> None:
        """保存检查点"""
        pass

    @abstractmethod
    async def get_checkpoint(self, contract_address: str) -> Optional[int]:
        """获取检查点"""
        pass

    @abstractmethod
    async def get_all_checkpoints(self) -> dict[str, int]:
        """批量获取所有检查点"""
        pass


class RedisCheckpointManager(CheckpointManager):
    """Redis 实现的检查点管理器"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.prefix = "checkpoint:"

    async def save_checkpoint(self, contract_address: str, block_number: int) -> None:
        key = f"{self.prefix}{contract_address}"
        await self.redis.set(key, str(block_number))

    async def get_checkpoint(self, contract_address: str) -> Optional[int]:
        key = f"{self.prefix}{contract_address}"
        value = await self.redis.get(key)
        return int(value) if value else None

    async def get_all_checkpoints(self) -> dict[str, int]:
        pattern = f"{self.prefix}*"
        keys = await self.redis.keys(pattern)
        result = {}
        for key in keys:
            address = key.decode().replace(self.prefix, "")
            value = await self.redis.get(key)
            if value:
                result[address] = int(value)
        return result

# 存储在 Redis
# Key: checkpoint:${contractAddress}
# Value: blockNumber (string)
# 每处理100个事件或每5秒保存一次
```

### 5.2 去重机制

```python
from abc import ABC, abstractmethod
from datetime import datetime
import redis.asyncio as redis

class DeduplicationService(ABC):
    """去重服务抽象类"""

    @abstractmethod
    async def is_processed(self, tx_hash: str, log_index: int) -> bool:
        """检查是否已处理"""
        pass

    @abstractmethod
    async def mark_processed(self, tx_hash: str, log_index: int) -> None:
        """标记已处理"""
        pass


class RedisDeduplicationService(DeduplicationService):
    """Redis 实现的去重服务"""

    TTL_DAYS = 7

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.prefix = "event:processed:"

    def _get_key(self, tx_hash: str, log_index: int) -> str:
        return f"{self.prefix}{tx_hash}:{log_index}"

    async def is_processed(self, tx_hash: str, log_index: int) -> bool:
        key = self._get_key(tx_hash, log_index)
        return await self.redis.exists(key) > 0

    async def mark_processed(self, tx_hash: str, log_index: int) -> None:
        key = self._get_key(tx_hash, log_index)
        timestamp = datetime.utcnow().isoformat()
        await self.redis.setex(key, self.TTL_DAYS * 24 * 3600, timestamp)

# Redis 实现
# Key: event:processed:${txHash}:${logIndex}
# Value: timestamp
# TTL: 7 days
```

### 5.3 重试策略

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class RetryConfig:
    attempts: int = 3
    initial_delay: float = 1.0     # 初始延迟 1s
    max_delay: float = 30.0        # 最大延迟 30s
    backoff_type: Literal['exponential', 'linear'] = 'exponential'

    # 可重试的错误类型
    retryable_errors: tuple = (
        'NETWORK_ERROR',
        'TIMEOUT',
        'DATABASE_BUSY',
    )

    # 不可重试的错误类型
    non_retryable_errors: tuple = (
        'INVALID_EVENT',
        'DUPLICATE_EVENT',
        'VALIDATION_ERROR',
    )

    def get_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.backoff_type == 'exponential':
            delay = self.initial_delay * (2 ** attempt)
        else:
            delay = self.initial_delay * (attempt + 1)
        return min(delay, self.max_delay)


# 默认重试配置
RETRY_CONFIG = RetryConfig()
```

### 5.4 监控告警

| 指标 | 阈值 | 告警级别 |
|------|------|----------|
| 事件延迟 | > 60s | Warning |
| 事件延迟 | > 300s | Critical |
| 队列堆积 | > 1000 | Warning |
| 队列堆积 | > 5000 | Critical |
| 处理失败率 | > 1% | Warning |
| 处理失败率 | > 5% | Critical |
| WebSocket 断开 | > 30s | Warning |

---

## 6. 配置参考

### 6.1 环境变量

```bash
# RPC 配置
BSC_RPC_URL=https://bsc-dataseed.binance.org
BSC_WS_URL=wss://bsc-ws-node.nariox.org

# 合约地址
VAULT_ADDRESS=0x...
REDEMPTION_MANAGER_ADDRESS=0x...
ASSET_CONTROLLER_ADDRESS=0x...

# 监听配置
EVENT_START_BLOCK=12345678
EVENT_CONFIRMATIONS=15
EVENT_BATCH_SIZE=1000
EVENT_POLLING_INTERVAL=3000

# Redis 配置
REDIS_URL=redis://localhost:6379

# 重试配置
RETRY_ATTEMPTS=3
RETRY_DELAY=1000
```

### 6.2 合约 ABI

确保导入以下事件的 ABI：

```python
import json
from pathlib import Path
from web3 import Web3

# 从合约编译产物导入
def load_abi(filename: str) -> list:
    abi_path = Path(__file__).parent / 'abis' / filename
    with open(abi_path) as f:
        return json.load(f)

VAULT_ABI = load_abi('PNGYVault.json')
REDEMPTION_MANAGER_ABI = load_abi('RedemptionManager.json')
ASSET_CONTROLLER_ABI = load_abi('AssetController.json')

# 提取事件 ABI
def extract_event_abis(abi: list) -> list:
    return [item for item in abi if item.get('type') == 'event']

EVENT_ABIS = (
    extract_event_abis(VAULT_ABI) +
    extract_event_abis(REDEMPTION_MANAGER_ABI) +
    extract_event_abis(ASSET_CONTROLLER_ABI)
)

# 创建事件签名映射
def build_event_signature_map(event_abis: list) -> dict[str, dict]:
    """构建事件签名到 ABI 的映射"""
    w3 = Web3()
    result = {}
    for event_abi in event_abis:
        name = event_abi['name']
        inputs = ','.join(inp['type'] for inp in event_abi.get('inputs', []))
        signature = f"{name}({inputs})"
        topic = w3.keccak(text=signature).hex()
        result[topic] = event_abi
    return result

EVENT_SIGNATURE_MAP = build_event_signature_map(EVENT_ABIS)
```

---

## 7. 测试要点

### 7.1 单元测试

- 事件解析正确性
- 去重逻辑正确性
- Handler 业务逻辑

### 7.2 集成测试

- 端到端事件处理流程
- 断点续传功能
- 重试机制

### 7.3 压力测试

- 高并发事件处理
- 大量历史事件回放
- WebSocket 断开恢复

---

*下一节: [02-rebalance-engine.md](./02-rebalance-engine.md) - 调仓引擎设计*
