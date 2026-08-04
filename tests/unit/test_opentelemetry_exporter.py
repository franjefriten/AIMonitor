import types
from datetime import datetime, UTC
from unittest.mock import patch

from core.event import MCPEvent, Status
from exporters.opentelemetry import OpenTelemetryExporter


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

    def start_as_current_span(self, span_name):
        span = _DummySpan()
        self.started_spans.append((span_name, span))
        return _SpanContext(span)


def _build_fake_opentelemetry_module():
    tracer = _DummyTracer()
    trace_ns = types.SimpleNamespace(get_tracer=lambda service_name: tracer)
    module = types.SimpleNamespace(trace=trace_ns)
    return module, tracer


def _build_event() -> MCPEvent:
    return MCPEvent(
        tool_name="sample_tool",
        args={"tenant": "acme", "items": [1, 2, 3]},
        timestamp=datetime.now(UTC),
        delta=0.15,
        status=Status.SUCCESS,
        error="",
        metadata={"source": "unit"},
        result={"ok": True},
    )


def test_opentelemetry_exporter_disabled_is_noop():
    exporter = OpenTelemetryExporter(enabled=False)

    assert exporter.enabled is False
    assert exporter.tracer is None


def test_opentelemetry_exporter_enabled_without_dependency_disables_itself():
    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry":
            raise ImportError("missing opentelemetry")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        exporter = OpenTelemetryExporter(enabled=True)

    assert exporter.enabled is False
    assert exporter.tracer is None


@patch("os.getenv", return_value="false")
def test_opentelemetry_exporter_exports_event_to_span(_):
    fake_module, fake_tracer = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        exporter = OpenTelemetryExporter(enabled=True, service_name="test-service", span_prefix="mcp.tool")
        event = _build_event()

        import asyncio
        asyncio.run(exporter.export(event))

    assert exporter.enabled is True
    assert len(fake_tracer.started_spans) == 1

    span_name, span = fake_tracer.started_spans[0]
    assert span_name == "mcp.tool.sample_tool"
    assert span.attributes["mcp.tool_name"] == "sample_tool"
    assert span.attributes["mcp.status"] == "success"
    assert span.attributes["mcp.delta"] == 0.15


@patch("os.getenv", return_value="false")
def test_opentelemetry_exporter_exports_batch_to_multiple_spans(_):
    fake_module, fake_tracer = _build_fake_opentelemetry_module()

    with patch.dict("sys.modules", {"opentelemetry": fake_module}):
        exporter = OpenTelemetryExporter(enabled=True, span_prefix="mcp.tool")
        events = [_build_event(), _build_event()]

        import asyncio
        asyncio.run(exporter.export_batch(events))

    assert len(fake_tracer.started_spans) == 2
