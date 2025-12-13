"""Risk monitoring service module."""

from app.services.risk.schemas import (
    ConcentrationRisk,
    LiquidityRisk,
    PriceRisk,
    RedemptionPressure,
    RiskAlert,
    RiskAssessment,
    RiskConfig,
    RiskIndicator,
    RiskLevel,
    RiskScore,
    RiskType,
)
from app.services.risk.monitor import (
    RiskMonitorService,
    get_risk_monitor_service,
)
from app.services.risk.notification_schemas import (
    AlertRoutingConfig,
    ChannelConfig,
    EmergencyProtocol,
    EmergencyTrigger,
    EscalationRule,
    NotificationChannel,
    NotificationMessage,
    NotificationPriority,
    NotificationRecord,
    NotificationStatus,
    SlackConfig,
    TelegramConfig,
)
from app.services.risk.notification_service import (
    NotificationService,
    get_notification_service,
)
from app.services.risk.alert_router import (
    AlertRouter,
    get_alert_router,
)

__all__ = [
    # Enums
    "RiskType",
    "RiskLevel",
    "NotificationChannel",
    "NotificationPriority",
    "NotificationStatus",
    # Schemas
    "RiskConfig",
    "RiskIndicator",
    "LiquidityRisk",
    "PriceRisk",
    "ConcentrationRisk",
    "RedemptionPressure",
    "RiskScore",
    "RiskAlert",
    "RiskAssessment",
    # Notification schemas
    "ChannelConfig",
    "SlackConfig",
    "TelegramConfig",
    "NotificationMessage",
    "NotificationRecord",
    "EscalationRule",
    "AlertRoutingConfig",
    "EmergencyProtocol",
    "EmergencyTrigger",
    # Services
    "RiskMonitorService",
    "get_risk_monitor_service",
    "NotificationService",
    "get_notification_service",
    "AlertRouter",
    "get_alert_router",
]
