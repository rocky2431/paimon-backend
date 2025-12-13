# 调仓引擎设计

> 模块: Rebalance Engine
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 模块概述

### 1.1 职责

调仓引擎负责**基金资产的主动管理**，包括：
- 监控三层流动性配置偏离度
- 计算最优调仓方案
- 执行资产购买/赎回交易
- 管理流动性缓冲池

### 1.2 调仓目标

维持三层流动性的目标配置：

| 层级 | 名称 | 目标占比 | 容忍区间 | 资产类型 |
|------|------|----------|----------|----------|
| L1 | TIER_1_CASH | 10% | 5% - 20% | USDT 现金 |
| L2 | TIER_2_MMF | 30% | 20% - 40% | 货币市场基金 |
| L3 | TIER_3_HYD | 60% | 50% - 70% | 高收益 RWA 资产 |

---

## 2. 调仓触发机制

### 2.1 触发条件

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Rebalance Trigger Conditions                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  1. 定时触发 (Scheduled)                                          │  │
│  │     • 每日 UTC 00:00 检查各层偏离度                               │  │
│  │     • 每周一检查资产配置权重                                       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  2. 阈值触发 (Threshold)                                          │  │
│  │     • 任一层偏离目标 > ±5% 时自动触发                             │  │
│  │     • 单资产占比 > 25% 时触发分散                                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  3. 流动性触发 (Liquidity)                                        │  │
│  │     • L1 < 8% 时从 L2/L3 补充                                     │  │
│  │     • L1 > 15% 时部署多余现金到 L2/L3                             │  │
│  │     • 预测赎回 > 可用流动性时提前变现                             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  4. 事件触发 (Event-driven)                                       │  │
│  │     • 大额申购后 (>100K) 部署新资金                               │  │
│  │     • 资产到期/窗口开放时调整配置                                  │  │
│  │     • 价格显著波动后 (>5%) 重新平衡                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  5. 手动触发 (Manual)                                             │  │
│  │     • 管理员通过后台发起                                          │  │
│  │     • 需通过审批流程                                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 触发规则配置

```python
from dataclasses import dataclass

@dataclass
class ScheduledConfig:
    daily_check: str = '0 0 * * *'     # 每日 UTC 00:00
    weekly_check: str = '0 0 * * 1'    # 每周一 UTC 00:00

@dataclass
class ThresholdsConfig:
    layer_deviation: float = 0.05         # 层级偏离 5%
    asset_concentration: float = 0.25     # 单资产集中度 25%
    top3_concentration: float = 0.60      # 前3资产集中度 60%

@dataclass
class LiquidityConfig:
    l1_min: float = 0.05    # L1 最低 5%
    l1_low: float = 0.08    # L1 低位 8%
    l1_high: float = 0.15   # L1 高位 15%
    l1_max: float = 0.20    # L1 最高 20%

@dataclass
class RebalanceTriggerConfig:
    scheduled: ScheduledConfig = None
    thresholds: ThresholdsConfig = None
    liquidity: LiquidityConfig = None
    min_rebalance_amount: int = 10000    # 10K USDT

    def __post_init__(self):
        if self.scheduled is None:
            self.scheduled = ScheduledConfig()
        if self.thresholds is None:
            self.thresholds = ThresholdsConfig()
        if self.liquidity is None:
            self.liquidity = LiquidityConfig()
```

---

## 3. 调仓策略算法

### 3.1 偏离度计算

```python
from dataclasses import dataclass
from typing import Literal
from decimal import Decimal

@dataclass
class LayerMetrics:
    layer: Literal['L1', 'L2', 'L3']
    current_value: Decimal
    current_ratio: float
    target_ratio: float
    deviation: float          # current_ratio - target_ratio
    deviation_abs: float      # |deviation|
    min_ratio: float
    max_ratio: float
    within_bounds: bool       # min_ratio <= current_ratio <= max_ratio


def calculate_layer_metrics(vault_state) -> list[LayerMetrics]:
    """计算各层级的偏离度指标"""
    total_assets = float(vault_state.total_assets)

    layer_configs = [
        ('L1', vault_state.layer1_liquidity, 0.10, 0.05, 0.20),
        ('L2', vault_state.layer2_liquidity, 0.30, 0.20, 0.40),
        ('L3', vault_state.layer3_value, 0.60, 0.50, 0.70),
    ]

    metrics = []
    for layer, value, target, min_r, max_r in layer_configs:
        current_ratio = float(value) / total_assets if total_assets > 0 else 0
        deviation = current_ratio - target
        metrics.append(LayerMetrics(
            layer=layer,
            current_value=Decimal(str(value)),
            current_ratio=current_ratio,
            target_ratio=target,
            deviation=deviation,
            deviation_abs=abs(deviation),
            min_ratio=min_r,
            max_ratio=max_r,
            within_bounds=min_r <= current_ratio <= max_r,
        ))

    return metrics
```

### 3.2 调仓计划生成

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from enum import Enum
import uuid

class RebalanceActionType(str, Enum):
    TRANSFER = 'TRANSFER'
    PURCHASE = 'PURCHASE'
    REDEEM = 'REDEEM'

class RebalanceMethod(str, Enum):
    OTC = 'OTC'
    SWAP = 'SWAP'
    AUTO = 'AUTO'

class RebalanceTrigger(str, Enum):
    SCHEDULED = 'SCHEDULED'
    THRESHOLD = 'THRESHOLD'
    LIQUIDITY = 'LIQUIDITY'
    EVENT = 'EVENT'
    MANUAL = 'MANUAL'

@dataclass
class RebalanceAction:
    type: RebalanceActionType
    amount: Decimal
    priority: int              # 执行优先级
    reason: str
    from_layer: Optional[Literal['L1', 'L2', 'L3']] = None
    to_layer: Optional[Literal['L1', 'L2', 'L3']] = None
    asset: Optional[str] = None
    method: Optional[RebalanceMethod] = None
    estimated_slippage: Optional[float] = None

@dataclass
class RebalanceState:
    total_assets: Decimal
    l1_ratio: float
    l2_ratio: float
    l3_ratio: float

@dataclass
class RebalancePlan:
    id: str
    created_at: datetime
    trigger: RebalanceTrigger
    pre_state: RebalanceState
    target_state: RebalanceState
    actions: list[RebalanceAction]
    estimated_gas_cost: Decimal
    estimated_slippage: float
    requires_approval: bool
    approval_threshold: Decimal


def generate_rebalance_plan(
    metrics: list[LayerMetrics],
    config: RebalanceTriggerConfig,
    pending_redemptions: Decimal,
) -> RebalancePlan:
    """生成调仓计划"""
    actions: list[RebalanceAction] = []
    total_assets = sum(float(m.current_value) for m in metrics)

    # 获取各层指标
    l1 = next(m for m in metrics if m.layer == 'L1')
    l2 = next(m for m in metrics if m.layer == 'L2')
    l3 = next(m for m in metrics if m.layer == 'L3')

    # 情况1: L1 过低，需要补充
    if l1.current_ratio < config.liquidity.l1_low:
        deficit = (config.liquidity.l1_low - l1.current_ratio) * total_assets

        # 优先从 L2 补充
        if l2.current_ratio > l2.target_ratio:
            transfer_from_l2 = min(
                deficit,
                (l2.current_ratio - l2.target_ratio) * total_assets
            )
            actions.append(RebalanceAction(
                type=RebalanceActionType.TRANSFER,
                from_layer='L2',
                to_layer='L1',
                amount=Decimal(str(int(transfer_from_l2))),
                priority=1,
                reason='L1流动性不足，从L2补充',
            ))
            deficit -= transfer_from_l2

        # L2 不足时从 L3 补充
        if deficit > config.min_rebalance_amount:
            actions.append(RebalanceAction(
                type=RebalanceActionType.REDEEM,
                from_layer='L3',
                to_layer='L1',
                amount=Decimal(str(int(deficit))),
                priority=2,
                reason='L1流动性不足，从L3变现',
            ))

    # 情况2: L1 过高，需要部署
    if l1.current_ratio > config.liquidity.l1_high:
        surplus = (l1.current_ratio - l1.target_ratio) * total_assets

        # 优先部署到 L3 (收益最高)
        if l3.current_ratio < l3.target_ratio:
            deploy_to_l3 = min(
                surplus,
                (l3.target_ratio - l3.current_ratio) * total_assets
            )
            actions.append(RebalanceAction(
                type=RebalanceActionType.PURCHASE,
                from_layer='L1',
                to_layer='L3',
                amount=Decimal(str(int(deploy_to_l3))),
                method=RebalanceMethod.AUTO,
                priority=3,
                reason='L1现金过多，部署到L3增收',
            ))

    # 情况3: 即将到期的赎回需要提前准备
    available_liquidity = l1.current_value + l2.current_value
    if pending_redemptions > available_liquidity * Decimal('0.8'):
        shortfall = pending_redemptions - available_liquidity * Decimal('0.8')
        actions.append(RebalanceAction(
            type=RebalanceActionType.REDEEM,
            from_layer='L3',
            to_layer='L1',
            amount=shortfall,
            priority=0,  # 最高优先级
            reason='预备即将到期的赎回请求',
        ))

    # 计算是否需要审批
    total_action_amount = sum(a.amount for a in actions)
    approval_threshold = Decimal('50000') * Decimal('1e18')  # 50K
    requires_approval = total_action_amount > approval_threshold

    return RebalancePlan(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        trigger=RebalanceTrigger.THRESHOLD,
        pre_state=RebalanceState(
            total_assets=Decimal(str(total_assets)),
            l1_ratio=l1.current_ratio,
            l2_ratio=l2.current_ratio,
            l3_ratio=l3.current_ratio,
        ),
        target_state=RebalanceState(
            total_assets=Decimal(str(total_assets)),
            l1_ratio=0.10,
            l2_ratio=0.30,
            l3_ratio=0.60,
        ),
        actions=actions,
        estimated_gas_cost=estimate_gas_cost(actions),
        estimated_slippage=estimate_slippage(actions),
        requires_approval=requires_approval,
        approval_threshold=approval_threshold,
    )
```

---

## 4. 调仓执行流程

### 4.1 执行流水线

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Rebalance Execution Pipeline                       │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. 生成计划 (Generate Plan)                                              │
│     └→ 计算偏离度、生成调仓动作列表                                        │
│                                                                           │
│  2. 风控检查 (Risk Check) ⚠️                                              │
│     ├→ 滑点预估检查 (>2% 告警, >5% 阻止)                                  │
│     ├→ Gas 成本检查 (>调仓收益10% 跳过)                                   │
│     ├→ 流动性影响检查                                                     │
│     └→ 时间窗口检查 (避开高波动时段)                                       │
│                                                                           │
│  3. 审批流程 (Approval) [金额>50K时]                                      │
│     ├→ 创建审批工单                                                       │
│     ├→ 通知审批人                                                         │
│     └→ 等待审批结果                                                       │
│                                                                           │
│  4. 交易模拟 (Simulation)                                                 │
│     ├→ 使用 eth_call 模拟每个交易                                         │
│     ├→ 验证预期结果                                                       │
│     └→ 模拟失败则中止                                                     │
│                                                                           │
│  5. 执行交易 (Execute)                                                    │
│     ├→ 按优先级顺序执行                                                   │
│     ├→ 等待确认 (15 blocks)                                               │
│     ├→ 验证执行结果                                                       │
│     └→ 单笔失败不影响后续                                                 │
│                                                                           │
│  6. 结果验证 (Verify)                                                     │
│     ├→ 查询链上最新状态                                                   │
│     ├→ 对比预期 vs 实际                                                   │
│     └→ 偏差>1% 则告警                                                     │
│                                                                           │
│  7. 记录存档 (Record)                                                     │
│     ├→ 保存完整执行记录                                                   │
│     ├→ 更新调仓历史                                                       │
│     └→ 发送执行报告                                                       │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 合约调用

```python
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Protocol
from enum import IntEnum

class LiquidityTier(IntEnum):
    L1 = 0
    L2 = 1
    L3 = 2

class AssetControllerCalls(Protocol):
    """AssetController 合约接口"""

    async def allocate_to_layer(
        self, tier: LiquidityTier, amount: Decimal
    ) -> Decimal:
        """向特定层分配资金 (从缓冲池)"""
        ...

    async def purchase_asset(
        self, token: str, usdt_amount: Decimal
    ) -> Decimal:
        """购买资产"""
        ...

    async def redeem_asset(
        self, token: str, token_amount: Decimal
    ) -> Decimal:
        """赎回资产"""
        ...

    async def rebalance_buffer(self) -> None:
        """缓冲池再平衡"""
        ...

    async def execute_waterfall_liquidation(
        self, amount_needed: Decimal, max_tier: LiquidityTier
    ) -> Decimal:
        """瀑布清算 (紧急时使用)"""
        ...
```

### 4.3 执行代码示例

```python
import structlog
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.services.blockchain import BlockchainService
from app.services.simulation import SimulationService
from app.services.notification import NotificationService

logger = structlog.get_logger()

@dataclass
class ActionResult:
    action: RebalanceAction
    success: bool
    tx_hash: Optional[str] = None
    received: Optional[Decimal] = None
    error: Optional[str] = None

@dataclass
class RebalanceResult:
    success: bool
    results: list[ActionResult]
    reason: Optional[str] = None
    final_state: Optional[dict] = None
    verification: Optional[dict] = None


class RebalanceExecutor:
    """调仓执行器"""

    def __init__(
        self,
        blockchain_service: BlockchainService,
        simulation_service: SimulationService,
        notification_service: NotificationService,
    ):
        self.blockchain_service = blockchain_service
        self.simulation_service = simulation_service
        self.notification_service = notification_service

    async def execute(self, plan: RebalancePlan) -> RebalanceResult:
        results: list[ActionResult] = []

        # 1. 风控检查
        risk_check = await self._perform_risk_checks(plan)
        if not risk_check['passed']:
            return RebalanceResult(
                success=False,
                reason=risk_check['reason'],
                results=[],
            )

        # 2. 模拟所有交易
        for action in plan.actions:
            simulation = await self.simulation_service.simulate(action)
            if not simulation.success:
                await self.notification_service.alert_rebalance_failure(
                    plan=plan,
                    action=action,
                    error=simulation.error,
                    stage='SIMULATION',
                )
                return RebalanceResult(
                    success=False,
                    reason=f"Simulation failed for action: {action.reason}",
                    results=results,
                )

        # 3. 按优先级执行
        sorted_actions = sorted(plan.actions, key=lambda a: a.priority)

        for action in sorted_actions:
            try:
                result = await self._execute_action(action)
                results.append(result)

                if not result.success:
                    # 单笔失败记录但继续执行后续
                    logger.warning(
                        'Action failed, continuing with next',
                        action=action,
                        error=result.error,
                    )
            except Exception as e:
                results.append(ActionResult(
                    action=action,
                    success=False,
                    error=str(e),
                ))

        # 4. 验证最终状态
        final_state = await self.blockchain_service.get_vault_state()
        verification = self._verify_final_state(plan.target_state, final_state)

        # 5. 记录结果
        await self._record_execution(plan, results, final_state)

        return RebalanceResult(
            success=all(r.success for r in results),
            results=results,
            final_state=final_state,
            verification=verification,
        )

    async def _execute_action(self, action: RebalanceAction) -> ActionResult:
        """执行单个调仓动作"""
        if action.type == RebalanceActionType.TRANSFER:
            # 层间转移 (赎回 + 分配)
            if action.from_layer == 'L3':
                result = await self.blockchain_service.call(
                    'assetController',
                    'redeemAsset',
                    [action.asset, int(action.amount)],
                )
                return ActionResult(
                    action=action,
                    success=True,
                    tx_hash=result['hash'],
                    received=Decimal(str(result['value'])),
                )

        elif action.type == RebalanceActionType.PURCHASE:
            result = await self.blockchain_service.call(
                'assetController',
                'purchaseAsset',
                [action.asset, int(action.amount)],
            )
            return ActionResult(
                action=action,
                success=True,
                tx_hash=result['hash'],
                received=Decimal(str(result['value'])),
            )

        elif action.type == RebalanceActionType.REDEEM:
            tier_enum = self._tier_to_enum(action.from_layer)
            result = await self.blockchain_service.call(
                'assetController',
                'executeWaterfallLiquidation',
                [int(action.amount), tier_enum],
            )
            return ActionResult(
                action=action,
                success=True,
                tx_hash=result['hash'],
                received=Decimal(str(result['value'])),
            )

        return ActionResult(action=action, success=False, error='Unknown action type')

    def _tier_to_enum(self, layer: str) -> int:
        return {'L1': 0, 'L2': 1, 'L3': 2}.get(layer, 0)
```

---

## 5. 调仓监控

### 5.1 监控指标

| 指标 | 描述 | 告警阈值 |
|------|------|----------|
| `rebalance_deviation_ratio` | 当前偏离度 | >7% Warning, >10% Critical |
| `rebalance_execution_time` | 执行耗时 | >5min Warning |
| `rebalance_slippage` | 实际滑点 | >2% Warning, >5% Critical |
| `rebalance_gas_cost` | Gas 成本 | >0.5 BNB Warning |
| `rebalance_success_rate` | 成功率 | <90% Warning |
| `rebalance_pending_count` | 待执行计划数 | >5 Warning |

### 5.2 定时任务配置

```python
from celery import Celery
from celery.schedules import crontab

from app.services.rebalance import RebalanceService
from app.services.metrics import MetricsService

celery_app = Celery('paimon')

# 定时任务配置
celery_app.conf.beat_schedule = {
    # 每日 UTC 00:00 检查
    'daily-rebalance-check': {
        'task': 'tasks.daily_check',
        'schedule': crontab(hour=0, minute=0),
    },
    # 每小时检查阈值
    'hourly-threshold-check': {
        'task': 'tasks.hourly_threshold_check',
        'schedule': crontab(minute=0),
    },
    # 每5分钟检查流动性
    'liquidity-check': {
        'task': 'tasks.liquidity_check',
        'schedule': crontab(minute='*/5'),
    },
}


@celery_app.task
async def daily_check():
    """每日调仓检查"""
    rebalance_service = RebalanceService()
    await rebalance_service.check_and_trigger('SCHEDULED')


@celery_app.task
async def hourly_threshold_check():
    """每小时阈值检查"""
    metrics_service = MetricsService()
    rebalance_service = RebalanceService()

    metrics = await metrics_service.get_layer_metrics()
    needs_rebalance = any(m.deviation_abs > 0.05 for m in metrics)

    if needs_rebalance:
        await rebalance_service.check_and_trigger('THRESHOLD')


@celery_app.task
async def liquidity_check():
    """每5分钟流动性检查"""
    metrics_service = MetricsService()
    rebalance_service = RebalanceService()

    l1_ratio = await metrics_service.get_l1_ratio()

    if l1_ratio < 0.08 or l1_ratio > 0.15:
        await rebalance_service.check_and_trigger('LIQUIDITY')
```

---

## 6. 审批集成

### 6.1 审批规则

| 调仓金额 | 审批要求 | SLA |
|----------|----------|-----|
| < 10K | 无需审批 | - |
| 10K - 50K | 自动执行，事后复核 | - |
| 50K - 200K | 单人审批 (ADMIN) | 2小时 |
| > 200K | 多签审批 (2/3 ADMIN) | 4小时 |

### 6.2 审批工单创建

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

@dataclass
class ActionSummary:
    type: str
    amount: Decimal
    reason: str

@dataclass
class RebalanceSummary:
    trigger: str
    total_amount: Decimal
    actions: list[ActionSummary]

@dataclass
class RiskAssessment:
    estimated_slippage: float
    gas_cost: Decimal
    liquidity_impact: str

@dataclass
class RebalanceApprovalTicket:
    type: Literal['REBALANCE'] = 'REBALANCE'
    plan_id: str = ''

    # 调仓摘要
    summary: RebalanceSummary = None

    # 风险评估
    risk_assessment: RiskAssessment = None

    # 审批配置
    required_approvers: int = 1
    sla_deadline: datetime = None
```

---

## 7. 异常处理

### 7.1 失败场景

| 场景 | 处理方式 |
|------|----------|
| 模拟失败 | 中止执行，发送告警 |
| 交易失败 | 记录失败，尝试下一笔 |
| 滑点过大 | 中止当前交易，告警 |
| Gas 不足 | 暂停执行，补充 Gas |
| 网络超时 | 重试3次后告警 |
| 合约暂停 | 中止所有调仓，紧急告警 |

### 7.2 回滚策略

```python
# 调仓不支持自动回滚 (链上交易已确认)
# 但支持"反向调仓"手动修复

def create_rollback_plan(
    failed_plan: RebalancePlan,
    executed_actions: list[ActionResult],
) -> RebalancePlan:
    """创建回滚计划"""
    rollback_actions: list[RebalanceAction] = []

    for result in executed_actions:
        if result.success:
            # 生成反向操作
            action = result.action
            rollback_type = (
                RebalanceActionType.REDEEM
                if action.type == RebalanceActionType.PURCHASE
                else RebalanceActionType.PURCHASE
            )
            rollback_actions.append(RebalanceAction(
                type=rollback_type,
                from_layer=action.to_layer,
                to_layer=action.from_layer,
                amount=action.amount,
                priority=action.priority,
                reason=f"回滚: {action.reason}",
            ))

    return RebalancePlan(
        id=f"rollback-{failed_plan.id}",
        created_at=datetime.utcnow(),
        trigger=RebalanceTrigger.MANUAL,
        pre_state=failed_plan.pre_state,
        target_state=failed_plan.target_state,
        actions=rollback_actions,
        estimated_gas_cost=estimate_gas_cost(rollback_actions),
        estimated_slippage=estimate_slippage(rollback_actions),
        requires_approval=failed_plan.requires_approval,
        approval_threshold=failed_plan.approval_threshold,
    )
```

---

## 8. 配置参考

### 8.1 环境变量

```bash
# 调仓配置
REBALANCE_MIN_AMOUNT=10000          # 最小调仓金额 (USDT)
REBALANCE_APPROVAL_THRESHOLD=50000  # 审批阈值 (USDT)
REBALANCE_MAX_SLIPPAGE=200          # 最大滑点 (bps, 2%)
REBALANCE_GAS_LIMIT=500000          # Gas 限制

# 层级配置
L1_TARGET_RATIO=1000                # 10% (basis points)
L2_TARGET_RATIO=3000                # 30%
L3_TARGET_RATIO=6000                # 60%

# 容忍区间
L1_MIN_RATIO=500                    # 5%
L1_MAX_RATIO=2000                   # 20%
DEVIATION_THRESHOLD=500             # 5% 触发阈值
```

---

*下一节: [03-risk-control.md](./03-risk-control.md) - 风控系统设计*
