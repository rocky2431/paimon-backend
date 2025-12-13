"""Tests for metrics and tracing services."""

import pytest

from app.services.metrics import (
    MetricType,
    MetricsCollector,
    SpanContext,
    SpanKind,
    SpanStatus,
    TracingService,
    get_metrics_collector,
    get_tracing_service,
)


class TestMetricsCollector:
    """Tests for metrics collector."""

    @pytest.fixture
    def collector(self):
        """Create fresh collector."""
        return MetricsCollector()

    def test_inc_counter(self, collector):
        """Test incrementing counter."""
        collector.inc_counter("requests_total")
        collector.inc_counter("requests_total")
        collector.inc_counter("requests_total", value=5)

        assert collector.get_counter("requests_total") == 7

    def test_counter_with_labels(self, collector):
        """Test counter with labels."""
        collector.inc_counter("requests_total", labels={"method": "GET"})
        collector.inc_counter("requests_total", labels={"method": "POST"})
        collector.inc_counter("requests_total", labels={"method": "GET"})

        assert collector.get_counter("requests_total", {"method": "GET"}) == 2
        assert collector.get_counter("requests_total", {"method": "POST"}) == 1

    def test_set_gauge(self, collector):
        """Test setting gauge."""
        collector.set_gauge("temperature", 25.5)
        assert collector.get_gauge("temperature") == 25.5

        collector.set_gauge("temperature", 30.0)
        assert collector.get_gauge("temperature") == 30.0

    def test_inc_dec_gauge(self, collector):
        """Test incrementing/decrementing gauge."""
        collector.set_gauge("connections", 10)
        collector.inc_gauge("connections", 5)
        assert collector.get_gauge("connections") == 15

        collector.dec_gauge("connections", 3)
        assert collector.get_gauge("connections") == 12

    def test_histogram(self, collector):
        """Test histogram observations."""
        for v in [0.1, 0.2, 0.5, 1.0, 2.0]:
            collector.observe_histogram("request_duration", v)

        stats = collector.get_histogram_stats("request_duration")

        assert stats["count"] == 5
        assert stats["sum"] == 3.8
        assert stats["min"] == 0.1
        assert stats["max"] == 2.0
        assert stats["avg"] == 0.76

    def test_histogram_buckets(self, collector):
        """Test histogram bucket counts."""
        for v in [0.01, 0.05, 0.1, 0.5, 1.0, 5.0]:
            collector.observe_histogram("latency", v)

        stats = collector.get_histogram_stats("latency")
        buckets = stats["buckets"]

        # Check some bucket counts
        assert any(b["le"] == 0.05 and b["count"] == 2 for b in buckets)
        assert any(b["le"] == 0.1 and b["count"] == 3 for b in buckets)
        assert any(b["le"] == 1 and b["count"] == 5 for b in buckets)

    def test_time_function(self, collector):
        """Test timing context manager."""
        import time

        with collector.time_function("operation_duration"):
            time.sleep(0.01)

        stats = collector.get_histogram_stats("operation_duration")
        assert stats["count"] == 1
        assert stats["avg"] > 0.01

    def test_register_metric(self, collector):
        """Test registering metric help text."""
        collector.register_metric("my_counter", "My counter description")
        collector.inc_counter("my_counter")

        metrics = collector.get_all_metrics()
        metric = next((m for m in metrics if m.name == "my_counter"), None)

        assert metric is not None
        assert metric.help_text == "My counter description"

    def test_export_prometheus(self, collector):
        """Test Prometheus export format."""
        collector.register_metric("http_requests", "Total HTTP requests")
        collector.inc_counter("http_requests", labels={"status": "200"})
        collector.set_gauge("active_connections", 42)

        output = collector.export_prometheus()

        assert "# HELP http_requests Total HTTP requests" in output
        assert "# TYPE http_requests counter" in output
        assert 'http_requests{status="200"} 1' in output
        assert "# TYPE active_connections gauge" in output
        assert "active_connections 42" in output

    def test_get_all_metrics(self, collector):
        """Test getting all metrics."""
        collector.inc_counter("counter1")
        collector.set_gauge("gauge1", 10)

        metrics = collector.get_all_metrics()

        assert len(metrics) == 2
        names = [m.name for m in metrics]
        assert "counter1" in names
        assert "gauge1" in names

    def test_clear(self, collector):
        """Test clearing metrics."""
        collector.inc_counter("counter1")
        collector.set_gauge("gauge1", 10)

        collector.clear()

        assert collector.get_counter("counter1") == 0
        assert collector.get_gauge("gauge1") == 0


class TestTracingService:
    """Tests for tracing service."""

    @pytest.fixture
    def tracer(self):
        """Create fresh tracer."""
        return TracingService(service_name="test-service")

    def test_start_span(self, tracer):
        """Test starting a span."""
        active = tracer.start_span("test-operation")

        assert active.span.name == "test-operation"
        assert active.span.trace_id is not None
        assert active.span.span_id is not None
        assert active.span.service_name == "test-service"

        active.end()

    def test_span_context_manager(self, tracer):
        """Test span context manager."""
        with tracer.span("my-span") as active:
            active.set_attribute("key", "value")
            active.add_event("something happened")

        spans = tracer.get_recent_spans()
        assert len(spans) == 1
        assert spans[0].name == "my-span"
        assert spans[0].attributes["key"] == "value"
        assert len(spans[0].events) == 1

    def test_nested_spans(self, tracer):
        """Test nested spans."""
        with tracer.span("parent") as parent:
            with tracer.span("child", parent_context=parent.context) as child:
                assert child.span.parent_span_id == parent.span.span_id
                assert child.span.trace_id == parent.span.trace_id

        spans = tracer.get_recent_spans()
        assert len(spans) == 2

    def test_span_error_handling(self, tracer):
        """Test span error handling."""
        try:
            with tracer.span("failing-span") as active:
                raise ValueError("Test error")
        except ValueError:
            pass

        spans = tracer.get_recent_spans()
        assert spans[0].status == SpanStatus.ERROR
        assert "Test error" in spans[0].status_message
        # Error type is in the exception event
        assert len(spans[0].events) == 1
        assert spans[0].events[0].attributes["exception.type"] == "ValueError"

    def test_span_duration(self, tracer):
        """Test span duration tracking."""
        import time

        with tracer.span("timed-span"):
            time.sleep(0.01)

        spans = tracer.get_recent_spans()
        assert spans[0].duration_ms >= 10

    def test_span_kinds(self, tracer):
        """Test different span kinds."""
        with tracer.span("server-span", kind=SpanKind.SERVER):
            pass
        with tracer.span("client-span", kind=SpanKind.CLIENT):
            pass

        spans = tracer.get_recent_spans()
        kinds = [s.kind for s in spans]
        assert SpanKind.SERVER in kinds
        assert SpanKind.CLIENT in kinds

    def test_get_trace(self, tracer):
        """Test getting trace by ID."""
        with tracer.span("span1") as active:
            trace_id = active.span.trace_id

        with tracer.span("span2", parent_context=SpanContext(
            trace_id=trace_id,
            span_id="fake-parent",
        )):
            pass

        # Create a different trace
        with tracer.span("different-trace"):
            pass

        trace_spans = tracer.get_trace(trace_id)
        assert len(trace_spans) == 2

    def test_get_span(self, tracer):
        """Test getting span by ID."""
        with tracer.span("test-span") as active:
            span_id = active.span.span_id

        span = tracer.get_span(span_id)
        assert span is not None
        assert span.span_id == span_id

    def test_get_span_not_found(self, tracer):
        """Test getting nonexistent span."""
        span = tracer.get_span("nonexistent")
        assert span is None

    def test_get_stats(self, tracer):
        """Test getting tracing stats."""
        with tracer.span("span1"):
            pass
        with tracer.span("span2"):
            pass
        try:
            with tracer.span("failing"):
                raise Exception("error")
        except:
            pass

        stats = tracer.get_stats()

        assert stats["total_spans"] == 3
        assert stats["traces"] == 3
        assert stats["error_rate"] > 0

    def test_clear(self, tracer):
        """Test clearing spans."""
        with tracer.span("span1"):
            pass

        tracer.clear()

        assert len(tracer.get_recent_spans()) == 0


class TestSingletons:
    """Tests for singleton patterns."""

    def test_get_metrics_collector_singleton(self):
        """Test metrics collector singleton."""
        import app.services.metrics.collector as collector_module

        collector_module._metrics_collector = None

        c1 = get_metrics_collector()
        c2 = get_metrics_collector()

        assert c1 is c2

    def test_get_tracing_service_singleton(self):
        """Test tracing service singleton."""
        import app.services.metrics.tracing as tracing_module

        tracing_module._tracing_service = None

        t1 = get_tracing_service()
        t2 = get_tracing_service()

        assert t1 is t2
