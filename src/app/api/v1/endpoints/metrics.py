"""Metrics and tracing API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services.metrics import (
    MetricValue,
    Span,
    SpanContext,
    get_metrics_collector,
    get_tracing_service,
)

router = APIRouter(prefix="/metrics", tags=["Metrics"])


# Prometheus-compatible metrics endpoint
@router.get("/prometheus", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """Get metrics in Prometheus format.

    Returns:
        Prometheus-formatted metrics
    """
    collector = get_metrics_collector()
    return collector.export_prometheus()


@router.get("/all", response_model=list[MetricValue])
async def get_all_metrics() -> list[MetricValue]:
    """Get all metrics as JSON.

    Returns:
        All metrics
    """
    collector = get_metrics_collector()
    return collector.get_all_metrics()


@router.get("/counter/{name}")
async def get_counter(
    name: str,
    labels: str | None = None,
) -> dict[str, Any]:
    """Get counter value.

    Args:
        name: Counter name
        labels: Comma-separated key=value pairs

    Returns:
        Counter value
    """
    collector = get_metrics_collector()
    label_dict = {}
    if labels:
        for pair in labels.split(","):
            k, v = pair.split("=")
            label_dict[k.strip()] = v.strip()

    value = collector.get_counter(name, label_dict if label_dict else None)
    return {"name": name, "value": value, "labels": label_dict}


@router.get("/gauge/{name}")
async def get_gauge(
    name: str,
    labels: str | None = None,
) -> dict[str, Any]:
    """Get gauge value.

    Args:
        name: Gauge name
        labels: Comma-separated key=value pairs

    Returns:
        Gauge value
    """
    collector = get_metrics_collector()
    label_dict = {}
    if labels:
        for pair in labels.split(","):
            k, v = pair.split("=")
            label_dict[k.strip()] = v.strip()

    value = collector.get_gauge(name, label_dict if label_dict else None)
    return {"name": name, "value": value, "labels": label_dict}


@router.get("/histogram/{name}")
async def get_histogram(
    name: str,
    labels: str | None = None,
) -> dict[str, Any]:
    """Get histogram statistics.

    Args:
        name: Histogram name
        labels: Comma-separated key=value pairs

    Returns:
        Histogram statistics
    """
    collector = get_metrics_collector()
    label_dict = {}
    if labels:
        for pair in labels.split(","):
            k, v = pair.split("=")
            label_dict[k.strip()] = v.strip()

    stats = collector.get_histogram_stats(name, label_dict if label_dict else None)
    return {"name": name, "labels": label_dict, **stats}


# Tracing endpoints
@router.get("/traces/recent", response_model=list[Span])
async def get_recent_traces(limit: int = 100) -> list[Span]:
    """Get recent spans.

    Args:
        limit: Max spans

    Returns:
        Recent spans
    """
    tracer = get_tracing_service()
    return tracer.get_recent_spans(limit)


@router.get("/traces/{trace_id}", response_model=list[Span])
async def get_trace(trace_id: str) -> list[Span]:
    """Get all spans for a trace.

    Args:
        trace_id: Trace ID

    Returns:
        Trace spans
    """
    tracer = get_tracing_service()
    spans = tracer.get_trace(trace_id)

    if not spans:
        raise HTTPException(404, "Trace not found")

    return spans


@router.get("/spans/{span_id}", response_model=Span)
async def get_span(span_id: str) -> Span:
    """Get a specific span.

    Args:
        span_id: Span ID

    Returns:
        The span
    """
    tracer = get_tracing_service()
    span = tracer.get_span(span_id)

    if not span:
        raise HTTPException(404, "Span not found")

    return span


@router.get("/traces/stats")
async def get_tracing_stats() -> dict[str, Any]:
    """Get tracing statistics.

    Returns:
        Statistics
    """
    tracer = get_tracing_service()
    return tracer.get_stats()
