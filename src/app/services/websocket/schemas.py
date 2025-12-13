"""Schemas for WebSocket service."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """WebSocket message types."""

    # Connection lifecycle
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    PING = "PING"
    PONG = "PONG"

    # Subscription management
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    SUBSCRIBED = "SUBSCRIBED"
    UNSUBSCRIBED = "UNSUBSCRIBED"

    # Data updates
    NAV_UPDATE = "NAV_UPDATE"
    RISK_UPDATE = "RISK_UPDATE"
    ALERT_UPDATE = "ALERT_UPDATE"
    FLOW_UPDATE = "FLOW_UPDATE"
    REBALANCE_UPDATE = "REBALANCE_UPDATE"
    REDEMPTION_UPDATE = "REDEMPTION_UPDATE"

    # System events
    SYSTEM_ANNOUNCEMENT = "SYSTEM_ANNOUNCEMENT"
    EMERGENCY_ALERT = "EMERGENCY_ALERT"


class SubscriptionType(str, Enum):
    """Types of subscriptions available."""

    NAV = "NAV"  # NAV updates
    RISK = "RISK"  # Risk score updates
    ALERTS = "ALERTS"  # Alert notifications
    FLOWS = "FLOWS"  # Subscription/redemption flows
    REBALANCE = "REBALANCE"  # Rebalancing updates
    REDEMPTIONS = "REDEMPTIONS"  # Redemption status updates
    ALL = "ALL"  # All updates


class WebSocketMessage(BaseModel):
    """WebSocket message structure."""

    type: MessageType = Field(..., description="Message type")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(), description="Message timestamp"
    )
    data: dict[str, Any] | None = Field(None, description="Message payload")
    error: str | None = Field(None, description="Error message if applicable")

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class SubscriptionRequest(BaseModel):
    """Subscription request from client."""

    subscriptions: list[SubscriptionType] = Field(
        ..., description="Types to subscribe to"
    )


class NavUpdate(BaseModel):
    """NAV update payload."""

    nav: str = Field(..., description="Current NAV value")
    nav_change_24h: str = Field(..., description="24h NAV change %")
    aum: str = Field(..., description="Total AUM")
    updated_at: datetime = Field(..., description="Update timestamp")


class RiskUpdate(BaseModel):
    """Risk update payload."""

    risk_score: int = Field(..., description="Current risk score (0-100)")
    risk_level: str = Field(..., description="Risk level")
    liquidity_score: int = Field(..., description="Liquidity risk score")
    concentration_score: int = Field(..., description="Concentration risk score")
    price_score: int = Field(..., description="Price risk score")
    redemption_score: int = Field(..., description="Redemption pressure score")
    updated_at: datetime = Field(..., description="Update timestamp")


class AlertUpdate(BaseModel):
    """Alert update payload."""

    alert_id: str = Field(..., description="Alert ID")
    alert_type: str = Field(..., description="Alert type")
    severity: str = Field(..., description="Alert severity")
    message: str = Field(..., description="Alert message")
    created_at: datetime = Field(..., description="Alert timestamp")


class FlowUpdate(BaseModel):
    """Flow update payload."""

    flow_type: str = Field(..., description="SUBSCRIPTION or REDEMPTION")
    amount: str = Field(..., description="Flow amount")
    wallet_address: str = Field(..., description="Wallet address")
    status: str = Field(..., description="Flow status")
    updated_at: datetime = Field(..., description="Update timestamp")


class RebalanceUpdate(BaseModel):
    """Rebalance update payload."""

    plan_id: str = Field(..., description="Rebalance plan ID")
    status: str = Field(..., description="Plan status")
    trades_executed: int = Field(..., description="Trades executed")
    trades_total: int = Field(..., description="Total trades")
    updated_at: datetime = Field(..., description="Update timestamp")


class RedemptionUpdate(BaseModel):
    """Redemption update payload."""

    redemption_id: str = Field(..., description="Redemption ID")
    wallet_address: str = Field(..., description="Wallet address")
    amount: str = Field(..., description="Redemption amount")
    status: str = Field(..., description="Redemption status")
    updated_at: datetime = Field(..., description="Update timestamp")
