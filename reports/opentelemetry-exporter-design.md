# OpenTelemetry Exporter Refactor and Guide

> Status: implementation design. This document does not claim that the refactor is complete.

## 1. Objective

OpenTelemetry should operate as an AIMonitor-managed exporter following the same configuration and lifecycle model as the other exporters:

```text
AIMonitor configuration
  -> private OpenTelemetry SDK providers
  -> processors/readers and OTLP exporters
  -> user-configured OTLP endpoint
  -> Collector or compatible backend
```

AIMonitor sends telemetry to the configured endpoint. It does not need a separate integration for every OTLP-compatible backend. A Collector is optional; forwarding to additional backends is outside AIMonitor.

The exporter must not assume that the application created a global provider or replace global providers through `trace.set_tracer_provider()`, `metrics.set_meter_provider()`, or `logs.set_logger_provider()`. It must create and close its own private providers.

### Responsibilities

- `OpenTelemetryExporter` adapts AIMonitor events to OpenTelemetry signals, configures private providers for enabled signals, and manages lifecycle.
- OpenTelemetry OTLP exporters encode and transport signals. AIMonitor does not implement the protobuf protocol.
- The destination may be a Collector or compatible OTLP backend.
- Private spans are not automatically connected to application or library traces. The AIMonitor contract guarantees correlation only for an MCP execution and its nested spans.

## 2. Agreed contract and scope

| AIMonitor signal | OpenTelemetry representation |
| --- | --- |
| `MCPEvent` | Root span for tool execution |
| `SpanEvent` | Child or nested span in the same trace |
| `MetricEvent` | OpenTelemetry metric according to `MetricType` |
| `LogEvent` | OpenTelemetry log record |
| Internal signals (`SignalType._INNER`) | Not exported |

### Decisions

- AIMonitor owns private SDK providers and OTLP transport when the exporter is enabled.
- The destination is configured through AIMonitor.
- Exporters have distinct contracts: Kafka publishes AIMonitor events to topics, Prometheus exposes numerical aggregates for scraping, and OpenTelemetry converts enabled signals to OTLP.
- A trace includes the root tool-execution span and nested `SpanEvent` spans.
- `MCPEvent` and `SpanEvent` share an AIMonitor correlation key. The SDK creates OTel IDs and the exporter stores mappings between internal and OTel span IDs.
- `args` and `result` are not exported by default because they may contain sensitive data.
- `MetricEvent` uses `Counter.add`, `Histogram.record`, and the synchronous `Gauge.set`.
- The synchronous Gauge is available from `opentelemetry-api`/`opentelemetry-sdk` 1.23.0 and became concrete in 1.24.0. The package minimum is 1.24.0 for Python below 3.14 and 1.35.0 for Python 3.14 or newer.
- `MetricEvent.name` is the instrument name; `labels`, `environment`, and `version` become attributes; `metadata` is omitted. An optional `unit` is added to the common model with an empty default.
- `LogEvent.message` is the body; `level` maps to standard OTel severity; `source`, `environment`, and `version` become attributes; `metadata` is omitted by default.
- Trace, metric, and log signal flags default to `false`. Enabling the exporter alone does not enable a signal. If enabled but no signal is active, AIMonitor should warn and remain a no-op.
- The initial version supports OTLP/HTTP protobuf only. There is no protocol selector or gRPC support. The default metric export interval is 60,000 ms.
- `healthcheck()` evaluates local provider readiness. It does not claim that a remote backend received or stored data.

### Open decisions

1. Define policy for high-cardinality labels and series.
2. Define instrument descriptions and validate names and units.
3. Bound pending `SpanEvent` values that arrive before a root `MCPEvent`, and define behavior for missing parents or incomplete traces.
4. Separate local readiness from remote export failures and expose SDK delivery failures in health snapshots.

## 3. Optional dependency compatibility

Python and dependency versions are separate compatibility dimensions. Passing the latest dependencies on multiple Python versions does not prove minimum-dependency compatibility.

`pyproject.toml` declares lower bounds:

- OpenTelemetry API/SDK/OTLP HTTP: 1.24.0 for Python below 3.14, 1.35.0 for Python 3.14 or newer.
- `prometheus-client`: 0.20.0.
- `confluent-kafka`: 2.13.0.
- `aiosqlite`: 0.21.0.

OTel 1.24 supports the used APIs but constrains Protobuf below 5. Protobuf 4 fails to import on Python 3.14. The minimum is therefore runtime-specific rather than universal.

CI should test:

- Exact supported minimum combinations.
- The latest compatible resolution.
- Python versions in which each combination is installable.

For OpenTelemetry, API, SDK, and HTTP exporter are a versioned family. Python 3.10 can test all three at 1.24.0. Python 3.14 tests latest and requires at least 1.35.0.

### Resolving with application dependencies

A private provider isolates OTel provider state, not Python package versions. AIMonitor and the application share one installation of `opentelemetry-api`, `opentelemetry-sdk`, and exporters in an environment.

Extras declare minimum requirements; they do not select or pin the final environment version. An application lockfile should control resolution. Installing AIMonitor into an existing environment may update a package to satisfy requirements.

Recommendations:

- Do not expose an OTel package-version selector in YAML.
- Keep compatible ranges in `pyproject.toml`; do not pin exact library versions in library metadata.
- Recommend a lockfile such as `uv.lock`.
- Use application constraints only when specific versions must be enforced.
- If constraints conflict with AIMonitor minimums, resolve the conflict explicitly rather than suppressing dependency checks.

## 4. Current repository state

The existing [`OpenTelemetryExporter`](../src/aimonitor/exporters/opentelemetry.py):

- Works only with `MCPEvent`.
- Gets a tracer through `trace.get_tracer()`, so it depends on the global provider.
- Does not create private `TracerProvider`, `MeterProvider`, or `LoggerProvider`.
- Does not configure processors, readers, or OTLP exporters.
- Does not have a configured OTel endpoint.
- Does not process `MetricEvent` or `LogEvent`.

The existing configuration includes `service_name` and `span_prefix`. `service_name` should become the `service.name` resource attribute; `span_prefix` should continue to control span names.

The `opentelemetry` extra currently lacks the OTLP exporter package.

## 5. Proposed AIMonitor configuration

```yaml
exporters:
  otel:
    enabled: true
    endpoint: "http://otel-collector:4318"
    service_name: "my-mcp-agent"
    span_prefix: "mcp.tool"
    signals:
      traces: false
      metrics: false
      logs: false
    metrics_export_interval_ms: 60000
```

The signal flags default to `false`. With `enabled: true` and no active signal, AIMonitor warns and does not export.

The endpoint is the OTLP base address, not a web UI URL. OTLP/HTTP builds:

```text
/v1/traces
/v1/metrics
/v1/logs
```

Authentication headers and secrets must not be stored unprotected in YAML. Add environment or secret-provider support where needed.

## 6. Refactor implementation

### Optional dependencies

For OTLP/HTTP protobuf:

```toml
[project.optional-dependencies]
opentelemetry = [
    "opentelemetry-api>=1.24.0; python_version < '3.14'",
    "opentelemetry-sdk>=1.24.0; python_version < '3.14'",
    "opentelemetry-exporter-otlp-proto-http>=1.24.0; python_version < '3.14'",
    "opentelemetry-api>=1.35.0; python_version >= '3.14'",
    "opentelemetry-sdk>=1.35.0; python_version >= '3.14'",
    "opentelemetry-exporter-otlp-proto-http>=1.35.0; python_version >= '3.14'",
]
```

Use the public `meter.create_gauge()` API rather than importing the private `_Gauge` implementation.

### Private trace provider

`connect()` must create private providers only for enabled signals:

```python
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

resource = Resource.create({SERVICE_NAME: self.service_name})
traces_endpoint = f"{self.endpoint.rstrip('/')}/v1/traces"

self._tracer_provider = TracerProvider(resource=resource)
self._tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint))
)
self.tracer = self._tracer_provider.get_tracer("aimonitor")
```

Do not register the private provider globally. Keep handles so `close()` can flush and shut down every provider. `connect()` should be idempotent and fail explicitly for missing dependencies or invalid configuration.

### Signal routing

Dispatch concrete event types rather than assuming every signal has `MCPEvent` fields:

```python
for event in event_batch:
    if isinstance(event, MCPEvent):
        self._export_tool_span(event)
    elif isinstance(event, SpanEvent):
        self._export_nested_span(event)
    elif isinstance(event, MetricEvent):
        self._record_metric(event)
    elif isinstance(event, LogEvent):
        self._record_log(event)
    elif event.event_type == SignalType._INNER:
        continue
```

Do not export `args` or `result` by default.

### Metrics provider

```python
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

metrics_endpoint = f"{self.endpoint.rstrip('/')}/v1/metrics"
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=metrics_endpoint),
    export_interval_millis=self.metrics_export_interval_ms,
)
self._meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader],
)
self.meter = self._meter_provider.get_meter("aimonitor")
```

The synchronous Gauge uses `set(amount, attributes=...)`. Cache instruments by name, type, and unit; do not cache Gauge values in AIMonitor. Repeated sets update the last value for the matching attribute set in the OTel SDK.

For counters and histograms:

```python
attributes = {
    **event.labels,
    **({"environment": event.environment} if event.environment else {}),
    **({"version": event.version} if event.version else {}),
}
instrument = self._instrument_for(event)

if event.metric_type == MetricType.COUNTER:
    instrument.add(event.value, attributes=attributes)
elif event.metric_type == MetricType.HISTOGRAM:
    instrument.record(event.value, attributes=attributes)
elif event.metric_type == MetricType.GAUGE:
    instrument.set(event.value, attributes=attributes)
```

### Logs provider

```python
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

logs_endpoint = f"{self.endpoint.rstrip('/')}/v1/logs"
self._logger_provider = LoggerProvider(resource=resource)
self._logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=logs_endpoint))
)
self.otel_logger = self._logger_provider.get_logger("aimonitor")
```

### IDs and parent-child correlation

The existing `Trace` IDs include operation names and cannot be passed directly as OTel IDs. Preserve them as internal correlation keys and let the OTel SDK generate valid OTel IDs.

The common event contract should add `trace_id` to `MCPEvent`; `SpanEvent` already has it.

- Top-level `SpanEvent` values (`parent_id is None`) attach to the root `MCPEvent` span.
- Deeper spans attach to the `SpanEvent` identified by `parent_id`.
- Do not use `metadata` as a replacement for typed correlation fields.

The exporter should allow events for a trace to be pending until the root arrives, then process the root before its children. Bound pending memory and reject or age out incomplete traces. `SpanEvent` values may arrive before the root because nested context managers dispatch on close.

### Closing the pipeline

Batch processors may retain pending SDK work. `close()` should flush and shut down every created provider. Run synchronous SDK operations outside the event loop.

```python
async def close(self) -> None:
    await asyncio.to_thread(self._tracer_provider.shutdown)
    if self._meter_provider:
        await asyncio.to_thread(self._meter_provider.shutdown)
    if self._logger_provider:
        await asyncio.to_thread(self._logger_provider.shutdown)
```

Make close idempotent and safe during partial initialization.

## 7. Suggested implementation stages

1. Add private trace and OTLP dependencies.
2. Create private providers and resource attributes.
3. Add root and nested span export with pending-event handling.
4. Add metrics with counters, histograms, and gauges.
5. Add logs and severity mapping.
6. Implement flush and shutdown.
7. Add healthchecks for local providers.
8. Add minimum/latest dependency CI coverage.
9. Add integration coverage using the OTel in-memory test exporters.

## 8. Official references

- OpenTelemetry Python SDK and API.
- OTLP/HTTP exporter.
- OpenTelemetry resource and attribute conventions.
- OTel metrics aggregation and periodic reader behavior.
