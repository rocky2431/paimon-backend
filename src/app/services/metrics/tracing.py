"""Tracing service for distributed tracing (OpenTelemetry-style)."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Generator
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpanKind(str, Enum):
    """Type of span."""

    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class SpanStatus(str, Enum):
    """Span status."""

    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


class SpanContext(BaseModel):
    """Span context for propagation."""

    trace_id: str = Field(..., description="Trace ID")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: str | None = Field(None, description="Parent span ID")


class SpanEvent(BaseModel):
    """Event within a span."""

    name: str = Field(..., description="Event name")
    timestamp: datetime = Field(default_factory=datetime.now, description="Event time")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Event attributes")


class Span(BaseModel):
    """A distributed tracing span."""

    trace_id: str = Field(..., description="Trace ID")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: str | None = Field(None, description="Parent span ID")
    name: str = Field(..., description="Span name")
    kind: SpanKind = Field(default=SpanKind.INTERNAL, description="Span kind")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime | None = Field(None, description="End time")
    duration_ms: float | None = Field(None, description="Duration in ms")
    status: SpanStatus = Field(default=SpanStatus.UNSET, description="Status")
    status_message: str | None = Field(None, description="Status message")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Span attributes")
    events: list[SpanEvent] = Field(default_factory=list, description="Span events")
    service_name: str = Field(default="paimon-backend", description="Service name")


class ActiveSpan:
    """Context manager for an active span."""

    def __init__(
        self,
        tracer: "TracingService",
        span: Span,
    ):
        """Initialize active span.

        Args:
            tracer: Tracing service
            span: The span
        """
        self._tracer = tracer
        self._span = span
        self._start_time = time.time()

    @property
    def span(self) -> Span:
        """Get the span."""
        return self._span

    @property
    def context(self) -> SpanContext:
        """Get span context."""
        return SpanContext(
            trace_id=self._span.trace_id,
            span_id=self._span.span_id,
            parent_span_id=self._span.parent_span_id,
        )

    def set_attribute(self, key: str, value: Any) -> None:
        """Set span attribute.

        Args:
            key: Attribute key
            value: Attribute value
        """
        self._span.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add event to span.

        Args:
            name: Event name
            attributes: Event attributes
        """
        event = SpanEvent(
            name=name,
            attributes=attributes or {},
        )
        self._span.events.append(event)

    def set_status(self, status: SpanStatus, message: str | None = None) -> None:
        """Set span status.

        Args:
            status: Status
            message: Optional message
        """
        self._span.status = status
        self._span.status_message = message

    def set_error(self, error: Exception) -> None:
        """Set span error status.

        Args:
            error: The exception
        """
        self._span.status = SpanStatus.ERROR
        self._span.status_message = str(error)
        self.add_event(
            "exception",
            {
                "exception.type": type(error).__name__,
                "exception.message": str(error),
            },
        )

    def end(self) -> None:
        """End the span."""
        self._span.end_time = datetime.now()
        self._span.duration_ms = (time.time() - self._start_time) * 1000

        if self._span.status == SpanStatus.UNSET:
            self._span.status = SpanStatus.OK

        self._tracer._end_span(self._span)


class TracingService:
    """Service for distributed tracing."""

    def __init__(self, service_name: str = "paimon-backend"):
        """Initialize tracing service.

        Args:
            service_name: Name of this service
        """
        self.service_name = service_name
        self._spans: list[Span] = []
        self._active_spans: dict[str, ActiveSpan] = {}
        self._max_spans = 10000

    def _generate_id(self) -> str:
        """Generate a trace/span ID."""
        return uuid4().hex[:16]

    def start_span(
        self,
        name: str,
        *,
        parent_context: SpanContext | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> ActiveSpan:
        """Start a new span.

        Args:
            name: Span name
            parent_context: Optional parent context
            kind: Span kind
            attributes: Initial attributes

        Returns:
            Active span context manager
        """
        if parent_context:
            trace_id = parent_context.trace_id
            parent_span_id = parent_context.span_id
        else:
            trace_id = self._generate_id()
            parent_span_id = None

        span = Span(
            trace_id=trace_id,
            span_id=self._generate_id(),
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            start_time=datetime.now(),
            attributes=attributes or {},
            service_name=self.service_name,
        )

        active = ActiveSpan(self, span)
        self._active_spans[span.span_id] = active

        return active

    @contextmanager
    def span(
        self,
        name: str,
        *,
        parent_context: SpanContext | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[ActiveSpan, None, None]:
        """Context manager for creating spans.

        Args:
            name: Span name
            parent_context: Optional parent context
            kind: Span kind
            attributes: Initial attributes

        Yields:
            Active span
        """
        active = self.start_span(
            name,
            parent_context=parent_context,
            kind=kind,
            attributes=attributes,
        )

        try:
            yield active
        except Exception as e:
            active.set_error(e)
            raise
        finally:
            active.end()

    def _end_span(self, span: Span) -> None:
        """Called when span ends.

        Args:
            span: The ended span
        """
        # Remove from active
        self._active_spans.pop(span.span_id, None)

        # Store span
        self._spans.append(span)

        # Trim if needed
        if len(self._spans) > self._max_spans:
            self._spans = self._spans[-self._max_spans:]

        # Log span
        logger.debug(
            f"[TRACE] {span.name} completed in {span.duration_ms:.2f}ms",
            extra={
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "duration_ms": span.duration_ms,
            },
        )

    def get_trace(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace.

        Args:
            trace_id: Trace ID

        Returns:
            List of spans in the trace
        """
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_recent_spans(self, limit: int = 100) -> list[Span]:
        """Get recent spans.

        Args:
            limit: Max spans to return

        Returns:
            Recent spans
        """
        return self._spans[-limit:]

    def get_span(self, span_id: str) -> Span | None:
        """Get span by ID.

        Args:
            span_id: Span ID

        Returns:
            Span or None
        """
        for span in self._spans:
            if span.span_id == span_id:
                return span
        return None

    def get_stats(self) -> dict[str, Any]:
        """Get tracing statistics.

        Returns:
            Statistics dict
        """
        if not self._spans:
            return {
                "total_spans": 0,
                "active_spans": len(self._active_spans),
                "traces": 0,
                "avg_duration_ms": 0,
                "error_rate": 0,
            }

        traces = set(s.trace_id for s in self._spans)
        durations = [s.duration_ms for s in self._spans if s.duration_ms]
        errors = sum(1 for s in self._spans if s.status == SpanStatus.ERROR)

        return {
            "total_spans": len(self._spans),
            "active_spans": len(self._active_spans),
            "traces": len(traces),
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "error_rate": (errors / len(self._spans)) * 100,
        }

    def clear(self) -> None:
        """Clear all completed spans."""
        self._spans.clear()


# Singleton instance
_tracing_service: TracingService | None = None


def get_tracing_service() -> TracingService:
    """Get singleton tracing service instance.

    Returns:
        The tracing service
    """
    global _tracing_service
    if _tracing_service is None:
        _tracing_service = TracingService()
    return _tracing_service
