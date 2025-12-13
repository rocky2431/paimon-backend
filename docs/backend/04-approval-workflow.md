# 审批工作流设计

> 模块: Approval Workflow
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 模块概述

### 1.1 职责

审批工作流模块管理所有需要人工确认的操作，包括：
- 大额赎回审批
- 调仓操作审批
- 资产配置变更审批
- 费用提取审批
- 紧急操作审批

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **分级审批** | 不同金额/风险等级，不同审批要求 |
| **SLA 保障** | 每类审批有明确时限，超时自动升级 |
| **审计追踪** | 完整记录审批历史和决策依据 |
| **自动化** | 低风险操作自动审批，减少人工负担 |

---

## 2. 审批类型与规则

### 2.1 审批类型矩阵

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Approval Types Matrix                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  类型              │ 触发条件              │ 审批人         │ SLA        │
│  ─────────────────────────────────────────────────────────────────────   │
│  紧急赎回审批      │ >30K 或 >10% L1       │ VIP_APPROVER   │ 4小时      │
│  标准赎回审批      │ >100K 或 >5% (L1+L2)  │ VIP_APPROVER   │ 24小时     │
│  调仓审批 (小额)   │ 50K - 200K            │ ADMIN (1人)    │ 2小时      │
│  调仓审批 (大额)   │ >200K                 │ ADMIN (2/3)    │ 4小时      │
│  资产添加          │ 任何新资产            │ ADMIN (2/3)    │ 48小时     │
│  资产移除          │ 任何资产移除          │ ADMIN (2/3)    │ 24小时     │
│  费用提取          │ 任何金额              │ ADMIN (2/3)    │ 24小时     │
│  紧急模式开关      │ 启用/关闭             │ ADMIN (2/3)    │ 立即       │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 审批规则详细定义

```python
from dataclasses import dataclass, field
from typing import Literal, Optional, Any
from decimal import Decimal

@dataclass
class ApprovalCondition:
    field: str
    operator: Literal['>', '<', '>=', '<=', '==', '!=']
    value: Any

@dataclass
class ApproverConfig:
    role: str
    min_count: int        # 最少审批人数
    total_required: int   # 需要几人通过 (多签)

@dataclass
class SLAConfig:
    warning_time: int     # 警告时间 (毫秒)
    deadline_time: int    # 截止时间 (毫秒)
    escalation_time: int  # 升级时间 (毫秒)

@dataclass
class AutoApproveConfig:
    enabled: bool
    conditions: list[ApprovalCondition]

@dataclass
class ApprovalRule:
    type: str
    conditions: list[ApprovalCondition]
    approvers: ApproverConfig
    sla: SLAConfig
    auto_reject: bool = False    # 超时是否自动拒绝
    auto_approve: Optional[AutoApproveConfig] = None  # 自动审批条件


# 赎回审批规则
redemption_approval_rules: list[ApprovalRule] = [
    # 紧急赎回审批
    ApprovalRule(
        type='EMERGENCY_REDEMPTION',
        conditions=[
            ApprovalCondition(field='amount', operator='>', value=Decimal('30000e18')),
            ApprovalCondition(field='amount_ratio_l1', operator='>', value=0.10),
        ],
        approvers=ApproverConfig(
            role='VIP_APPROVER',
            min_count=1,
            total_required=1,
        ),
        sla=SLAConfig(
            warning_time=2 * 60 * 60 * 1000,    # 2小时
            deadline_time=4 * 60 * 60 * 1000,   # 4小时
            escalation_time=3 * 60 * 60 * 1000, # 3小时升级
        ),
        auto_reject=False,
    ),

    # 标准赎回审批
    ApprovalRule(
        type='STANDARD_REDEMPTION',
        conditions=[
            ApprovalCondition(field='amount', operator='>', value=Decimal('100000e18')),
            ApprovalCondition(field='amount_ratio_l1_l2', operator='>', value=0.05),
        ],
        approvers=ApproverConfig(
            role='VIP_APPROVER',
            min_count=1,
            total_required=1,
        ),
        sla=SLAConfig(
            warning_time=12 * 60 * 60 * 1000,   # 12小时
            deadline_time=24 * 60 * 60 * 1000,  # 24小时
            escalation_time=18 * 60 * 60 * 1000, # 18小时升级
        ),
        auto_reject=False,
    ),
]

# 调仓审批规则
rebalance_approval_rules: list[ApprovalRule] = [
    # 小额调仓
    ApprovalRule(
        type='REBALANCE_SMALL',
        conditions=[
            ApprovalCondition(field='amount', operator='>=', value=Decimal('50000e18')),
            ApprovalCondition(field='amount', operator='<', value=Decimal('200000e18')),
        ],
        approvers=ApproverConfig(
            role='ADMIN',
            min_count=1,
            total_required=1,
        ),
        sla=SLAConfig(
            warning_time=1 * 60 * 60 * 1000,
            deadline_time=2 * 60 * 60 * 1000,
            escalation_time=int(1.5 * 60 * 60 * 1000),
        ),
        auto_reject=False,
        auto_approve=AutoApproveConfig(
            enabled=True,
            conditions=[
                ApprovalCondition(field='trigger', operator='==', value='THRESHOLD'),
                ApprovalCondition(field='risk_level', operator='<=', value='ELEVATED'),
            ],
        ),
    ),

    # 大额调仓
    ApprovalRule(
        type='REBALANCE_LARGE',
        conditions=[
            ApprovalCondition(field='amount', operator='>=', value=Decimal('200000e18')),
        ],
        approvers=ApproverConfig(
            role='ADMIN',
            min_count=3,
            total_required=2,  # 2/3 多签
        ),
        sla=SLAConfig(
            warning_time=2 * 60 * 60 * 1000,
            deadline_time=4 * 60 * 60 * 1000,
            escalation_time=3 * 60 * 60 * 1000,
        ),
        auto_reject=False,
    ),
]
```

---

## 3. 工单数据模型

### 3.1 工单结构

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Any
from decimal import Decimal


class ApprovalStatus(str, Enum):
    PENDING = 'PENDING'                        # 待审批
    PARTIALLY_APPROVED = 'PARTIALLY_APPROVED'  # 部分审批 (多签)
    APPROVED = 'APPROVED'                      # 已通过
    REJECTED = 'REJECTED'                      # 已拒绝
    EXPIRED = 'EXPIRED'                        # 已过期
    CANCELLED = 'CANCELLED'                    # 已取消


class ApprovalType(str, Enum):
    EMERGENCY_REDEMPTION = 'EMERGENCY_REDEMPTION'
    STANDARD_REDEMPTION = 'STANDARD_REDEMPTION'
    REBALANCE_SMALL = 'REBALANCE_SMALL'
    REBALANCE_LARGE = 'REBALANCE_LARGE'
    ASSET_ADD = 'ASSET_ADD'
    ASSET_REMOVE = 'ASSET_REMOVE'
    FEE_WITHDRAW = 'FEE_WITHDRAW'
    EMERGENCY_MODE = 'EMERGENCY_MODE'


@dataclass
class RiskAssessment:
    level: str
    score: int
    factors: list[str]


@dataclass
class RequestData:
    amount: Decimal
    description: str
    risk_assessment: Optional[RiskAssessment] = None
    additional_info: Optional[dict[str, Any]] = None


@dataclass
class ApprovalRecord:
    id: str
    ticket_id: str
    approver: str                # 审批人地址
    action: Literal['APPROVE', 'REJECT']
    timestamp: datetime
    reason: Optional[str] = None
    signature: Optional[str] = None  # 链上签名 (可选)


@dataclass
class ApprovalTicket:
    # 基础信息
    id: str                              # 工单ID
    type: ApprovalType                   # 审批类型
    status: ApprovalStatus               # 工单状态
    created_at: datetime
    updated_at: datetime

    # 关联信息
    reference_type: Literal['REDEMPTION', 'REBALANCE', 'ASSET_CONFIG', 'FEE_WITHDRAW']
    reference_id: str                    # 关联的业务ID

    # 请求详情
    requester: str                       # 请求发起人地址
    request_data: RequestData

    # 审批配置
    rule: ApprovalRule
    required_approvals: int              # 需要的审批数
    current_approvals: int = 0           # 当前审批数
    current_rejections: int = 0          # 当前拒绝数

    # 审批记录
    approval_records: list[ApprovalRecord] = field(default_factory=list)

    # SLA
    sla_deadline: datetime = None
    sla_warning: datetime = None
    escalated_at: Optional[datetime] = None
    escalated_to: Optional[list[str]] = None

    # 结果
    result: Optional[Literal['APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED']] = None
    result_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
```

### 3.2 状态流转

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Approval Status Flow                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│                          ┌─────────────┐                                  │
│                          │   PENDING   │                                  │
│                          │   (待审批)   │                                  │
│                          └──────┬──────┘                                  │
│                                 │                                         │
│            ┌────────────────────┼────────────────────┐                   │
│            │                    │                    │                   │
│            ▼                    ▼                    ▼                   │
│   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐          │
│   │  PARTIALLY_    │   │   APPROVED     │   │   REJECTED     │          │
│   │  APPROVED      │   │   (已通过)     │   │   (已拒绝)     │          │
│   │  (部分审批)    │   └────────────────┘   └────────────────┘          │
│   └───────┬────────┘            ▲                    ▲                   │
│           │                     │                    │                   │
│           └─────────────────────┴────────────────────┘                   │
│                                                                           │
│            ┌────────────────────┴────────────────────┐                   │
│            │                                         │                   │
│            ▼                                         ▼                   │
│   ┌────────────────┐                        ┌────────────────┐          │
│   │    EXPIRED     │                        │   CANCELLED    │          │
│   │   (已过期)     │                        │   (已取消)     │          │
│   └────────────────┘                        └────────────────┘          │
│                                                                           │
│  状态转换条件:                                                            │
│  ────────────                                                            │
│  PENDING → PARTIALLY_APPROVED: 收到部分审批 (多签场景)                    │
│  PENDING → APPROVED: 收到足够审批                                         │
│  PENDING → REJECTED: 收到拒绝                                             │
│  PARTIALLY_APPROVED → APPROVED: 收到足够审批                              │
│  PARTIALLY_APPROVED → REJECTED: 收到拒绝                                  │
│  PENDING → EXPIRED: 超过SLA截止时间                                       │
│  PENDING → CANCELLED: 请求人取消                                          │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 工作流引擎

### 4.1 工作流架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Approval Workflow Engine                           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Ticket Creator                                │   │
│  │  • 接收创建请求                                                    │   │
│  │  • 匹配审批规则                                                    │   │
│  │  • 生成工单                                                        │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                    │                                      │
│                                    ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Auto Approval Check                           │   │
│  │  • 检查是否满足自动审批条件                                        │   │
│  │  • 满足则直接通过                                                  │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                    │                                      │
│                     ┌──────────────┴──────────────┐                      │
│                     │                             │                      │
│                     ▼                             ▼                      │
│  ┌──────────────────────────┐    ┌──────────────────────────────────┐   │
│  │     Manual Approval      │    │        Auto Approved             │   │
│  │     (需要人工审批)        │    │        (自动通过)                 │   │
│  └────────────┬─────────────┘    └──────────────────────────────────┘   │
│               │                                                          │
│               ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Notification Service                          │   │
│  │  • 通知审批人                                                      │   │
│  │  • 设置SLA定时器                                                   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│               │                                                          │
│               ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Approval Handler                              │   │
│  │  • 处理审批动作                                                    │   │
│  │  • 更新工单状态                                                    │   │
│  │  • 检查是否达到审批阈值                                            │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│               │                                                          │
│               ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Result Processor                              │   │
│  │  • 执行审批后动作                                                  │   │
│  │  • 触发下游流程                                                    │   │
│  │  • 发送结果通知                                                    │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 核心服务实现

```python
import uuid
import structlog
from datetime import datetime, timedelta
from typing import Literal, Optional

from app.repositories.approval_ticket import ApprovalTicketRepository
from app.services.approval_rule_engine import ApprovalRuleEngine
from app.services.notification import NotificationService
from app.services.scheduler import SchedulerService
from app.services.blockchain import BlockchainService
from app.exceptions import NotFoundException, BadRequestException, ForbiddenException

logger = structlog.get_logger()


def generate_ticket_id() -> str:
    return f"TKT-{uuid.uuid4().hex[:12].upper()}"


def generate_record_id() -> str:
    return f"REC-{uuid.uuid4().hex[:12].upper()}"


class ApprovalWorkflowService:
    """审批工作流服务"""

    def __init__(
        self,
        ticket_repo: ApprovalTicketRepository,
        rule_engine: ApprovalRuleEngine,
        notification_service: NotificationService,
        scheduler_service: SchedulerService,
        blockchain_service: BlockchainService,
    ):
        self.ticket_repo = ticket_repo
        self.rule_engine = rule_engine
        self.notification_service = notification_service
        self.scheduler_service = scheduler_service
        self.blockchain_service = blockchain_service

    async def create_ticket(self, request: 'CreateTicketRequest') -> ApprovalTicket:
        """创建审批工单"""
        # 1. 匹配审批规则
        rule = self.rule_engine.match_rule(request.type, request.data)
        if not rule:
            raise ValueError(f"No approval rule matched for type: {request.type}")

        # 2. 检查是否满足自动审批条件
        if rule.auto_approve and rule.auto_approve.enabled:
            auto_approve_match = self.rule_engine.check_conditions(
                rule.auto_approve.conditions,
                request.data,
            )
            if auto_approve_match:
                return await self._create_auto_approved_ticket(request, rule)

        # 3. 创建工单
        now = datetime.utcnow()
        ticket = ApprovalTicket(
            id=generate_ticket_id(),
            type=request.type,
            status=ApprovalStatus.PENDING,
            created_at=now,
            updated_at=now,
            reference_type=request.reference_type,
            reference_id=request.reference_id,
            requester=request.requester,
            request_data=request.data,
            rule=rule,
            required_approvals=rule.approvers.total_required,
            current_approvals=0,
            current_rejections=0,
            approval_records=[],
            sla_deadline=now + timedelta(milliseconds=rule.sla.deadline_time),
            sla_warning=now + timedelta(milliseconds=rule.sla.warning_time),
        )

        await self.ticket_repo.save(ticket)

        # 4. 通知审批人
        await self._notify_approvers(ticket)

        # 5. 设置SLA定时器
        self._schedule_sla_checks(ticket)

        return ticket

    async def process_approval(
        self,
        ticket_id: str,
        approver: str,
        action: Literal['APPROVE', 'REJECT'],
        reason: Optional[str] = None,
    ) -> ApprovalTicket:
        """处理审批动作"""
        ticket = await self.ticket_repo.find_by_id(ticket_id)
        if not ticket:
            raise NotFoundException(f"Ticket not found: {ticket_id}")

        # 1. 验证状态
        if ticket.status not in (ApprovalStatus.PENDING, ApprovalStatus.PARTIALLY_APPROVED):
            raise BadRequestException(f"Ticket is not in approvable state: {ticket.status}")

        # 2. 验证审批人权限
        has_permission = await self._verify_approver_permission(approver, ticket.rule)
        if not has_permission:
            raise ForbiddenException("Approver does not have permission")

        # 3. 检查是否已审批
        already_approved = any(r.approver == approver for r in ticket.approval_records)
        if already_approved:
            raise BadRequestException("Approver has already acted on this ticket")

        # 4. 记录审批动作
        record = ApprovalRecord(
            id=generate_record_id(),
            ticket_id=ticket_id,
            approver=approver,
            action=action,
            reason=reason,
            timestamp=datetime.utcnow(),
        )
        ticket.approval_records.append(record)

        # 5. 更新计数
        if action == 'APPROVE':
            ticket.current_approvals += 1
        else:
            ticket.current_rejections += 1

        # 6. 判断工单状态
        if action == 'REJECT':
            # 任何拒绝都导致工单被拒绝
            ticket.status = ApprovalStatus.REJECTED
            ticket.result = 'REJECTED'
            ticket.result_reason = reason
            ticket.resolved_at = datetime.utcnow()
            ticket.resolved_by = approver
        elif ticket.current_approvals >= ticket.required_approvals:
            # 达到审批阈值
            ticket.status = ApprovalStatus.APPROVED
            ticket.result = 'APPROVED'
            ticket.resolved_at = datetime.utcnow()
            ticket.resolved_by = approver
        else:
            # 部分审批
            ticket.status = ApprovalStatus.PARTIALLY_APPROVED

        ticket.updated_at = datetime.utcnow()
        await self.ticket_repo.save(ticket)

        # 7. 处理结果
        if ticket.result:
            await self._process_result(ticket)

        return ticket

    async def _process_result(self, ticket: ApprovalTicket) -> None:
        """处理审批结果"""
        # 取消SLA定时器
        self._cancel_sla_checks(ticket.id)

        # 根据审批类型执行不同动作
        handlers = {
            'REDEMPTION': self._process_redemption_approval,
            'REBALANCE': self._process_rebalance_approval,
            'ASSET_CONFIG': self._process_asset_config_approval,
            'FEE_WITHDRAW': self._process_fee_withdraw_approval,
        }

        handler = handlers.get(ticket.reference_type)
        if handler:
            await handler(ticket)

        # 发送结果通知
        await self.notification_service.notify_approval_result(ticket)

    async def _process_redemption_approval(self, ticket: ApprovalTicket) -> None:
        """处理赎回审批结果"""
        if ticket.result == 'APPROVED':
            # 调用合约审批赎回
            await self.blockchain_service.call(
                'redemptionManager',
                'approveRedemption',
                [int(ticket.reference_id)],
            )
        elif ticket.result == 'REJECTED':
            # 调用合约拒绝赎回
            await self.blockchain_service.call(
                'redemptionManager',
                'rejectRedemption',
                [int(ticket.reference_id), ticket.result_reason or 'Rejected by approver'],
            )

    async def _process_rebalance_approval(self, ticket: ApprovalTicket) -> None:
        """处理调仓审批结果"""
        pass

    async def _process_asset_config_approval(self, ticket: ApprovalTicket) -> None:
        """处理资产配置审批结果"""
        pass

    async def _process_fee_withdraw_approval(self, ticket: ApprovalTicket) -> None:
        """处理费用提取审批结果"""
        pass

    async def _notify_approvers(self, ticket: ApprovalTicket) -> None:
        """通知审批人"""
        pass

    def _schedule_sla_checks(self, ticket: ApprovalTicket) -> None:
        """设置SLA检查定时器"""
        pass

    def _cancel_sla_checks(self, ticket_id: str) -> None:
        """取消SLA检查定时器"""
        pass

    async def _verify_approver_permission(
        self, approver: str, rule: ApprovalRule
    ) -> bool:
        """验证审批人权限"""
        return True

    async def _create_auto_approved_ticket(
        self, request: 'CreateTicketRequest', rule: ApprovalRule
    ) -> ApprovalTicket:
        """创建自动审批的工单"""
        now = datetime.utcnow()
        return ApprovalTicket(
            id=generate_ticket_id(),
            type=request.type,
            status=ApprovalStatus.APPROVED,
            created_at=now,
            updated_at=now,
            reference_type=request.reference_type,
            reference_id=request.reference_id,
            requester=request.requester,
            request_data=request.data,
            rule=rule,
            required_approvals=0,
            result='APPROVED',
            result_reason='Auto-approved',
            resolved_at=now,
        )
```

---

## 5. SLA 管理

### 5.1 SLA 定时任务

```python
import structlog
from datetime import datetime, timedelta
from typing import Optional

from app.repositories.approval_ticket import ApprovalTicketRepository
from app.services.notification import NotificationService
from app.services.scheduler import SchedulerService

logger = structlog.get_logger()


def format_duration(milliseconds: int) -> str:
    """格式化时间间隔"""
    seconds = milliseconds // 1000
    if seconds < 60:
        return f"{seconds}秒"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if remaining_minutes > 0:
        return f"{hours}小时{remaining_minutes}分钟"
    return f"{hours}小时"


class SLAManager:
    """SLA管理器"""

    def __init__(
        self,
        ticket_repo: ApprovalTicketRepository,
        notification_service: NotificationService,
        scheduler_service: SchedulerService,
    ):
        self.ticket_repo = ticket_repo
        self.notification_service = notification_service
        self.scheduler_service = scheduler_service

    def schedule_sla_checks(self, ticket: ApprovalTicket) -> None:
        """设置SLA检查定时器"""
        # 警告定时器
        self.scheduler_service.schedule(
            id=f"sla-warning-{ticket.id}",
            execute_at=ticket.sla_warning,
            handler=lambda: self.handle_sla_warning(ticket.id),
        )

        # 升级定时器
        escalation_time = ticket.created_at + timedelta(
            milliseconds=ticket.rule.sla.escalation_time
        )
        self.scheduler_service.schedule(
            id=f"sla-escalation-{ticket.id}",
            execute_at=escalation_time,
            handler=lambda: self.handle_sla_escalation(ticket.id),
        )

        # 截止定时器
        self.scheduler_service.schedule(
            id=f"sla-deadline-{ticket.id}",
            execute_at=ticket.sla_deadline,
            handler=lambda: self.handle_sla_deadline(ticket.id),
        )

    async def handle_sla_warning(self, ticket_id: str) -> None:
        """处理SLA警告"""
        ticket = await self.ticket_repo.find_by_id(ticket_id)
        if not ticket or ticket.result:
            return  # 已处理

        time_remaining = int(
            (ticket.sla_deadline - datetime.utcnow()).total_seconds() * 1000
        )

        await self.notification_service.send({
            'type': 'SLA_WARNING',
            'severity': 'warning',
            'title': '⏰ 审批工单即将超时',
            'description': f'工单 {ticket_id} 将在 {format_duration(time_remaining)} 后超时',
            'ticket': ticket,
        })

    async def handle_sla_escalation(self, ticket_id: str) -> None:
        """处理SLA升级"""
        ticket = await self.ticket_repo.find_by_id(ticket_id)
        if not ticket or ticket.result:
            return

        # 升级到上级审批人
        escalation_approvers = await self._get_escalation_approvers(ticket.rule)

        ticket.escalated_at = datetime.utcnow()
        ticket.escalated_to = escalation_approvers
        await self.ticket_repo.save(ticket)

        # 通知升级审批人
        await self.notification_service.send({
            'type': 'SLA_ESCALATION',
            'severity': 'warning',
            'title': '🔺 审批工单已升级',
            'description': f'工单 {ticket_id} 因超时已升级处理',
            'recipients': escalation_approvers,
            'ticket': ticket,
        })

    async def handle_sla_deadline(self, ticket_id: str) -> None:
        """处理SLA截止"""
        ticket = await self.ticket_repo.find_by_id(ticket_id)
        if not ticket or ticket.result:
            return

        if ticket.rule.auto_reject:
            # 自动拒绝
            ticket.status = ApprovalStatus.EXPIRED
            ticket.result = 'EXPIRED'
            ticket.result_reason = 'SLA deadline exceeded'
            ticket.resolved_at = datetime.utcnow()
            await self.ticket_repo.save(ticket)

            await self._process_result(ticket)
        else:
            # 仅通知，不自动拒绝
            await self.notification_service.send({
                'type': 'SLA_EXCEEDED',
                'severity': 'critical',
                'title': '🚨 审批工单已超时',
                'description': f'工单 {ticket_id} 已超过SLA截止时间，请立即处理',
                'ticket': ticket,
            })

    async def _get_escalation_approvers(self, rule: ApprovalRule) -> list[str]:
        """获取升级审批人列表"""
        # 实现获取升级审批人的逻辑
        return []

    async def _process_result(self, ticket: ApprovalTicket) -> None:
        """处理审批结果"""
        pass
```

### 5.2 SLA 报表

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReportPeriod:
    start: datetime
    end: datetime


@dataclass
class TypeStatistics:
    type: ApprovalType
    total: int
    sla_met_rate: float
    average_time: int  # 毫秒


@dataclass
class ApproverStatistics:
    approver: str               # 审批人地址
    total_approvals: int
    average_response_time: int  # 毫秒


@dataclass
class ExceededTicket:
    id: str
    type: ApprovalType
    exceeded_by: int  # 超时时长 (毫秒)


@dataclass
class SLAReport:
    period: ReportPeriod

    # 整体统计
    total_tickets: int
    resolved_tickets: int
    pending_tickets: int

    # SLA达成率
    sla_met_rate: float           # 在SLA内完成的比例
    average_resolution_time: int  # 平均处理时间 (毫秒)

    # 按类型统计
    by_type: list[TypeStatistics]

    # 按审批人统计
    by_approver: list[ApproverStatistics]

    # 超时工单
    exceeded_tickets: list[ExceededTicket]
```

---

## 6. 通知系统集成

### 6.1 通知模板

```python
from dataclasses import dataclass
from typing import Any
from decimal import Decimal


def format_amount(amount: Decimal) -> str:
    """格式化金额"""
    return f"${amount:,.2f}"


def shorten_address(address: str) -> str:
    """缩短地址显示"""
    return f"{address[:6]}...{address[-4:]}"


def format_date(dt: datetime) -> str:
    """格式化日期时间"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_new_ticket_slack_message(ticket: ApprovalTicket, dashboard_url: str) -> dict:
    """构建新工单 Slack 消息"""
    return {
        'blocks': [
            {
                'type': 'header',
                'text': {'type': 'plain_text', 'text': '📋 新审批工单'},
            },
            {
                'type': 'section',
                'fields': [
                    {'type': 'mrkdwn', 'text': f'*类型:* {ticket.type.value}'},
                    {'type': 'mrkdwn', 'text': f'*金额:* {format_amount(ticket.request_data.amount)}'},
                    {'type': 'mrkdwn', 'text': f'*请求人:* {shorten_address(ticket.requester)}'},
                    {'type': 'mrkdwn', 'text': f'*截止时间:* {format_date(ticket.sla_deadline)}'},
                ],
            },
            {
                'type': 'actions',
                'elements': [
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': '✅ 批准'},
                        'style': 'primary',
                        'action_id': f'approve-{ticket.id}',
                    },
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': '❌ 拒绝'},
                        'style': 'danger',
                        'action_id': f'reject-{ticket.id}',
                    },
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': '📄 详情'},
                        'url': f'{dashboard_url}/approvals/{ticket.id}',
                    },
                ],
            },
        ],
    }


# 审批结果通知模板
@dataclass
class ResultTemplate:
    emoji: str
    title: str
    color: str


RESULT_TEMPLATES: dict[str, ResultTemplate] = {
    'approved': ResultTemplate(emoji='✅', title='审批已通过', color='#36a64f'),
    'rejected': ResultTemplate(emoji='❌', title='审批已拒绝', color='#dc3545'),
    'expired': ResultTemplate(emoji='⏰', title='审批已超时', color='#ffc107'),
}
```

### 6.2 通知渠道配置

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class EventNotificationConfig:
    channels: list[Literal['slack', 'email', 'phone']]
    recipients: list[str]  # 'approvers', 'requester', 'escalation_approvers'


@dataclass
class NotificationConfig:
    # 工单创建时通知
    on_create: EventNotificationConfig = None

    # SLA警告时通知
    on_sla_warning: EventNotificationConfig = None

    # SLA升级时通知
    on_sla_escalation: EventNotificationConfig = None

    # 审批完成时通知
    on_result: EventNotificationConfig = None

    def __post_init__(self):
        if self.on_create is None:
            self.on_create = EventNotificationConfig(
                channels=['slack', 'email'],
                recipients=['approvers'],
            )
        if self.on_sla_warning is None:
            self.on_sla_warning = EventNotificationConfig(
                channels=['slack'],
                recipients=['approvers'],
            )
        if self.on_sla_escalation is None:
            self.on_sla_escalation = EventNotificationConfig(
                channels=['slack', 'email', 'phone'],
                recipients=['escalation_approvers', 'requester'],
            )
        if self.on_result is None:
            self.on_result = EventNotificationConfig(
                channels=['slack', 'email'],
                recipients=['requester', 'approvers'],
            )
```

---

## 7. 审计日志

### 7.1 日志结构

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Any


@dataclass
class ApprovalAuditLog:
    id: str
    timestamp: datetime
    ticket_id: str

    # 操作信息
    action: Literal['CREATE', 'APPROVE', 'REJECT', 'CANCEL', 'EXPIRE', 'ESCALATE']
    actor: str              # 操作人地址
    actor_role: str

    # 变更详情
    new_status: ApprovalStatus
    previous_status: Optional[ApprovalStatus] = None

    # 元数据
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    reason: Optional[str] = None

    # 完整快照
    ticket_snapshot: Optional[dict[str, Any]] = None
```

### 7.2 日志查询接口

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass
class AuditLogQuery:
    # 时间范围
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # 过滤条件
    ticket_id: Optional[str] = None
    actor: Optional[str] = None
    action: Optional[str] = None
    ticket_type: Optional[ApprovalType] = None

    # 分页
    page: int = 1
    page_size: int = 20

    # 排序
    sort_by: Literal['timestamp', 'actor', 'action'] = 'timestamp'
    sort_order: Literal['asc', 'desc'] = 'desc'
```

---

## 8. API 接口

### 8.1 审批相关 API

```yaml
# 获取待审批列表
GET /api/v1/approvals
  Query:
    - status: string (PENDING, PARTIALLY_APPROVED)
    - type: string
    - page: number
    - pageSize: number
  Response:
    - items: ApprovalTicket[]
    - total: number
    - page: number

# 获取工单详情
GET /api/v1/approvals/:id
  Response: ApprovalTicket

# 审批通过
POST /api/v1/approvals/:id/approve
  Body:
    - reason?: string
  Response: ApprovalTicket

# 审批拒绝
POST /api/v1/approvals/:id/reject
  Body:
    - reason: string (required)
  Response: ApprovalTicket

# 取消工单 (仅请求人)
POST /api/v1/approvals/:id/cancel
  Response: ApprovalTicket

# 获取审计日志
GET /api/v1/approvals/:id/audit-logs
  Response: ApprovalAuditLog[]

# 获取SLA报表
GET /api/v1/approvals/sla-report
  Query:
    - startDate: string
    - endDate: string
  Response: SLAReport
```

---

## 9. 配置参考

### 9.1 环境变量

```bash
# SLA配置
APPROVAL_SLA_EMERGENCY_HOURS=4
APPROVAL_SLA_STANDARD_HOURS=24
APPROVAL_SLA_REBALANCE_SMALL_HOURS=2
APPROVAL_SLA_REBALANCE_LARGE_HOURS=4

# 阈值配置
APPROVAL_EMERGENCY_AMOUNT=30000      # 30K USDT
APPROVAL_STANDARD_AMOUNT=100000      # 100K USDT
APPROVAL_REBALANCE_SMALL=50000       # 50K USDT
APPROVAL_REBALANCE_LARGE=200000      # 200K USDT

# 通知配置
APPROVAL_SLACK_CHANNEL=#fund-approvals
APPROVAL_EMAIL_RECIPIENTS=ops@paimon.fund
```

---

*下一节: [05-api-specification.md](./05-api-specification.md) - API 规范*
