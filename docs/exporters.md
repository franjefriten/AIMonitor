# AIMonitor Exporters

An exporter converts AIMonitor signals into an external representation or destination.
All exporters receive batches through `ExporterRegistry`, but exporters differ in:

- the signal types they accept;
- whether they connect to a resource;
- whether they expose a destination or only write locally;
- how failures are reported;
- whether they participate in readiness and recovery.

Use the registry as the normal integration point:

```python
from aimonitor.core.event import MCPEvent
from aimonitor.core.registry import registry

await registry.dispatch(
    MCPEvent(tool_name="fetch_customer", status="success")
)
```

The registry starts export workers and distributes each queued signal to every registered exporter.
Each exporter decides whether to handle that signal.

## Exporter contracts

### Minimal protocol exporter

The smallest supported interface is `ProtocolExporter`:

```python
from collections.abc import Sequence
from typing import Protocol

from aimonitor.core.event import BaseSignal


class ProtocolExporter(Protocol):
    async def export(
        self,
        event_batch: Sequence[BaseSignal],
    ) -> None:
        ...
```

A custom class needs only `export()`. It is registered normally, but it does not participate in registry health snapshots because the registry cannot query a healthcheck or recovery implementation for it.

### Health-managed exporter

An exporter that owns a connection, server, or local resource should inherit from `BaseExporter`:

```python
from collections.abc import Sequence

from aimonitor.exporters.base import BaseExporter
from aimonitor.core.event import BaseSignal


class MyExporter(BaseExporter):
    async def export(self, event_batch: Sequence[BaseSignal]) -> None:
        # Send or persist the batch.
        ...

    async def connect(self) -> None:
        # Initialize resources.
        ...

    async def close(self) -> None:
        # Flush and release resources.
        ...

    async def healthcheck(self) -> bool:
        # Return True only after the exporter can perform its job.
        return True

    async def describe(self) -> dict[str, object]:
        # Return diagnostic information only.
        return {"destination": "my-backend"}

    async def recover(self) -> bool:
        # Reconnect or rebuild resources.
        return True
```

`BaseExporter` defines lifecycle and health methods, but implementations must provide their concrete behavior:

| Method | Responsibility |
| --- | --- |
| `connect()` | Initialize a client, database, server, provider, or file handle. |
| `export(event_batch)` | Deliver or persist one batch. Unsupported signals should be skipped. |
| `healthcheck()` | Return `True` for a currently usable exporter or `False` for a known unavailable exporter. Raise an exception when the check itself cannot be completed. |
| `describe()` | Return diagnostic details. It must not decide registry health. |
| `recover()` | Reconnect or reconstruct resources and return whether recovery was initiated successfully. |
| `close()` | Flush and release resources; cleanup should be idempotent. |

### Registry behavior

When a `BaseExporter` is registered, the registry first records `starting`.
The background health worker then maps results to exporter health states:

| Result | State |
| --- | --- |
| `healthcheck()` returns `True` | `healthy` |
| `healthcheck()` returns `False` | `down` |
| `healthcheck()` raises or times out | `failure` |
| `recover()` is running | `recovering` |
| `close()` completes | `stopped` |

Recovery is only complete after a successful follow-up healthcheck.
The registry does not consider `recover()` alone sufficient to mark the exporter healthy.

An export failure is observable to the caller and registry worker.
It must not be converted into a successful batch merely because an underlying client buffered bytes or queued a request.

The health snapshot is the source of readiness.
It does not call `describe()` or perform a fresh exporter probe for every readiness request.

## Signal types

AIMonitor defines these public signal families:

| Signal | Model | Typical content |
| --- | --- | --- |
| Event | `MCPEvent` | Tool name, arguments, result, execution duration, status, error, and trace ID |
| Span | `SpanEvent` | Parent span, trace ID, operation name, status, error, and duration |
| Metric | `MetricEvent` | Name, numeric value, metric type, labels, environment, version, and unit |
| Log | `LogEvent` | Message, level, source, environment, version, and metadata |
| Internal | `InnerEvent` | SDK health and internal observability signals |

Arguments and results are application data.
Only exporters that explicitly document payload preservation should be assumed to store them.
Sensitive-field redaction is performed according to AIMonitor configuration before export; exporters must still avoid logging complete credentials or payloads.

## Exporter matrix

| Exporter | Supported signals | Resources | Delivery model | Health and recovery | Optional dependency |
| --- | --- | --- | --- | --- | --- |
| `ConsoleExporter` | Event, Log, Metric, Span, Internal | Text stream | Synchronous print | Always healthy; always recoverable | None |
| `FileExporter` | Event, Log, Metric, Span | Local JSONL file | Append and flush; size/date rotation | Filesystem write check; reopen on recovery | `aiofiles` |
| `SQLiteExporter` | Event, Log, Metric, Span | Local SQLite database | Async SQL inserts | `SELECT 1` check; reconnect on recovery | `aiosqlite` |
| `WebhookExporter` | Event, Log, Metric, Span | Remote HTTP endpoint | HTTP POST batch; HTTP errors raised | GET probe to the configured URL; recreate client on recovery | `httpx` |
| `PrometheusExporter` | Metric only | Local HTTP metrics server | Pull-based scrape | HTTP `/metrics` probe; restart server on recovery | `prometheus-client` |
| `KafkaExporter` | Event, Metric, Span, Log | Kafka broker | JSON messages with broker acknowledgment | Broker metadata probe; rebuild producer on recovery | `confluent-kafka[aio]` |
| `OpenTelemetryExporter` | Event, Span, Metric, Log, independently enabled | Private OTel SDK providers and OTLP/HTTP endpoints | Batch traces, metrics, and logs | Verify local providers; close and reconnect on recovery | OpenTelemetry API, SDK, and OTLP/HTTP exporter |

Redis, MongoDB, and PostgreSQL settings are present in configuration, but their exporters are not implemented in this repository snapshot.
Do not enable those settings expecting runtime exporter registration.

## ConsoleExporter

`ConsoleExporter` is intended for development and local debugging.
It prints a UTC trace header and each `model_dump()` representation to a text stream.

```python
from aimonitor.exporters.console import ConsoleExporter
from aimonitor.core.registry import registry

registry.register(ConsoleExporter())
```

To write to a custom stream:

```python
import sys

registry.register(ConsoleExporter(stream=sys.stderr))
```

### Contract

- Supports event, log, metric, span, and internal signals.
- Writes synchronously through the supplied stream.
- Flushes after writing if the stream provides `flush()`.
- Does not create durable storage.
- Does not batch serialization; it prints the complete Pydantic model representation.
- Health checks write a trace line and always return `True`.
- Recovery always returns `True`.

The exporter is useful for validating decorators and dispatch order, but it is not suitable as an audit log or production persistence mechanism.

## FileExporter

`FileExporter` writes JSON Lines to a dated file and rotates by date or byte size.

```python
from pathlib import Path

from aimonitor.exporters.file import FileExporter
from aimonitor.core.registry import registry

exporter = FileExporter(
    base_uri=Path("./logs"),
    mode="a",
    max_bytes=10 * 1024 * 1024,
)
await exporter.connect()
registry.register(exporter)
```

### Bootstrap configuration

```yaml
exporters:
  file:
    enabled: true
    path: "./logs"
    max_mb_per_file: 10.0
```

The bootstrap currently creates `FileExporter(settings.exporters.file.path)` and therefore uses the exporter constructor's `max_bytes` default.
`max_mb_per_file` is a settings field, but it is not yet passed into `FileExporter` by bootstrap.

### Contract

- Supports event, log, metric, and span signals.
- Skips unsupported signals.
- Creates the base directory in the constructor.
- Opens a JSONL file using `aiofiles`.
- Each line starts with a UTC timestamp and contains `event.model_dump_json()`.
- Rotates to a new numbered file when the projected batch would reach or exceed `max_bytes`.
- Reopens a new dated file after the UTC date changes.
- Uses the configured mode for file opening; normal operation should use append mode.
- Must be connected before export.
- The retry decorator applies to export operations.

`export()` logs an initialization error if `connect()` was not called, but should be treated as a lifecycle misuse rather than a normal runtime state.

### Health and recovery

Health writes and removes `healthcheck_test_file.txt` in the base directory.
It returns `False` if creation or removal fails.

Recovery opens the configured file in append mode if no client is active.
If the client exists but is closed, recovery may need a more complete close/reconnect policy.

Example output shape:

```text
2026-11-23 22:30:00.123456+00:00: {"id":"...","event_type":"event","tool_name":"fetch"}
```

## SQLiteExporter

`SQLiteExporter` stores supported signals in separate tables.

```python
from aimonitor.exporters.sqlite import SQLiteExporter
from aimonitor.core.registry import registry

exporter = SQLiteExporter(
    dsn="./aimonitor.sqlite",
    table_name="aimonitor",
)
await exporter.connect()
registry.register(exporter)
```

Install the dependency:

```bash
pip install -e ".[sqlite]"
```

Bootstrap configuration:

```yaml
exporters:
  sqlite:
    enabled: true
    uri: "./aimonitor.sqlite"
```

### Contract

- Supports event, log, metric, and span signals.
- Creates one table per supported signal model, for example `aimonitor_event`, `aimonitor_log`, `aimonitor_metric`, and `aimonitor_span`.
- Enables SQLite WAL journal mode.
- Uses `INSERT OR REPLACE` for one primary-keyed batch per table.
- Commits after each export batch.
- Converts Python `datetime`, `Enum`, dictionaries, and lists into storage-compatible values.
- Requires `connect()` before export.

The field list and primary-key shape follow each Pydantic signal model.
Changing the signal model after rows already exist requires an explicit migration strategy.

### Health and recovery

Health executes `SELECT 1`.
It returns `False` if the query fails.

Recovery attempts to open a new connection when no client exists.
If a connection is present but broken, close and reconnect explicitly before retrying export:

```python
await exporter.close()
await exporter.connect()
```

Close the exporter during application shutdown so the aiosqlite connection is released.

## WebhookExporter

`WebhookExporter` sends JSON arrays of Pydantic signal models to an HTTP endpoint.

```python
from aimonitor.exporters.http import WebhookExporter
from aimonitor.core.registry import registry

exporter = WebhookExporter(
    url="https://example.com/aimonitor",
    headers={
        "Authorization": "Bearer <token>",
        "Content-Type": "application/json",
    },
)
await exporter.connect()
registry.register(exporter)
```

### Contract

- Supports event, log, metric, and span signals.
- Skips unsupported signals.
- Converts each supported event with `model_dump()`.
- Sends one HTTP POST containing the complete JSON array.
- Raises for a non-success HTTP status.
- Requires `connect()` before export.
- Uses a 10-second export timeout and the shared retry policy for connection or timeout errors.

The HTTP base client has a one-second default timeout, while the export call passes an explicit ten-second timeout.
`describe()` reports only the exporter's status and message; it does not include the URL, headers, or authentication configuration, which may contain secrets.

### Health and recovery

Health sends `GET` to the configured URL with a ten-second timeout and calls `raise_for_status()`.
This assumes the endpoint accepts or handles `GET` safely.

Recovery creates a new generic `httpx.AsyncClient()` if no client exists.
It does not preserve the original URL, base URL, headers, or authentication configuration in its recovery implementation.
Therefore, configure recovery carefully or add application-level reconnection logic before treating the endpoint as production-ready.

Do not put secrets directly in YAML unless the project has secret loading and redaction controls.

## PrometheusExporter

`PrometheusExporter` exposes numeric `MetricEvent` values through an HTTP scrape endpoint.
It does not export raw tool events, logs, spans, arguments, results, or trace identifiers.

```python
from aimonitor.exporters.prometheus import PrometheusExporter
from aimonitor.core.registry import registry

exporter = PrometheusExporter(address="http://0.0.0.0:9000")
await exporter.connect()
registry.register(exporter)
```

Prometheus reads:

```text
http://127.0.0.1:9000/metrics
```

Bootstrap configuration:

```yaml
exporters:
  prometheus:
    enabled: true
    url: "http://0.0.0.0:9000"
    bearer_token: "$secrets.PROMETHEUS_SCRAPE_TOKEN"
```

When `bearer_token` is configured, `/metrics` requires an `Authorization: Bearer <token>` header and returns `401 Unauthorized` otherwise. The token can be supplied through the YAML secret reference or `AIMONITOR_PROMETHEUS_BEARER_TOKEN`. Without a token, the endpoint remains unauthenticated for backwards compatibility.

Configure Prometheus to send the same token when scraping:

```yaml
scrape_configs:
  - job_name: "aimonitor"
    static_configs:
      - targets: ["aimonitor:9000"]
    authorization:
      type: Bearer
      credentials_file: /run/secrets/prometheus-scrape-token
```

The exporter serves HTTP, so bearer credentials are not encrypted in transit. Keep the endpoint on a trusted private network or put it behind a TLS-terminating reverse proxy when traffic crosses an untrusted network.

Install the dependency:

```bash
pip install -e ".[prometheus]"
```

### Metric contract

Only `MetricEvent` signals are accepted.

| `metric_type` | Prometheus operation |
| --- | --- |
| `COUNTER` | Increment by the event value |
| `GAUGE` | Set the current value |
| `HISTOGRAM` | Observe the event value |

Metric names are stable per exporter instance.
The implementation rejects:

- negative counter increments;
- changing a name from one metric type to another;
- changing a metric name's label set after registration.

Labels come directly from `MetricEvent.labels`.
Environment and version fields are not automatically added as labels.
The exporter uses a private `CollectorRegistry`, so it does not mix metrics with application-owned Prometheus registries.

### Health and recovery

Health verifies that:

- the HTTP server is started;
- the server thread is alive;
- `/metrics` returns HTTP 200.

Recovery:

1. Runs a healthcheck.
2. Closes the old server if it was partially started.
3. Starts a fresh server.

Close the exporter to shut down the metrics server and join its thread.

## KafkaExporter

`KafkaExporter` publishes JSON-encoded AIMonitor signals to explicitly configured Kafka topics.

### Bootstrap configuration

```yaml
exporters:
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "SASL_SSL"
    sasl:
      mechanism: "PLAIN"
      username: "$secrets.KAFKA_USERNAME"
      password: "$secrets.KAFKA_PASSWORD"
    topics:
      event: "aimonitor.events"
      metric: "aimonitor.metrics"
      span: "aimonitor.spans"
      log: "aimonitor.logs"
    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
```

Install the dependency:

```bash
pip install -e ".[kafka]"
```

Initialize through the bootstrap:

```python
await initialize_monitor("config.yaml")
```

### Contract

- Supports event, metric, span, and log signals.
- Does not publish internal health signals.
- Requires a topic mapping for every signal type that should be delivered.
- Logs and skips a signal when no topic is configured.
- Serializes the Pydantic model with `model_dump_json()`.
- Encodes the value as UTF-8 bytes.
- Uses a stable 16-character SHA-256-derived partition key from the signal type.
- Calls `AIOProducer.produce()` and awaits delivery futures.
- Raises `ExporterDeliveryError` with the original Kafka exception as its cause if a delivery future fails.
- Raises `ExporterNotReadyError` after the producer is closed or never initialized.

Successful producer acknowledgment is not evidence that a downstream consumer processed the record.

The bootstrap builds producer configuration with acknowledgement, idempotence, retries, in-flight limit, linger, compression, delivery timeout, request timeout, socket timeout, reconnect backoff, and SASL values.
Credentials are stored as `SecretStr` values in settings where supported and should not be included in diagnostic logs.
The YAML secret references are resolved from the process environment; see [configuration](configuration.md#secret-references-in-yaml).

### Health and recovery

The health probe uses Kafka metadata instead of publishing an application or healthcheck event.
It is healthy only when metadata reports at least one broker.

Recovery:

1. Closes and flushes the existing producer.
2. Creates a new `AIOProducer` with the original configuration.
3. Recreates the Kafka metadata health probe.

Close the exporter during shutdown.
The Kafka exporter also makes close operations idempotent: closing an already closed or missing producer is a no-op.

## OpenTelemetryExporter

`OpenTelemetryExporter` uses private OpenTelemetry providers and OTLP/HTTP exporters.
It does not replace application-global trace, meter, or logger providers.

```python
from aimonitor.exporters.opentelemetry import OpenTelemetryExporter
from aimonitor.core.registry import registry

exporter = OpenTelemetryExporter(
    enabled=True,
    service_name="checkout-agent",
    span_prefix="mcp.tool",
    endpoint="http://localhost:4318",
    headers={"Authorization": "Bearer <token>"},
    traces_enabled=True,
    metrics_enabled=True,
    logs_enabled=True,
    metrics_export_interval_ms=60_000,
)
await exporter.connect()
registry.register(exporter)
```

Bootstrap configuration:

```yaml
exporters:
  otel:
    enabled: true
    service_name: "checkout-agent"
    span_prefix: "mcp.tool"
    endpoint: "http://localhost:4318"
    headers:
      Authorization: "Bearer $secrets.OTEL_EXPORTER_TOKEN"
    signals:
      traces: true
      metrics: true
      logs: false
    metrics_export_interval_ms: 60000
```

`headers` is passed to the OTLP/HTTP trace, metric, and log exporters. Use it for Bearer tokens or backend-specific API-key headers. Header values are stored as `SecretStr` in settings; YAML secret references are resolved from the process environment. Avoid sending credentials over plain HTTP outside a trusted local network; use HTTPS for remote collectors.
Alternatively, set `AIMONITOR_OTEL_HEADERS` to a JSON object in the process environment.

Install the optional dependency:

```bash
pip install -e ".[opentelemetry]"
```

### Signal contract

| AIMonitor signal | OpenTelemetry signal |
| --- | --- |
| `MCPEvent` | Root span |
| `SpanEvent` | Nested child span |
| `MetricEvent` | Counter, histogram, or synchronous gauge |
| `LogEvent` | Log record |
| Internal signal | Skipped |

Trace, metric, and log toggles are independent.
Enabling the exporter without enabling a signal produces a warning and a no-op.

OTLP paths are derived from the base endpoint:

```text
/v1/traces
/v1/metrics
/v1/logs
```

The exporter validates HTTP or HTTPS endpoints and rejects URLs with query strings or fragments.

### Trace contract

- `MCPEvent` becomes a span named `{span_prefix}.{tool_name}`.
- Its start and end timestamps derive from `timestamp` and `delta`.
- Tool status, duration, error, and tool name are mapped to span attributes.
- `args` and `result` are not exported by default.
- `SpanEvent` values with `parent_id=None` attach to the matching root trace span.
- Deeper spans attach to the parent span context recorded under `parent_id`.
- Events that arrive before their parent are retained temporarily and flushed when the parent appears.
- Expired pending traces are removed so unfinished traces do not remain in memory forever.

### Metric contract

- Metric name is `MetricEvent.name`.
- Labels from `MetricEvent.labels` become attributes.
- Counters use `add()`.
- Histograms use `record()`.
- Gauges use `set()` and rely on OTel last-value aggregation.
- Instruments are cached by name, metric type, and unit.
- Gauge values are not cached separately by AIMonitor.
- Metrics export periodically according to `metrics_export_interval_ms`.

### Log contract

The log body is `LogEvent.message`.
Level, source, environment, and version are mapped into standard log fields or attributes according to the implementation.
Metadata and payload objects are omitted unless explicitly designed into attributes.

### Health and recovery

Health is local readiness only.
It does not prove that a Collector or remote backend received data.

It verifies that each enabled provider exists:

- trace provider for traces;
- meter provider for metrics;
- logger provider for logs.

Recovery closes all providers and reconnects them.
Close flushes and shuts down providers, cancels pending-trace cleanup, and clears pending trace state.

Install OTel dependencies compatible with the active Python version.
For Python 3.14 or newer, use SDK 1.35.0 or newer.

## Custom exporters

A custom exporter should:

1. Declare `SUPPORTED_SIGNALS`.
2. Override `export()` and validate batch types.
3. Implement `connect()` for resources that require initialization.
4. Return `True` or `False` consistently from `healthcheck()`.
5. Keep `describe()` diagnostic-only.
6. Implement bounded `recover()`.
7. Make `close()` idempotent.
8. Preserve exceptions and chained causes for delivery failures.
9. Never include credentials or complete payloads in log messages.

Example:

```python
from collections.abc import Sequence

from aimonitor.core.event import BaseSignal, SignalType
from aimonitor.exporters.base import BaseExporter


class AuditExporter(BaseExporter):
    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG}

    def __init__(self):
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def export(self, event_batch: Sequence[BaseSignal]) -> None:
        if not self.connected:
            raise RuntimeError("AuditExporter is not connected")

        for event in event_batch:
            if event.event_type in self.SUPPORTED_SIGNALS:
                await self.write_audit_record(event)

    async def write_audit_record(self, event: BaseSignal) -> None:
        ...

    async def healthcheck(self) -> bool:
        return self.connected

    async def describe(self) -> dict[str, object]:
        return {
            "connected": self.connected,
            "supported_signals": sorted(
                signal.value for signal in self.SUPPORTED_SIGNALS
            ),
        }

    async def recover(self) -> bool:
        await self.close()
        await self.connect()
        return self.connected

    async def close(self) -> None:
        self.connected = False
```

Register it explicitly:

```python
from aimonitor.core.registry import registry

exporter = AuditExporter()
await exporter.connect()
registry.register(exporter)
```
