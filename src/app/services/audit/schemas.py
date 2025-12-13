"""Schemas for audit logging service."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditCategory(str, Enum):
    """Categories of audit events."""

    AUTHENTICATION = "AUTHENTICATION"  # Login, logout, token refresh
    AUTHORIZATION = "AUTHORIZATION"  # Permission checks, access denied
    USER_ACTION = "USER_ACTION"  # User-initiated actions
    SYSTEM_ACTION = "SYSTEM_ACTION"  # Automated system actions
    DATA_ACCESS = "DATA_ACCESS"  # Data read operations
    DATA_MODIFICATION = "DATA_MODIFICATION"  # Data write operations
    FINANCIAL = "FINANCIAL"  # Financial transactions
    SECURITY = "SECURITY"  # Security-related events
    CONFIGURATION = "CONFIGURATION"  # Config changes
    EMERGENCY = "EMERGENCY"  # Emergency protocol events


class AuditAction(str, Enum):
    """Specific audit actions."""

    # Authentication
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    TOKEN_REVOKED = "TOKEN_REVOKED"

    # Redemptions
    REDEMPTION_CREATED = "REDEMPTION_CREATED"
    REDEMPTION_APPROVED = "REDEMPTION_APPROVED"
    REDEMPTION_REJECTED = "REDEMPTION_REJECTED"
    REDEMPTION_SETTLED = "REDEMPTION_SETTLED"
    REDEMPTION_CANCELLED = "REDEMPTION_CANCELLED"

    # Rebalancing
    REBALANCE_TRIGGERED = "REBALANCE_TRIGGERED"
    REBALANCE_APPROVED = "REBALANCE_APPROVED"
    REBALANCE_EXECUTED = "REBALANCE_EXECUTED"
    REBALANCE_CANCELLED = "REBALANCE_CANCELLED"

    # Risk
    RISK_ALERT_GENERATED = "RISK_ALERT_GENERATED"
    RISK_ALERT_ACKNOWLEDGED = "RISK_ALERT_ACKNOWLEDGED"
    RISK_ALERT_RESOLVED = "RISK_ALERT_RESOLVED"
    EMERGENCY_TRIGGERED = "EMERGENCY_TRIGGERED"
    EMERGENCY_RESOLVED = "EMERGENCY_RESOLVED"

    # Approvals
    APPROVAL_SUBMITTED = "APPROVAL_SUBMITTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_ESCALATED = "APPROVAL_ESCALATED"

    # Configuration
    CONFIG_UPDATED = "CONFIG_UPDATED"
    THRESHOLD_CHANGED = "THRESHOLD_CHANGED"
    WALLET_ADDED = "WALLET_ADDED"
    WALLET_REMOVED = "WALLET_REMOVED"

    # Data
    REPORT_GENERATED = "REPORT_GENERATED"
    REPORT_DOWNLOADED = "REPORT_DOWNLOADED"
    DATA_EXPORTED = "DATA_EXPORTED"

    # System
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    SCHEDULED_JOB_RUN = "SCHEDULED_JOB_RUN"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditEntry(BaseModel):
    """Audit log entry."""

    entry_id: str = Field(..., description="Unique entry ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    category: AuditCategory = Field(..., description="Event category")
    action: AuditAction = Field(..., description="Specific action")
    severity: AuditSeverity = Field(
        default=AuditSeverity.INFO, description="Event severity"
    )

    # Actor information
    actor_id: str | None = Field(None, description="User/system ID that triggered")
    actor_type: str = Field(default="user", description="Type: user, system, api")
    actor_ip: str | None = Field(None, description="IP address if applicable")
    actor_user_agent: str | None = Field(None, description="User agent if applicable")

    # Resource information
    resource_type: str | None = Field(None, description="Type of resource affected")
    resource_id: str | None = Field(None, description="ID of resource affected")

    # Event details
    description: str = Field(..., description="Human-readable description")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="System metadata")

    # Outcome
    success: bool = Field(default=True, description="Whether action succeeded")
    error_message: str | None = Field(None, description="Error if failed")

    # Correlation
    correlation_id: str | None = Field(None, description="Request correlation ID")
    parent_entry_id: str | None = Field(None, description="Parent entry for chaining")


class AuditQuery(BaseModel):
    """Query parameters for audit log search."""

    start_time: datetime | None = Field(None, description="Start of time range")
    end_time: datetime | None = Field(None, description="End of time range")
    categories: list[AuditCategory] | None = Field(None, description="Filter categories")
    actions: list[AuditAction] | None = Field(None, description="Filter actions")
    severities: list[AuditSeverity] | None = Field(None, description="Filter severities")
    actor_id: str | None = Field(None, description="Filter by actor")
    resource_type: str | None = Field(None, description="Filter by resource type")
    resource_id: str | None = Field(None, description="Filter by resource ID")
    success: bool | None = Field(None, description="Filter by success/failure")
    correlation_id: str | None = Field(None, description="Filter by correlation ID")
    limit: int = Field(default=100, le=1000, description="Max results")
    offset: int = Field(default=0, description="Pagination offset")


class AuditStats(BaseModel):
    """Audit statistics."""

    total_entries: int = Field(..., description="Total entries")
    entries_by_category: dict[str, int] = Field(..., description="Count by category")
    entries_by_severity: dict[str, int] = Field(..., description="Count by severity")
    entries_by_action: dict[str, int] = Field(..., description="Count by action")
    success_rate: float = Field(..., description="Success rate percentage")
    unique_actors: int = Field(..., description="Unique actor count")
    time_range_start: datetime | None = Field(None, description="Earliest entry")
    time_range_end: datetime | None = Field(None, description="Latest entry")
