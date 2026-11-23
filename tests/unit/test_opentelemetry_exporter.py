import asyncio
from unittest.mock import patch

import pytest

import aimonitor.exporters.opentelemetry as otel_exporter_module
from aimonitor.core.event import SpanEvent
from aimonitor.core.exceptions import (
    ExporterConfigurationError,
    OptionalDependencyMissingError,
)
from aimonitor.exporters.opentelemetry import OpenTelemetryExporter


def test_opentelemetry_exporter_disabled_is_noop():
    exporter = OpenTelemetryExporter(enabled=False)

    asyncio.run(exporter.connect())

    assert exporter.enabled is False
    assert exporter.tracer is None
    assert asyncio.run(exporter.healthcheck()) is False


def test_opentelemetry_exporter_with_no_signals_is_noop():
    exporter = OpenTelemetryExporter(enabled=True)

    asyncio.run(exporter.connect())
    asyncio.run(exporter.export_batch([]))

    assert exporter._connected is True
    assert exporter.tracer is None
    assert asyncio.run(exporter.healthcheck()) is True


def test_opentelemetry_exporter_rejects_invalid_endpoint():
    exporter = OpenTelemetryExporter(
        enabled=True,
        endpoint="not-a-url",
        traces_enabled=True,
    )

    with pytest.raises(ExporterConfigurationError):
        asyncio.run(exporter.connect())


def test_opentelemetry_exporter_requires_otlp_http_dependency():
    exporter = OpenTelemetryExporter(enabled=True, traces_enabled=True)
    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("opentelemetry"):
            raise ImportError("missing OpenTelemetry")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(OptionalDependencyMissingError):
            asyncio.run(exporter.connect())


def test_pending_spans_are_bounded_and_oldest_are_discarded(monkeypatch):
    exporter = OpenTelemetryExporter(enabled=True, traces_enabled=True)
    state = exporter._trace_state("trace")
    monkeypatch.setattr(otel_exporter_module.time, "monotonic", lambda: 10.0)

    for index in range(otel_exporter_module._MAX_PENDING_SPANS + 1):
        exporter._queue_pending_span(
            state,
            SpanEvent(
                trace_id="trace",
                span_id=f"span-{index}",
                operation_name="operation",
            ),
        )

    assert exporter._pending_span_count == otel_exporter_module._MAX_PENDING_SPANS
    assert len(state.pending_spans) == otel_exporter_module._MAX_PENDING_SPANS
    assert state.pending_spans[0][0].span_id == "span-1"


def test_pending_spans_expire_after_five_minutes(monkeypatch):
    current_time = [10.0]
    monkeypatch.setattr(
        otel_exporter_module.time,
        "monotonic",
        lambda: current_time[0],
    )
    exporter = OpenTelemetryExporter(enabled=True, traces_enabled=True)
    state = exporter._trace_state("trace")
    exporter._queue_pending_span(
        state,
        SpanEvent(
            trace_id="trace",
            span_id="span-1",
            operation_name="operation",
        ),
    )

    current_time[0] += otel_exporter_module._PENDING_SPAN_TTL_SECONDS
    exporter._prune_expired_traces()

    assert exporter._pending_span_count == 0
    assert "trace" not in exporter._traces
