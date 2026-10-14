import types
import sys
import asyncio
from unittest.mock import patch

from aimonitor.core.event import HealthCheckSnapshot, HealthStatus
from aimonitor.telemetry.api import (
    configure_internal_telemetry,
    get_process_liveness,
    get_sdk_readiness,
    get_telemetry_status,
    telemetry_producer,
)


class _DummySpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class _SpanContext:
    def __init__(self, span):
        self._span = span

    def __enter__(self):
        return self._span

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyTracer:
    def __init__(self):
        self.started_spans = []

    def start_as_current_span(self, event_name):
        span = _DummySpan()
        self.started_spans.append((event_name, span))
        return _SpanContext(span)


class _DummyCounter:
    def __init__(self):
        self.calls = []

    def add(self, value, attributes):
        self.calls.append((value, attributes))


class _DummyMeter:
    def __init__(self):
        self.counters = {}

    def create_counter(self, metric_name):
        if metric_name not in self.counters:
            self.counters[metric_name] = _DummyCounter()
        return self.counters[metric_name]


def _build_fake_opentelemetry_module():
    tracer = _DummyTracer()
    meter = _DummyMeter()

    trace_ns = types.SimpleNamespace(get_tracer=lambda service_name: tracer)
    metrics_ns = types.SimpleNamespace(get_meter=lambda service_name: meter)
    module = types.SimpleNamespace(trace=trace_ns, metrics=metrics_ns)
    return module, tracer, meter


def test_configure_internal_telemetry_disabled_forces_noop():
    manager = configure_internal_telemetry(enabled=False, service_name="test-service")

    assert manager is telemetry_producer
    assert manager.enabled is False
    assert manager.tracer is None
    assert manager.meter is None


def test_configure_internal_telemetry_enabled_without_opentelemetry_is_noop():
    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry":
            raise ImportError("missing opentelemetry")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")

    assert manager.enabled is False
    assert manager.tracer is None
    assert manager.meter is None


def test_record_event_is_noop_when_disabled():
    manager = configure_internal_telemetry(enabled=False)
    manager.record_event("event.test", {"k": "v"})

    assert manager.tracer is None


def test_record_metric_is_noop_when_disabled():
    manager = configure_internal_telemetry(enabled=False)
    manager.record_metric("metric.test", value=10, attributes={"env": "test"})

    assert manager.meter is None


def test_configure_internal_telemetry_enabled_records_events_and_metrics():
    fake_module, fake_tracer, fake_meter = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        manager.record_event("event.sample", {"tenant": "acme", "count": 2})
        manager.record_metric("metric.sample", value=3, attributes={"env": "test"})

    assert manager.enabled is True
    assert len(fake_tracer.started_spans) == 1
    event_name, span = fake_tracer.started_spans[0]
    assert event_name == "event.sample"
    assert span.attributes["tenant"] == "acme"
    assert span.attributes["count"] == 2

    counter = fake_meter.counters["metric.sample"]
    assert counter.calls == [(3, {"env": "test"})]


def test_configure_internal_telemetry_reuses_meter_counters():
    fake_module, _, fake_meter = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        manager.record_metric("metric.sample", value=1)
        manager.record_metric("metric.sample", value=2)

    counter = fake_meter.counters["metric.sample"]
    assert counter.calls == [(1, {}), (2, {})]


def test_record_exporter_healthcheck_reports_exporter_state_to_internal_telemetry():
    fake_module, fake_tracer, _ = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        asyncio.run(
            manager.record_exporter_healthcheck(
                HealthCheckSnapshot(
                    exporter_name="KafkaExporter",
                    status=HealthStatus.HEALTHY,
                    message="Broker reachable",
                ),
                {"topic": "aimonitor-healthcheck"},
            )
        )

    assert manager.enabled is True
    assert len(fake_tracer.started_spans) == 1
    event_name, span = fake_tracer.started_spans[0]
    assert event_name == "sdk.exporter.healthcheck"
    assert span.attributes["exporter_name"] == "KafkaExporter"
    assert span.attributes["status"] == HealthStatus.HEALTHY.value
    assert span.attributes["message"] == "Broker reachable"
    assert span.attributes["topic"] == "aimonitor-healthcheck"


def test_telemetry_consumer_reports_local_provider_state():
    fake_module, _, _ = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        telemetry_status = get_telemetry_status()

    assert telemetry_status == {
        "enabled": True,
        "service_name": "test-service",
        "tracer_available": True,
        "meter_available": True,
    }


def test_process_liveness_is_independent_from_telemetry_provider():
    import asyncio

    configure_internal_telemetry(enabled=False)
    liveness = asyncio.run(get_process_liveness())

    assert liveness["status"] == "alive"
    assert liveness["component"] == "aimonitor-sdk"
    assert liveness["pid"] > 0
    assert liveness["uptime_seconds"] >= 0
