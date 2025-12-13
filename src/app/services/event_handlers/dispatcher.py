"""Event dispatcher for routing blockchain events to handlers."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Type

from app.infrastructure.blockchain.events import EventType, ParsedEvent

logger = logging.getLogger(__name__)


# Handler type
Handler = Callable[[ParsedEvent], Coroutine[Any, Any, None]]


@dataclass
class HandlerStats:
    """Statistics for an event handler."""

    handler_name: str
    event_type: EventType
    events_processed: int = 0
    events_failed: int = 0
    total_processing_time_ms: float = 0.0
    last_processed: datetime | None = None
    last_error: str = ""


@dataclass
class DispatcherStats:
    """Statistics for the event dispatcher."""

    events_dispatched: int = 0
    events_unhandled: int = 0
    errors: int = 0
    handlers_by_type: dict[str, int] = field(default_factory=dict)


class EventHandlerBase(ABC):
    """Base class for event handlers."""

    def __init__(self, event_type: EventType):
        """Initialize handler.

        Args:
            event_type: Type of events this handler processes
        """
        self.event_type = event_type
        self.stats = HandlerStats(
            handler_name=self.__class__.__name__,
            event_type=event_type,
        )

    @abstractmethod
    async def handle(self, event: ParsedEvent) -> None:
        """Handle an event.

        Args:
            event: Parsed blockchain event
        """
        pass

    async def __call__(self, event: ParsedEvent) -> None:
        """Process event with timing and error handling."""
        start_time = datetime.now(timezone.utc)

        try:
            await self.handle(event)
            self.stats.events_processed += 1
            self.stats.last_processed = datetime.now(timezone.utc)

        except Exception as e:
            self.stats.events_failed += 1
            self.stats.last_error = str(e)
            logger.error(f"{self.__class__.__name__} failed: {e}")
            raise

        finally:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self.stats.total_processing_time_ms += elapsed


class EventDispatcher:
    """Routes blockchain events to appropriate handlers.

    Supports:
    - Multiple handlers per event type
    - Handler priority ordering
    - Async event processing
    - Error isolation between handlers
    """

    def __init__(self):
        """Initialize event dispatcher."""
        self._handlers: dict[EventType, list[tuple[int, Handler]]] = {}
        self._stats = DispatcherStats()
        self._middleware: list[Handler] = []

    @property
    def stats(self) -> DispatcherStats:
        """Get dispatcher statistics."""
        return self._stats

    def register_handler(
        self,
        event_type: EventType,
        handler: Handler | EventHandlerBase,
        priority: int = 0,
    ) -> None:
        """Register a handler for an event type.

        Args:
            event_type: Type of events to handle
            handler: Handler function or EventHandlerBase instance
            priority: Handler priority (higher = executed first)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        # Wrap EventHandlerBase as callable
        callable_handler = handler if callable(handler) else handler.__call__

        self._handlers[event_type].append((priority, callable_handler))
        # Sort by priority (descending)
        self._handlers[event_type].sort(key=lambda x: -x[0])

        # Update stats
        self._stats.handlers_by_type[event_type.value] = len(
            self._handlers[event_type]
        )

        logger.info(
            f"Registered handler for {event_type.value} "
            f"(priority={priority}, total={len(self._handlers[event_type])})"
        )

    def unregister_handler(
        self,
        event_type: EventType,
        handler: Handler | EventHandlerBase,
    ) -> bool:
        """Unregister a handler.

        Args:
            event_type: Event type to unregister from
            handler: Handler to unregister

        Returns:
            True if handler was found and removed
        """
        if event_type not in self._handlers:
            return False

        callable_handler = handler if callable(handler) else handler.__call__

        original_length = len(self._handlers[event_type])
        self._handlers[event_type] = [
            (p, h) for p, h in self._handlers[event_type] if h != callable_handler
        ]

        removed = len(self._handlers[event_type]) < original_length
        if removed:
            self._stats.handlers_by_type[event_type.value] = len(
                self._handlers[event_type]
            )

        return removed

    def add_middleware(self, middleware: Handler) -> None:
        """Add middleware that runs before all handlers.

        Args:
            middleware: Middleware function
        """
        self._middleware.append(middleware)

    async def dispatch(self, event: ParsedEvent) -> bool:
        """Dispatch an event to registered handlers.

        Args:
            event: Event to dispatch

        Returns:
            True if at least one handler processed the event
        """
        self._stats.events_dispatched += 1

        # Run middleware first
        for middleware in self._middleware:
            try:
                await middleware(event)
            except Exception as e:
                logger.error(f"Middleware error: {e}")
                self._stats.errors += 1

        # Get handlers for this event type
        handlers = self._handlers.get(event.event_type, [])

        if not handlers:
            self._stats.events_unhandled += 1
            logger.debug(f"No handlers for event type: {event.event_type}")
            return False

        # Execute handlers in priority order
        handled = False
        for priority, handler in handlers:
            try:
                await handler(event)
                handled = True
            except Exception as e:
                logger.error(
                    f"Handler error for {event.event_type}: {e}"
                )
                self._stats.errors += 1

        return handled

    async def dispatch_batch(self, events: list[ParsedEvent]) -> int:
        """Dispatch multiple events.

        Args:
            events: List of events to dispatch

        Returns:
            Number of events successfully handled
        """
        handled_count = 0
        for event in events:
            if await self.dispatch(event):
                handled_count += 1
        return handled_count

    async def dispatch_parallel(
        self,
        events: list[ParsedEvent],
        max_concurrent: int = 10,
    ) -> int:
        """Dispatch events in parallel with concurrency limit.

        Args:
            events: Events to dispatch
            max_concurrent: Maximum concurrent dispatches

        Returns:
            Number of events successfully handled
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        handled_count = 0

        async def dispatch_with_semaphore(event: ParsedEvent) -> bool:
            async with semaphore:
                return await self.dispatch(event)

        results = await asyncio.gather(
            *[dispatch_with_semaphore(e) for e in events],
            return_exceptions=True,
        )

        for result in results:
            if result is True:
                handled_count += 1

        return handled_count

    def get_registered_types(self) -> list[EventType]:
        """Get list of event types with registered handlers."""
        return list(self._handlers.keys())

    def get_handler_count(self, event_type: EventType) -> int:
        """Get number of handlers for an event type."""
        return len(self._handlers.get(event_type, []))

    def clear_handlers(self, event_type: EventType | None = None) -> None:
        """Clear handlers.

        Args:
            event_type: Specific type to clear, or None for all
        """
        if event_type:
            self._handlers.pop(event_type, None)
            self._stats.handlers_by_type.pop(event_type.value, None)
        else:
            self._handlers.clear()
            self._stats.handlers_by_type.clear()


# Singleton dispatcher instance
_dispatcher: EventDispatcher | None = None


def get_event_dispatcher() -> EventDispatcher:
    """Get or create event dispatcher singleton."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = EventDispatcher()
    return _dispatcher
