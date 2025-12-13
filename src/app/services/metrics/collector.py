"""Metrics collector service for Prometheus-style metrics."""

import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Types of metrics."""

    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Can go up or down
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"  # Similar to histogram


class MetricValue(BaseModel):
    """A metric value."""

    name: str = Field(..., description="Metric name")
    metric_type: MetricType = Field(..., description="Metric type")
    value: float = Field(..., description="Current value")
    labels: dict[str, str] = Field(default_factory=dict, description="Metric labels")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp")
    help_text: str = Field(default="", description="Metric description")


class HistogramBucket(BaseModel):
    """Histogram bucket."""

    le: float = Field(..., description="Bucket upper bound")
    count: int = Field(default=0, description="Count in bucket")


class MetricsCollector:
    """Service for collecting and exposing metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._help_texts: dict[str, str] = {}
        self._default_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]

    def _labels_key(self, labels: dict[str, str] | None) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    def register_metric(self, name: str, help_text: str) -> None:
        """Register a metric with help text.

        Args:
            name: Metric name
            help_text: Description
        """
        self._help_texts[name] = help_text

    def inc_counter(
        self,
        name: str,
        value: float = 1,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Increment a counter.

        Args:
            name: Counter name
            value: Increment value (default 1)
            labels: Optional labels

        Returns:
            New counter value
        """
        key = self._labels_key(labels)
        self._counters[name][key] += value
        return self._counters[name][key]

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value.

        Args:
            name: Gauge name
            value: New value
            labels: Optional labels
        """
        key = self._labels_key(labels)
        self._gauges[name][key] = value

    def inc_gauge(
        self,
        name: str,
        value: float = 1,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Increment a gauge.

        Args:
            name: Gauge name
            value: Increment value
            labels: Optional labels

        Returns:
            New gauge value
        """
        key = self._labels_key(labels)
        self._gauges[name][key] += value
        return self._gauges[name][key]

    def dec_gauge(
        self,
        name: str,
        value: float = 1,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Decrement a gauge.

        Args:
            name: Gauge name
            value: Decrement value
            labels: Optional labels

        Returns:
            New gauge value
        """
        key = self._labels_key(labels)
        self._gauges[name][key] -= value
        return self._gauges[name][key]

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram observation.

        Args:
            name: Histogram name
            value: Observed value
            labels: Optional labels
        """
        key = self._labels_key(labels)
        self._histograms[name][key].append(value)

    def get_counter(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Get counter value.

        Args:
            name: Counter name
            labels: Optional labels

        Returns:
            Counter value
        """
        key = self._labels_key(labels)
        return self._counters[name][key]

    def get_gauge(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Get gauge value.

        Args:
            name: Gauge name
            labels: Optional labels

        Returns:
            Gauge value
        """
        key = self._labels_key(labels)
        return self._gauges[name][key]

    def get_histogram_stats(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get histogram statistics.

        Args:
            name: Histogram name
            labels: Optional labels

        Returns:
            Statistics dict
        """
        key = self._labels_key(labels)
        values = self._histograms[name][key]

        if not values:
            return {
                "count": 0,
                "sum": 0,
                "min": 0,
                "max": 0,
                "avg": 0,
                "buckets": [],
            }

        bucket_counts = []
        for le in self._default_buckets:
            count = sum(1 for v in values if v <= le)
            bucket_counts.append({"le": le, "count": count})
        bucket_counts.append({"le": float("inf"), "count": len(values)})

        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "buckets": bucket_counts,
        }

    def time_function(self, name: str, labels: dict[str, str] | None = None):
        """Context manager for timing function execution.

        Args:
            name: Histogram name
            labels: Optional labels

        Usage:
            with collector.time_function("http_request_duration"):
                # do something
        """
        class Timer:
            def __init__(timer_self):
                timer_self.start = None

            def __enter__(timer_self):
                timer_self.start = time.time()
                return timer_self

            def __exit__(timer_self, *args):
                duration = time.time() - timer_self.start
                self.observe_histogram(name, duration, labels)

        return Timer()

    def get_all_metrics(self) -> list[MetricValue]:
        """Get all metrics as a list.

        Returns:
            List of all metrics
        """
        metrics = []

        # Counters
        for name, values in self._counters.items():
            for key, value in values.items():
                labels = dict(kv.split("=") for kv in key.split(",") if kv) if key else {}
                labels = {k: v.strip('"') for k, v in labels.items()}
                metrics.append(
                    MetricValue(
                        name=name,
                        metric_type=MetricType.COUNTER,
                        value=value,
                        labels=labels,
                        help_text=self._help_texts.get(name, ""),
                    )
                )

        # Gauges
        for name, values in self._gauges.items():
            for key, value in values.items():
                labels = dict(kv.split("=") for kv in key.split(",") if kv) if key else {}
                labels = {k: v.strip('"') for k, v in labels.items()}
                metrics.append(
                    MetricValue(
                        name=name,
                        metric_type=MetricType.GAUGE,
                        value=value,
                        labels=labels,
                        help_text=self._help_texts.get(name, ""),
                    )
                )

        return metrics

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        # Counters
        for name, values in self._counters.items():
            if name in self._help_texts:
                lines.append(f"# HELP {name} {self._help_texts[name]}")
            lines.append(f"# TYPE {name} counter")
            for key, value in values.items():
                if key:
                    lines.append(f"{name}{{{key}}} {value}")
                else:
                    lines.append(f"{name} {value}")

        # Gauges
        for name, values in self._gauges.items():
            if name in self._help_texts:
                lines.append(f"# HELP {name} {self._help_texts[name]}")
            lines.append(f"# TYPE {name} gauge")
            for key, value in values.items():
                if key:
                    lines.append(f"{name}{{{key}}} {value}")
                else:
                    lines.append(f"{name} {value}")

        # Histograms
        for name, values in self._histograms.items():
            if name in self._help_texts:
                lines.append(f"# HELP {name} {self._help_texts[name]}")
            lines.append(f"# TYPE {name} histogram")
            for key, observations in values.items():
                if observations:
                    total_sum = sum(observations)
                    count = len(observations)

                    for le in self._default_buckets:
                        bucket_count = sum(1 for v in observations if v <= le)
                        if key:
                            lines.append(f'{name}_bucket{{{key},le="{le}"}} {bucket_count}')
                        else:
                            lines.append(f'{name}_bucket{{le="{le}"}} {bucket_count}')

                    if key:
                        lines.append(f'{name}_bucket{{{key},le="+Inf"}} {count}')
                        lines.append(f"{name}_sum{{{key}}} {total_sum}")
                        lines.append(f"{name}_count{{{key}}} {count}")
                    else:
                        lines.append(f'{name}_bucket{{le="+Inf"}} {count}')
                        lines.append(f"{name}_sum {total_sum}")
                        lines.append(f"{name}_count {count}")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


# Singleton instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get singleton metrics collector instance.

    Returns:
        The metrics collector
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
