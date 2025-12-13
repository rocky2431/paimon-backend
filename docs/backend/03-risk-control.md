# 风控系统设计

> 模块: Risk Control
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 模块概述

### 1.1 职责

风控系统是基金安全运营的**守护者**，负责：
- 实时监控关键风险指标
- 预测流动性需求和缺口
- 触发预警和响应动作
- 执行紧急预案

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **预防为主** | 提前预警，而非事后补救 |
| **分级响应** | 不同风险等级，不同响应力度 |
| **自动化** | 关键响应自动执行，减少人工延迟 |
| **可追溯** | 所有风险事件完整记录 |

---

## 2. 风险指标体系

### 2.1 指标分类

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Risk Indicator System                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  1. 流动性风险 (Liquidity Risk)                                   │  │
│  │     • L1 占比                                                     │  │
│  │     • L1+L2 占比                                                  │  │
│  │     • 赎回负债覆盖率                                              │  │
│  │     • 流动性缺口预测                                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  2. 价格风险 (Price Risk)                                         │  │
│  │     • NAV 24h 波动                                                │  │
│  │     • 单资产价格偏离                                              │  │
│  │     • 预言机价格有效性                                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  3. 集中度风险 (Concentration Risk)                               │  │
│  │     • 单资产占比                                                  │  │
│  │     • 前3资产占比                                                 │  │
│  │     • 单交易对手占比                                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  4. 赎回压力 (Redemption Pressure)                                │  │
│  │     • 单日赎回/AUM                                                │  │
│  │     • 待审批赎回金额                                              │  │
│  │     • 赎回请求增速                                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  5. 操作风险 (Operational Risk)                                   │  │
│  │     • 交易失败率                                                  │  │
│  │     • 调仓执行延迟                                                │  │
│  │     • 系统健康状态                                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 指标详细定义

#### 流动性风险指标

| 指标 | 计算公式 | 正常 | 警告 | 严重 |
|------|----------|------|------|------|
| `l1_ratio` | L1 / TotalAssets | ≥10% | 8%-10% | <8% |
| `l1_l2_ratio` | (L1+L2) / TotalAssets | ≥40% | 35%-40% | <35% |
| `redemption_coverage` | (L1+L2) / RedemptionLiability | ≥150% | 100%-150% | <100% |
| `liquidity_gap_7d` | PredictedOutflow - AvailableLiquidity | ≤0 | 0-10% AUM | >10% AUM |

#### 价格风险指标

| 指标 | 计算公式 | 正常 | 警告 | 严重 |
|------|----------|------|------|------|
| `nav_volatility_24h` | (NAVmax - NAVmin) / NAVavg | <3% | 3%-5% | >5% |
| `asset_price_deviation` | \|ChainPrice - OraclePrice\| / OraclePrice | <2% | 2%-3% | >3% |
| `oracle_staleness` | Now - OracleLastUpdate | <1h | 1h-4h | >4h |

#### 集中度风险指标

| 指标 | 计算公式 | 正常 | 警告 | 严重 |
|------|----------|------|------|------|
| `single_asset_concentration` | MaxAssetValue / TotalAssets | <20% | 20%-25% | >25% |
| `top3_concentration` | Top3AssetsValue / TotalAssets | <50% | 50%-60% | >60% |
| `counterparty_concentration` | MaxCounterpartyExposure / TotalAssets | <30% | 30%-40% | >40% |

#### 赎回压力指标

| 指标 | 计算公式 | 正常 | 警告 | 严重 |
|------|----------|------|------|------|
| `daily_redemption_rate` | DailyRedemption / AUM | <3% | 3%-5% | >5% |
| `pending_approval_ratio` | PendingApprovalAmount / (L1+L2) | <20% | 20%-30% | >30% |
| `redemption_velocity` | RedemptionCount7d / RedemptionCount7d_prev | <1.5x | 1.5x-2x | >2x |

---

## 3. 风险等级与响应

### 3.1 风险等级定义

```python
from enum import IntEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

class RiskLevel(IntEnum):
    NORMAL = 1     # 正常运营
    ELEVATED = 2   # 关注状态
    HIGH = 3       # 高风险
    CRITICAL = 4   # 紧急状态

@dataclass
class RiskIndicator:
    name: str
    value: float
    threshold: float
    status: Literal['normal', 'warning', 'critical']

@dataclass
class RiskStatus:
    level: RiskLevel
    indicators: list[RiskIndicator]
    overall_score: int  # 0-100, 越高风险越大
    timestamp: datetime
```

### 3.2 响应矩阵

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Response Matrix                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Level 1: NORMAL (正常)                                                   │
│  ───────────────────                                                      │
│  触发条件: 所有指标在正常范围内                                            │
│  响应动作:                                                                │
│    • 常规监控 (5分钟刷新)                                                 │
│    • 生成日报                                                             │
│                                                                           │
│  Level 2: ELEVATED (关注)                                                 │
│  ───────────────────                                                      │
│  触发条件:                                                                │
│    • L1 占比 < 10%                                                        │
│    • 单日赎回 > 3% AUM                                                    │
│    • NAV 24h 波动 > 3%                                                    │
│  响应动作:                                                                │
│    • 加密监控频率 (1分钟刷新)                                             │
│    • 发送 Slack 通知给运营团队                                            │
│    • 自动启动 L2→L1 流动性转移                                            │
│    • 每小时生成流动性报告                                                 │
│                                                                           │
│  Level 3: HIGH (高风险)                                                   │
│  ───────────────────                                                      │
│  触发条件:                                                                │
│    • L1 占比 < 8%                                                         │
│    • 赎回负债覆盖率 < 120%                                                │
│    • 单日赎回 > 5% AUM                                                    │
│  响应动作:                                                                │
│    • 电话通知基金经理                                                     │
│    • 暂停新的标准赎回请求                                                 │
│    • 启动 L3 瀑布清算预备                                                 │
│    • 准备紧急模式启动                                                     │
│    • 每15分钟生成报告                                                     │
│                                                                           │
│  Level 4: CRITICAL (紧急)                                                 │
│  ───────────────────                                                      │
│  触发条件:                                                                │
│    • 赎回负债 > 可用流动性                                                │
│    • L1+L2 占比 < 25%                                                     │
│    • 系统异常 (连续3次交易失败)                                           │
│  响应动作:                                                                │
│    • 启动紧急模式 (emergencyMode = true)                                  │
│    • 暂停所有新申购                                                       │
│    • 执行瀑布清算                                                         │
│    • 通知监管/审计                                                        │
│    • 召开紧急会议                                                         │
│    • 实时报告 (每5分钟)                                                   │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 流动性预测模型

### 4.1 预测模型架构

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

@dataclass
class CurrentLiquidity:
    l1: Decimal
    l2: Decimal
    l3: Decimal

@dataclass
class HistoricalData:
    redemption_rate: float    # 历史赎回率 (年化)
    deposit_rate: float       # 历史申购率 (年化)
    seasonality: list[float]  # 季节性因子

@dataclass
class MarketConditions:
    volatility_index: float   # 市场波动指数
    sentiment_score: float    # 市场情绪分数

@dataclass
class ForecastInputs:
    current_liquidity: CurrentLiquidity
    pending_redemptions: list  # RedemptionRequest list
    historical_data: HistoricalData
    market_conditions: MarketConditions

@dataclass
class ConfidenceInterval:
    lower: Decimal
    upper: Decimal

@dataclass
class ForecastOutputs:
    expected_inflow: Decimal
    expected_outflow: Decimal
    net_flow: Decimal
    liquidity_balance: Decimal
    shortfall_probability: float   # 缺口发生概率
    shortfall_amount: Decimal      # 预期缺口金额
    confidence_interval: ConfidenceInterval

@dataclass
class ForecastRecommendation:
    action: Literal['NONE', 'MONITOR', 'PREPARE_LIQUIDITY', 'EMERGENCY']
    reason: str
    suggested_amount: Optional[Decimal] = None

@dataclass
class LiquidityForecast:
    horizon: Literal['1d', '7d', '30d']
    inputs: ForecastInputs
    outputs: ForecastOutputs
    recommendations: ForecastRecommendation
```

### 4.2 预测算法

```python
import random
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Literal

from app.services.vault import VaultService
from app.services.redemption import RedemptionService

class LiquidityPredictor:
    """流动性预测器"""

    def __init__(self, vault_service: VaultService, redemption_service: RedemptionService):
        self.vault_service = vault_service
        self.redemption_service = redemption_service

    async def forecast(self, horizon: Literal['1d', '7d', '30d']) -> LiquidityForecast:
        days = {'1d': 1, '7d': 7, '30d': 30}[horizon]

        # 1. 获取当前状态
        current_state = await self.vault_service.get_state()
        pending_redemptions = await self.redemption_service.get_pending()

        # 2. 计算确定性流出 (已确认的待结算赎回)
        confirmed_outflow = self._calculate_confirmed_outflow(
            pending_redemptions, days
        )

        # 3. 计算概率性流出 (基于历史数据预测)
        historical_rate = await self._get_historical_redemption_rate()
        probabilistic_outflow = self._calculate_probabilistic_outflow(
            current_state.total_assets, historical_rate, days
        )

        # 4. 计算预期流入 (保守估计)
        historical_deposit_rate = await self._get_historical_deposit_rate()
        expected_inflow = self._calculate_expected_inflow(
            current_state.total_assets, historical_deposit_rate, days
        ) * Decimal('0.5')  # 保守系数 50%

        # 5. 计算可用流动性演变
        available_liquidity = self._project_available_liquidity(current_state, days)

        # 6. 计算缺口概率
        total_outflow = confirmed_outflow + probabilistic_outflow
        net_flow = expected_inflow - total_outflow
        final_balance = available_liquidity + net_flow

        shortfall_probability = self._calculate_shortfall_probability(
            available_liquidity, total_outflow, expected_inflow
        )

        # 7. 生成建议
        recommendations = self._generate_recommendations(
            shortfall_probability, final_balance, current_state.total_assets
        )

        return LiquidityForecast(
            horizon=horizon,
            inputs=ForecastInputs(
                current_liquidity=CurrentLiquidity(
                    l1=current_state.layer1_liquidity,
                    l2=current_state.layer2_liquidity,
                    l3=current_state.layer3_value,
                ),
                pending_redemptions=pending_redemptions,
                historical_data=HistoricalData(
                    redemption_rate=historical_rate,
                    deposit_rate=historical_deposit_rate,
                    seasonality=[],
                ),
                market_conditions=MarketConditions(
                    volatility_index=0.0, sentiment_score=0.0
                ),
            ),
            outputs=ForecastOutputs(
                expected_inflow=expected_inflow,
                expected_outflow=total_outflow,
                net_flow=net_flow,
                liquidity_balance=max(final_balance, Decimal(0)),
                shortfall_probability=shortfall_probability,
                shortfall_amount=abs(final_balance) if final_balance < 0 else Decimal(0),
                confidence_interval=self._calculate_confidence_interval(final_balance),
            ),
            recommendations=recommendations,
        )

    def _calculate_confirmed_outflow(
        self, redemptions: list, days: int
    ) -> Decimal:
        """计算确定性流出"""
        cutoff = datetime.utcnow() + timedelta(days=days)
        return sum(
            r.gross_amount for r in redemptions
            if r.settlement_time <= cutoff
            and r.status not in ('SETTLED', 'CANCELLED')
        )

    def _calculate_shortfall_probability(
        self, available: Decimal, outflow: Decimal, inflow: Decimal
    ) -> float:
        """蒙特卡洛模拟计算缺口概率"""
        simulations = 1000
        shortfall_count = 0

        for _ in range(simulations):
            # 添加随机波动
            actual_outflow = outflow * Decimal(str(0.8 + random.random() * 0.4))
            actual_inflow = inflow * Decimal(str(0.5 + random.random()))

            if available + actual_inflow < actual_outflow:
                shortfall_count += 1

        return shortfall_count / simulations

    def _generate_recommendations(
        self, shortfall_prob: float, balance: Decimal, total_assets: Decimal
    ) -> ForecastRecommendation:
        """生成流动性建议"""
        if shortfall_prob < 0.05:
            return ForecastRecommendation(action='NONE', reason='流动性充足')

        if shortfall_prob < 0.20:
            return ForecastRecommendation(
                action='MONITOR', reason='存在轻微流动性压力，建议密切关注'
            )

        if shortfall_prob < 0.50:
            suggested = abs(balance) if balance < 0 else total_assets / 10
            return ForecastRecommendation(
                action='PREPARE_LIQUIDITY',
                reason='流动性压力较大，建议提前准备',
                suggested_amount=suggested,
            )

        return ForecastRecommendation(
            action='EMERGENCY',
            reason='高概率流动性缺口，建议启动紧急预案',
            suggested_amount=abs(balance) * Decimal('1.2') if balance < 0 else None,
        )
```

---

## 5. 告警系统

### 5.1 告警通道配置

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class SlackChannels:
    normal: str = '#fund-ops'
    warning: str = '#fund-alerts'
    critical: str = '#fund-critical'

@dataclass
class SlackConfig:
    enabled: bool = True
    webhook_url: str = ''
    channels: SlackChannels = None

    def __post_init__(self):
        if self.channels is None:
            self.channels = SlackChannels()

@dataclass
class EmailRecipients:
    normal: list[str] = None
    warning: list[str] = None
    critical: list[str] = None

@dataclass
class EmailConfig:
    enabled: bool = True
    recipients: EmailRecipients = None

@dataclass
class PhoneConfig:
    enabled: bool = False
    provider: Literal['twilio', 'aws-sns'] = 'twilio'
    numbers: list[str] = None  # 基金经理电话

@dataclass
class TelegramChatIds:
    ops: str = ''
    management: str = ''

@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ''
    chat_ids: TelegramChatIds = None

@dataclass
class PagerDutyConfig:
    enabled: bool = False
    service_key: str = ''

@dataclass
class AlertChannelConfig:
    slack: SlackConfig = None
    email: EmailConfig = None
    phone: PhoneConfig = None
    telegram: TelegramConfig = None
    pagerduty: PagerDutyConfig = None

    def __post_init__(self):
        if self.slack is None:
            self.slack = SlackConfig()
        if self.email is None:
            self.email = EmailConfig()
        if self.phone is None:
            self.phone = PhoneConfig()
        if self.telegram is None:
            self.telegram = TelegramConfig()
        if self.pagerduty is None:
            self.pagerduty = PagerDutyConfig()
```

### 5.2 告警模板

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class AlertRiskIndicator:
    name: str
    current_value: str
    threshold: str
    status: str

@dataclass
class AlertLinks:
    dashboard: str
    details: str

@dataclass
class AlertMessage:
    # 基础信息
    severity: Literal['info', 'warning', 'critical']
    title: str
    description: str

    # 风险详情
    risk_indicators: list[AlertRiskIndicator]

    # 建议动作
    suggested_actions: list[str]

    # 链接
    links: AlertLinks

    # 时间
    timestamp: str


# 示例: 低流动性告警
low_liquidity_alert = AlertMessage(
    severity='warning',
    title='⚠️ 流动性预警',
    description='L1 流动性已降至 7.5%，低于安全阈值 8%',
    risk_indicators=[
        AlertRiskIndicator(
            name='L1占比', current_value='7.5%',
            threshold='8%', status='🟡 Warning'
        ),
        AlertRiskIndicator(
            name='L1+L2占比', current_value='37%',
            threshold='35%', status='🟢 Normal'
        ),
        AlertRiskIndicator(
            name='赎回覆盖率', current_value='125%',
            threshold='100%', status='🟢 Normal'
        ),
    ],
    suggested_actions=[
        '检查待结算赎回情况',
        '考虑从 L2 向 L1 转移资金',
        '关注未来 7 天流动性预测',
    ],
    links=AlertLinks(
        dashboard='https://admin.paimon.fund/dashboard',
        details='https://admin.paimon.fund/risk/liquidity',
    ),
    timestamp=datetime.utcnow().isoformat(),
)
```

### 5.3 告警升级机制

```python
from dataclasses import dataclass

@dataclass
class EscalationLevel:
    delay: int              # 延迟毫秒数
    channels: list[str]     # 告警通道列表

@dataclass
class EscalationRules:
    level1: EscalationLevel = None  # 立即发送
    level2: EscalationLevel = None  # 30分钟未处理
    level3: EscalationLevel = None  # 2小时未处理

    def __post_init__(self):
        if self.level1 is None:
            self.level1 = EscalationLevel(
                delay=0, channels=['slack:warning']
            )
        if self.level2 is None:
            self.level2 = EscalationLevel(
                delay=30 * 60 * 1000,
                channels=['slack:warning', 'email:warning']
            )
        if self.level3 is None:
            self.level3 = EscalationLevel(
                delay=2 * 60 * 60 * 1000,
                channels=['slack:critical', 'email:critical', 'phone']
            )

@dataclass
class AcknowledgementConfig:
    required: bool = True
    timeout: int = 30 * 60 * 1000   # 未确认超时时间 (30分钟)
    escalate_on_timeout: bool = True

@dataclass
class AlertEscalation:
    rules: EscalationRules = None
    acknowledgement: AcknowledgementConfig = None

    def __post_init__(self):
        if self.rules is None:
            self.rules = EscalationRules()
        if self.acknowledgement is None:
            self.acknowledgement = AcknowledgementConfig()
```

---

## 6. 紧急预案

### 6.1 预案流程图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Emergency Response Plan                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  触发条件检测                                                              │
│       │                                                                   │
│       ▼                                                                   │
│  ┌─────────────────┐                                                      │
│  │ 风险等级 = CRITICAL │                                                  │
│  └────────┬────────┘                                                      │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                        自动响应 (0-5分钟)                            │ │
│  │  1. 启动紧急模式 (emergencyMode = true)                             │ │
│  │  2. 暂停新申购                                                       │ │
│  │  3. 发送 Critical 告警到所有通道                                     │ │
│  │  4. 记录紧急事件开始时间                                             │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                      流动性救援 (5-30分钟)                           │ │
│  │  1. 评估流动性缺口                                                   │ │
│  │  2. 执行瀑布清算 (L3 → L2 → L1)                                     │ │
│  │  3. 联系 OTC 交易对手                                                │ │
│  │  4. 准备外部流动性注入                                               │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                      人工介入 (30分钟+)                              │ │
│  │  1. 召开紧急会议                                                     │ │
│  │  2. 评估是否需要暂停赎回                                             │ │
│  │  3. 准备对外公告                                                     │ │
│  │  4. 通知监管/审计                                                    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│           │                                                               │
│           ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                        恢复阶段                                      │ │
│  │  1. 确认流动性已恢复到安全水平                                       │ │
│  │  2. 关闭紧急模式                                                     │ │
│  │  3. 恢复正常运营                                                     │ │
│  │  4. 发布事后报告                                                     │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.2 预案执行代码

```python
import asyncio
import structlog
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

from app.services.blockchain import BlockchainService
from app.services.alert import AlertService
from app.services.phone import PhoneService
from app.services.meeting import MeetingService
from app.services.otc import OTCService
from app.services.metrics import MetricsService
from app.services.report import ReportService

logger = structlog.get_logger()


class EmergencyHandler:
    """紧急预案处理器"""

    def __init__(
        self,
        blockchain_service: BlockchainService,
        alert_service: AlertService,
        phone_service: PhoneService,
        meeting_service: MeetingService,
        otc_service: OTCService,
        metrics_service: MetricsService,
        report_service: ReportService,
    ):
        self.blockchain_service = blockchain_service
        self.alert_service = alert_service
        self.phone_service = phone_service
        self.meeting_service = meeting_service
        self.otc_service = otc_service
        self.metrics_service = metrics_service
        self.report_service = report_service

    async def trigger_emergency(self, reason: str, metrics: dict) -> None:
        """触发紧急预案"""
        emergency_id = str(uuid.uuid4())

        # 1. 记录紧急事件开始
        await self._record_emergency_start(emergency_id, reason, metrics)

        # 2. 自动响应 (并行执行)
        await asyncio.gather(
            # 启动紧急模式
            self.blockchain_service.call('vault', 'setEmergencyMode', [True]),
            # 暂停申购
            self.blockchain_service.call('vault', 'pause', []),
            # 发送告警
            self.alert_service.send_critical({
                'title': '🚨 紧急预案已启动',
                'reason': reason,
                'metrics': metrics,
                'emergency_id': emergency_id,
            }),
            # 电话通知
            self.phone_service.call_all('紧急预案已启动，请立即登录系统处理'),
        )

        # 3. 评估并执行流动性救援
        liquidity_gap = await self._assess_liquidity_gap()
        if liquidity_gap > 0:
            await self._execute_liquidity_rescue(liquidity_gap)

        # 4. 创建紧急会议
        emergency_team = await self._get_emergency_team()
        await self.meeting_service.schedule_emergency_meeting(
            title=f'紧急会议: {reason}',
            attendees=emergency_team,
            scheduled_at=datetime.utcnow() + timedelta(minutes=30),
        )

        # 5. 持续监控直到恢复
        asyncio.create_task(self._start_recovery_monitoring(emergency_id))

    async def _execute_liquidity_rescue(self, gap: Decimal) -> None:
        """执行流动性救援"""
        logger.warning('Executing liquidity rescue', gap=str(gap))

        # 瀑布清算
        result = await self.blockchain_service.call(
            'assetController',
            'executeWaterfallLiquidation',
            [int(gap), 2],  # maxTier = L3
        )
        liquidated = Decimal(str(result['value']))

        logger.info(
            'Waterfall liquidation completed',
            requested=str(gap),
            received=str(liquidated),
        )

        # 如果瀑布清算不足，尝试 OTC
        if liquidated < gap:
            remaining = gap - liquidated
            await self.otc_service.request_emergency_liquidity(remaining)

    async def _start_recovery_monitoring(self, emergency_id: str) -> None:
        """开始恢复监控"""
        while True:
            await asyncio.sleep(5 * 60)  # 5分钟检查一次

            metrics = await self.metrics_service.get_current_metrics()
            risk_level = self._calculate_risk_level(metrics)

            if risk_level <= RiskLevel.ELEVATED:
                await self._complete_recovery(emergency_id)
                break

    async def _complete_recovery(self, emergency_id: str) -> None:
        """完成恢复流程"""
        # 1. 关闭紧急模式
        await self.blockchain_service.call('vault', 'setEmergencyMode', [False])

        # 2. 恢复申购
        await self.blockchain_service.call('vault', 'unpause', [])

        # 3. 发送恢复通知
        await self.alert_service.send({
            'severity': 'info',
            'title': '✅ 紧急状态已解除',
            'description': '基金已恢复正常运营',
        })

        # 4. 记录紧急事件结束
        await self._record_emergency_end(emergency_id)

        # 5. 生成事后报告
        await self.report_service.generate_emergency_report(emergency_id)

    def _calculate_risk_level(self, metrics: dict) -> RiskLevel:
        """计算风险等级"""
        # 实现风险等级计算逻辑
        return RiskLevel.NORMAL
```

---

## 7. 监控仪表板

### 7.1 风控仪表板布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Risk Control Dashboard                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  整体风险状态: 🟢 NORMAL                    更新时间: 12:34:56  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │  流动性风险             │  │  流动性趋势 (7天)                   │   │
│  │  ─────────────          │  │  [折线图: L1/L2/L3 占比变化]        │   │
│  │  L1 占比: 10.2% 🟢      │  │                                     │   │
│  │  L1+L2占比: 40.5% 🟢    │  │                                     │   │
│  │  覆盖率: 156% 🟢        │  │                                     │   │
│  │  7日缺口: -$0 🟢        │  │                                     │   │
│  └─────────────────────────┘  └─────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │  价格风险               │  │  集中度风险                         │   │
│  │  ─────────────          │  │  ─────────────                       │   │
│  │  NAV波动: 1.2% 🟢       │  │  最大单资产: 18% 🟢                 │   │
│  │  价格偏离: 0.5% 🟢      │  │  前3资产: 48% 🟢                    │   │
│  │  预言机: 正常 🟢        │  │  交易对手: 25% 🟢                   │   │
│  └─────────────────────────┘  └─────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  最近风险事件                                                    │    │
│  │  ─────────────                                                   │    │
│  │  12:30 [INFO] 定时风控检查完成，无异常                           │    │
│  │  11:45 [WARN] L1占比降至9.8%，已自动补充                         │    │
│  │  10:00 [INFO] 流动性预测报告已生成                               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  流动性预测 (7天)                                                │    │
│  │  ─────────────                                                   │    │
│  │  预期流入: $125,000                                              │    │
│  │  预期流出: $89,000                                               │    │
│  │  净流量:   +$36,000                                              │    │
│  │  缺口概率: 2.3% 🟢                                               │    │
│  │  建议动作: 无需操作                                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 配置参考

### 8.1 环境变量

```bash
# 风控阈值
RISK_L1_MIN_RATIO=500               # 5% (bps)
RISK_L1_LOW_RATIO=800               # 8%
RISK_L1_TARGET_RATIO=1000           # 10%
RISK_L1L2_MIN_RATIO=3500            # 35%
RISK_REDEMPTION_COVERAGE_MIN=10000  # 100%

# 监控配置
RISK_CHECK_INTERVAL=60000           # 1分钟
RISK_FORECAST_INTERVAL=3600000      # 1小时

# 告警配置
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/...
ALERT_EMAIL_FROM=alert@paimon.fund
ALERT_PHONE_NUMBERS=+86138xxxx,+86139xxxx
```

### 8.2 定时任务

```python
from celery import Celery
from celery.schedules import crontab

celery_app = Celery('paimon_risk')

# 风控定时任务配置
celery_app.conf.beat_schedule = {
    # 每分钟检查风控指标
    'check-risk-indicators': {
        'task': 'risk.check_risk_indicators',
        'schedule': crontab(),  # 每分钟
    },
    # 每小时生成流动性预测
    'generate-liquidity-forecast': {
        'task': 'risk.generate_liquidity_forecast',
        'schedule': crontab(minute=0),  # 每小时整点
    },
    # 每日生成风控报告
    'generate-daily-risk-report': {
        'task': 'risk.generate_daily_risk_report',
        'schedule': crontab(hour=0, minute=0),  # 每日 00:00
    },
    # 每周一生成周报
    'generate-weekly-risk-report': {
        'task': 'risk.generate_weekly_risk_report',
        'schedule': crontab(hour=0, minute=0, day_of_week=1),  # 每周一 00:00
    },
}


@celery_app.task
async def check_risk_indicators():
    """每分钟检查风控指标"""
    pass


@celery_app.task
async def generate_liquidity_forecast():
    """每小时生成流动性预测"""
    pass


@celery_app.task
async def generate_daily_risk_report():
    """每日生成风控日报"""
    pass


@celery_app.task
async def generate_weekly_risk_report():
    """每周一生成风控周报"""
    pass
```

---

*下一节: [04-approval-workflow.md](./04-approval-workflow.md) - 审批工作流设计*
