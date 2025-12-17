"""Approval workflow service module."""

from app.services.approval.executor import (
    ApprovalExecutionResult,
    ApprovalExecutor,
    ExecutionStatus,
    get_approval_executor,
)
from app.services.approval.schemas import (
    ApprovalAction,
    ApprovalLevel,
    ApprovalResult,
    ApprovalRuleConfig,
    ApprovalTicketCreate,
    ApprovalTicketDetail,
    ApprovalTicketListItem,
    ApprovalTicketListResponse,
    ApprovalTicketStatus,
    ApprovalTicketType,
    EscalationConfig,
    SLAConfig,
)
from app.services.approval.workflow import (
    ApprovalWorkflowEngine,
    get_approval_workflow_engine,
)

__all__ = [
    # Enums
    "ApprovalTicketType",
    "ApprovalTicketStatus",
    "ApprovalResult",
    "ApprovalAction",
    "ApprovalLevel",
    "ExecutionStatus",
    # Config schemas
    "ApprovalRuleConfig",
    "SLAConfig",
    "EscalationConfig",
    # Ticket schemas
    "ApprovalTicketCreate",
    "ApprovalTicketListItem",
    "ApprovalTicketListResponse",
    "ApprovalTicketDetail",
    # Engine
    "ApprovalWorkflowEngine",
    "get_approval_workflow_engine",
    # Executor (v2.0.0 - On-chain execution)
    "ApprovalExecutor",
    "ApprovalExecutionResult",
    "get_approval_executor",
]
