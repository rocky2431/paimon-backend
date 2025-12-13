"""Event handlers module."""

from app.services.event_handlers.dispatcher import (
    DispatcherStats,
    EventDispatcher,
    EventHandlerBase,
    HandlerStats,
    get_event_dispatcher,
)
from app.services.event_handlers.handlers import (
    AssetAddedHandler,
    AssetRemovedHandler,
    DepositHandler,
    EmergencyModeChangedHandler,
    RebalanceExecutedHandler,
    RedemptionApprovedHandler,
    RedemptionCancelledHandler,
    RedemptionRejectedHandler,
    RedemptionRequestedHandler,
    RedemptionSettledHandler,
    WithdrawHandler,
    register_all_handlers,
)

__all__ = [
    # Dispatcher
    "EventDispatcher",
    "EventHandlerBase",
    "HandlerStats",
    "DispatcherStats",
    "get_event_dispatcher",
    # Handlers
    "DepositHandler",
    "WithdrawHandler",
    "RedemptionRequestedHandler",
    "RedemptionApprovedHandler",
    "RedemptionRejectedHandler",
    "RedemptionSettledHandler",
    "RedemptionCancelledHandler",
    "EmergencyModeChangedHandler",
    "AssetAddedHandler",
    "AssetRemovedHandler",
    "RebalanceExecutedHandler",
    "register_all_handlers",
]
