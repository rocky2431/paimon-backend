"""Tests for event dispatcher and handlers."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.blockchain.events import EventType, ParsedEvent
from app.services.event_handlers.dispatcher import (
    EventDispatcher,
    EventHandlerBase,
    HandlerStats,
    get_event_dispatcher,
)
from app.services.event_handlers.handlers import (
    DepositHandler,
    EmergencyModeChangedHandler,
    RedemptionRequestedHandler,
    register_all_handlers,
)


def create_test_event(
    event_type: EventType = EventType.DEPOSIT,
    args: dict = None,
) -> ParsedEvent:
    """Create a test event."""
    return ParsedEvent(
        event_type=event_type,
        tx_hash="0x123",
        block_number=100,
        log_index=0,
        block_timestamp=datetime.now(timezone.utc),
        contract_address="0x456",
        args=args or {},
        raw_data={},
    )


class TestEventDispatcher:
    """Tests for EventDispatcher."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dispatcher = EventDispatcher()

    @pytest.mark.asyncio
    async def test_register_handler(self):
        """Test registering a handler."""

        async def handler(event):
            pass

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)

        assert self.dispatcher.get_handler_count(EventType.DEPOSIT) == 1

    @pytest.mark.asyncio
    async def test_dispatch_to_handler(self):
        """Test dispatching event to handler."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)

        event = create_test_event(EventType.DEPOSIT)
        result = await self.dispatcher.dispatch(event)

        assert result is True
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_dispatch_unhandled_event(self):
        """Test dispatching event with no handler."""
        event = create_test_event(EventType.DEPOSIT)
        result = await self.dispatcher.dispatch(event)

        assert result is False
        assert self.dispatcher.stats.events_unhandled == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_type(self):
        """Test multiple handlers for same event type."""
        calls = []

        async def handler1(event):
            calls.append("handler1")

        async def handler2(event):
            calls.append("handler2")

        self.dispatcher.register_handler(EventType.DEPOSIT, handler1)
        self.dispatcher.register_handler(EventType.DEPOSIT, handler2)

        event = create_test_event(EventType.DEPOSIT)
        await self.dispatcher.dispatch(event)

        assert len(calls) == 2
        assert "handler1" in calls
        assert "handler2" in calls

    @pytest.mark.asyncio
    async def test_handler_priority(self):
        """Test handlers are called in priority order."""
        calls = []

        async def low_priority(event):
            calls.append("low")

        async def high_priority(event):
            calls.append("high")

        self.dispatcher.register_handler(EventType.DEPOSIT, low_priority, priority=1)
        self.dispatcher.register_handler(EventType.DEPOSIT, high_priority, priority=10)

        event = create_test_event(EventType.DEPOSIT)
        await self.dispatcher.dispatch(event)

        # High priority should be first
        assert calls[0] == "high"
        assert calls[1] == "low"

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self):
        """Test errors in one handler don't affect others."""
        calls = []

        async def failing_handler(event):
            raise Exception("Handler error")

        async def working_handler(event):
            calls.append("working")

        self.dispatcher.register_handler(EventType.DEPOSIT, failing_handler, priority=10)
        self.dispatcher.register_handler(EventType.DEPOSIT, working_handler, priority=1)

        event = create_test_event(EventType.DEPOSIT)
        await self.dispatcher.dispatch(event)

        # Working handler should still be called
        assert "working" in calls
        assert self.dispatcher.stats.errors == 1

    @pytest.mark.asyncio
    async def test_unregister_handler(self):
        """Test unregistering a handler."""

        async def handler(event):
            pass

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)
        assert self.dispatcher.get_handler_count(EventType.DEPOSIT) == 1

        result = self.dispatcher.unregister_handler(EventType.DEPOSIT, handler)
        assert result is True
        assert self.dispatcher.get_handler_count(EventType.DEPOSIT) == 0

    @pytest.mark.asyncio
    async def test_middleware(self):
        """Test middleware runs before handlers."""
        calls = []

        async def middleware(event):
            calls.append("middleware")

        async def handler(event):
            calls.append("handler")

        self.dispatcher.add_middleware(middleware)
        self.dispatcher.register_handler(EventType.DEPOSIT, handler)

        event = create_test_event(EventType.DEPOSIT)
        await self.dispatcher.dispatch(event)

        assert calls == ["middleware", "handler"]

    @pytest.mark.asyncio
    async def test_dispatch_batch(self):
        """Test dispatching multiple events."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)

        events = [
            create_test_event(EventType.DEPOSIT),
            create_test_event(EventType.DEPOSIT),
            create_test_event(EventType.DEPOSIT),
        ]

        count = await self.dispatcher.dispatch_batch(events)

        assert count == 3
        assert len(events_received) == 3

    @pytest.mark.asyncio
    async def test_dispatch_parallel(self):
        """Test parallel event dispatching."""
        events_received = []

        async def handler(event):
            events_received.append(event)
            await asyncio.sleep(0.01)

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)

        events = [create_test_event(EventType.DEPOSIT) for _ in range(5)]

        count = await self.dispatcher.dispatch_parallel(events, max_concurrent=2)

        assert count == 5
        assert len(events_received) == 5

    def test_get_registered_types(self):
        """Test getting registered event types."""

        async def handler(event):
            pass

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)
        self.dispatcher.register_handler(EventType.WITHDRAW, handler)

        types = self.dispatcher.get_registered_types()

        assert EventType.DEPOSIT in types
        assert EventType.WITHDRAW in types

    def test_clear_handlers(self):
        """Test clearing handlers."""

        async def handler(event):
            pass

        self.dispatcher.register_handler(EventType.DEPOSIT, handler)
        self.dispatcher.register_handler(EventType.WITHDRAW, handler)

        self.dispatcher.clear_handlers(EventType.DEPOSIT)
        assert self.dispatcher.get_handler_count(EventType.DEPOSIT) == 0
        assert self.dispatcher.get_handler_count(EventType.WITHDRAW) == 1

        self.dispatcher.clear_handlers()
        assert len(self.dispatcher.get_registered_types()) == 0


class TestEventHandlerBase:
    """Tests for EventHandlerBase."""

    @pytest.mark.asyncio
    async def test_handler_base_stats(self):
        """Test handler base statistics tracking."""

        class TestHandler(EventHandlerBase):
            async def handle(self, event):
                pass

        handler = TestHandler(EventType.DEPOSIT)
        event = create_test_event(EventType.DEPOSIT)

        await handler(event)

        assert handler.stats.events_processed == 1
        assert handler.stats.last_processed is not None

    @pytest.mark.asyncio
    async def test_handler_base_error_stats(self):
        """Test handler base error statistics."""

        class FailingHandler(EventHandlerBase):
            async def handle(self, event):
                raise Exception("Test error")

        handler = FailingHandler(EventType.DEPOSIT)
        event = create_test_event(EventType.DEPOSIT)

        with pytest.raises(Exception):
            await handler(event)

        assert handler.stats.events_failed == 1
        assert "Test error" in handler.stats.last_error


class TestConcreteHandlers:
    """Tests for concrete event handlers."""

    @pytest.mark.asyncio
    async def test_deposit_handler(self):
        """Test DepositHandler processes events."""
        handler = DepositHandler()

        event = create_test_event(
            EventType.DEPOSIT,
            args={"sender": "0x123", "assets": 1000, "shares": 500},
        )

        await handler(event)

        assert handler.stats.events_processed == 1

    @pytest.mark.asyncio
    async def test_redemption_requested_handler(self):
        """Test RedemptionRequestedHandler processes events."""
        handler = RedemptionRequestedHandler()

        event = create_test_event(
            EventType.REDEMPTION_REQUESTED,
            args={
                "request_id": 1,
                "owner": "0x123",
                "shares": 1000,
                "gross_amount": 2000,
                "channel": 0,
            },
        )

        await handler(event)

        assert handler.stats.events_processed == 1

    @pytest.mark.asyncio
    async def test_emergency_handler(self):
        """Test EmergencyModeChangedHandler processes events."""
        handler = EmergencyModeChangedHandler()

        event = create_test_event(
            EventType.EMERGENCY_MODE_CHANGED,
            args={"enabled": True, "triggered_by": "0x999"},
        )

        await handler(event)

        assert handler.stats.events_processed == 1


class TestRegisterAllHandlers:
    """Tests for register_all_handlers function."""

    def test_register_all_handlers(self):
        """Test all handlers are registered."""
        dispatcher = EventDispatcher()
        register_all_handlers(dispatcher)

        # Check main event types have handlers
        assert dispatcher.get_handler_count(EventType.DEPOSIT) >= 1
        assert dispatcher.get_handler_count(EventType.REDEMPTION_REQUESTED) >= 1
        assert dispatcher.get_handler_count(EventType.EMERGENCY_MODE_CHANGED) >= 1

    def test_emergency_handler_highest_priority(self):
        """Test emergency handler has highest priority."""
        dispatcher = EventDispatcher()
        register_all_handlers(dispatcher)

        # Emergency should have priority 100
        handlers = dispatcher._handlers.get(EventType.EMERGENCY_MODE_CHANGED, [])
        assert len(handlers) >= 1
        # First handler (highest priority)
        assert handlers[0][0] == 100
