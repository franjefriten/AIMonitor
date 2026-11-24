from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from aimonitor.core.event import (
    LogEvent,
    LogStatus,
    MCPEvent,
    MetricEvent,
    MetricType,
    SpanEvent,
    Status,
)
from aimonitor.core.registry import registry
from aimonitor.exporters.opentelemetry import OpenTelemetryExporter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opentelemetry_exporter_builds_private_nested_trace(monkeypatch):
    pytest.importorskip(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        reason="The opentelemetry extra is required for this integration test",
    )
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp_trace_exporter

    memory_exporter = InMemorySpanExporter()
    received_headers = {}

    def create_otlp_exporter(endpoint, headers=None):
        received_headers.update(headers or {})
        return memory_exporter

    monkeypatch.setattr(
        otlp_trace_exporter,
        "OTLPSpanExporter",
        create_otlp_exporter,
    )
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    global_provider = trace.get_tracer_provider()

    await registry.reset()
    exporter = OpenTelemetryExporter(
        enabled=True,
        service_name="integration-test",
        span_prefix="mcp.tool",
        headers={"Authorization": "Bearer integration-token"},
        traces_enabled=True,
    )
    await exporter.connect()
    assert received_headers == {
        "Authorization": "Bearer integration-token"
    }
    timestamp = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    trace_id = str(uuid4())
    parent = SpanEvent(
        trace_id=trace_id,
        span_id="parent-span",
        parent_id=None,
        operation_name="parent-operation",
        timestamp=timestamp - timedelta(milliseconds=400),
        delta=0.2,
    )
    child = SpanEvent(
        trace_id=trace_id,
        span_id="child-span",
        parent_id="parent-span",
        operation_name="child-operation",
        timestamp=timestamp - timedelta(milliseconds=300),
        delta=0.1,
        status=Status.FAILURE,
        error="nested failure",
    )
    root = MCPEvent(
        trace_id=trace_id,
        tool_name="successful_tool",
        args={"secret": "not exported"},
        result={"secret": "not exported"},
        metadata={"secret": "not exported"},
        timestamp=timestamp,
        delta=0.5,
        status=Status.SUCCESS,
    )

    try:
        registry.register(exporter)
        await registry.dispatch([child, parent, root])
        await registry._queue.join()
        await registry.shutdown()

        spans_by_name = {
            span.name: span
            for span in memory_exporter.get_finished_spans()
        }
        assert set(spans_by_name) == {
            "mcp.tool.successful_tool",
            "parent-operation",
            "child-operation",
        }

        root_span = spans_by_name["mcp.tool.successful_tool"]
        parent_span = spans_by_name["parent-operation"]
        child_span = spans_by_name["child-operation"]
        assert root_span.parent is None
        assert parent_span.parent.span_id == root_span.context.span_id
        assert child_span.parent.span_id == parent_span.context.span_id
        assert len({root_span.context.trace_id, parent_span.context.trace_id, child_span.context.trace_id}) == 1
        assert root_span.resource.attributes["service.name"] == "integration-test"
        assert root_span.start_time == int(timestamp.timestamp() * 1_000_000_000) - 500_000_000
        assert root_span.end_time == int(timestamp.timestamp() * 1_000_000_000)
        assert "mcp.args" not in root_span.attributes
        assert "mcp.result" not in root_span.attributes
        assert "mcp.metadata" not in root_span.attributes
        assert child_span.attributes["mcp.status"] == Status.FAILURE.value
        assert trace.get_tracer_provider() is global_provider
    finally:
        await registry.reset()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opentelemetry_exporter_maps_metrics_and_logs(monkeypatch):
    pytest.importorskip(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        reason="The opentelemetry extra is required for this integration test",
    )
    from opentelemetry.exporter.otlp.proto.http import _log_exporter, metric_exporter
    try:
        from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
    except ImportError:
        from opentelemetry.sdk._logs.export import InMemoryLogExporter as InMemoryLogRecordExporter
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    import opentelemetry.sdk.metrics.export as sdk_metric_export

    log_exporter = InMemoryLogRecordExporter()
    received_headers = {}
    metric_readers = []

    def create_log_exporter(endpoint, headers=None):
        received_headers["logs"] = headers
        return log_exporter

    def create_metric_exporter(endpoint, headers=None):
        received_headers["metrics"] = headers
        return object()

    def make_metric_reader(exporter, export_interval_millis):
        reader = InMemoryMetricReader()
        metric_readers.append(reader)
        return reader

    monkeypatch.setattr(_log_exporter, "OTLPLogExporter", create_log_exporter)
    monkeypatch.setattr(metric_exporter, "OTLPMetricExporter", create_metric_exporter)
    monkeypatch.setattr(
        sdk_metric_export,
        "PeriodicExportingMetricReader",
        make_metric_reader,
    )
    exporter = OpenTelemetryExporter(
        enabled=True,
        service_name="signal-test",
        headers={"X-Api-Key": "integration-api-key"},
        metrics_enabled=True,
        logs_enabled=True,
    )
    await exporter.connect()
    assert received_headers == {
        "logs": {"X-Api-Key": "integration-api-key"},
        "metrics": {"X-Api-Key": "integration-api-key"},
    }

    try:
        await exporter.export(
            [
                MetricEvent(
                    name="requests_total",
                    value=2,
                    metric_type=MetricType.COUNTER,
                    unit="requests",
                    labels={"route": "/items"},
                    environment="DEV",
                    version="1.2",
                ),
                MetricEvent(
                    name="request_duration",
                    value=1.5,
                    metric_type=MetricType.HISTOGRAM,
                    unit="s",
                ),
                MetricEvent(
                    name="queue_depth",
                    value=7,
                    metric_type=MetricType.GAUGE,
                    unit="items",
                ),
                LogEvent(
                    message="service unavailable",
                    level=LogStatus.CRITICAL,
                    source="worker",
                    environment="DEV",
                    version="1.2",
                    metadata={"private": "omitted"},
                ),
            ]
        )
        metric_data = metric_readers[0].get_metrics_data()
        metrics = {
            metric.name: metric
            for resource_metrics in metric_data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        }
        assert set(metrics) == {"requests_total", "request_duration", "queue_depth"}
        assert metrics["requests_total"].unit == "requests"
        counter_point = metrics["requests_total"].data.data_points[0]
        assert counter_point.value == 2
        assert counter_point.attributes == {
            "route": "/items",
            "environment": "DEV",
            "version": "1.2",
        }
        assert metrics["request_duration"].data.data_points[0].count == 1
        assert metrics["queue_depth"].data.data_points[0].value == 7
    finally:
        await exporter.close()

    log_record = log_exporter.get_finished_logs()[0].log_record
    assert log_record.body == "service unavailable"
    assert log_record.severity_text == "critical"
    assert log_record.attributes == {
        "source": "worker",
        "environment": "DEV",
        "version": "1.2",
    }
