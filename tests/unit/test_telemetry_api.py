import types
import sys
from unittest.mock import patch

from telemetry.api import configure_internal_telemetry, internal_telemetry_manager


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

    assert manager is internal_telemetry_manager
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


def test_track_event_is_noop_when_disabled():
    manager = configure_internal_telemetry(enabled=False)
    manager.track_event("event.test", {"k": "v"})

    assert manager.tracer is None


def test_track_metric_counter_is_noop_when_disabled():
    manager = configure_internal_telemetry(enabled=False)
    manager.track_metric_counter("metric.test", value=10, attributes={"env": "test"})

    assert manager.meter is None


def test_configure_internal_telemetry_enabled_records_events_and_metrics():
    fake_module, fake_tracer, fake_meter = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        manager.track_event("event.sample", {"tenant": "acme", "count": 2})
        manager.track_metric_counter("metric.sample", value=3, attributes={"env": "test"})

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
        manager.track_metric_counter("metric.sample", value=1)
        manager.track_metric_counter("metric.sample", value=2)

    counter = fake_meter.counters["metric.sample"]
    assert counter.calls == [(1, {}), (2, {})]


def test_track_healthcheck_reports_exporter_state_to_internal_telemetry():
    fake_module, fake_tracer, _ = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        manager = configure_internal_telemetry(enabled=True, service_name="test-service")
        manager.track_healthcheck("KafkaExporter", True, "Broker reachable", {"topic": "aimonitor-healthcheck"})

    assert manager.enabled is True
    assert len(fake_tracer.started_spans) == 1
    event_name, span = fake_tracer.started_spans[0]
    assert event_name == "sdk.exporter.healthcheck"
    assert span.attributes["exporter_name"] == "KafkaExporter"
    assert span.attributes["healthy"] is True
    assert span.attributes["message"] == "Broker reachable"
    assert span.attributes["topic"] == "aimonitor-healthcheck"
