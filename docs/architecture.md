# AIMonitor Architecture

## High-level design

AIMonitor is built as a modular monitoring framework for MCP workflows, with a clear separation between:

- internal SDK telemetry
- user-facing event export

The repository is organized into:

- `core/`: event model, registry and decorators for tool monitoring
- `exporters/`: output adapters for console, file, SQLite, Webhook/HTTP, Prometheus, OpenTelemetry, and Kafka
- `telemetry/`: internal SDK telemetry manager and OpenTelemetry integration
- `configs/`: settings model and environment handling
- `tests/`: unit and integration tests

## Core components

### `core.registry`

The `ExporterRegistry` collects exporters and manages background workers that process event batches.
It supports multiple exporter implementations and handles exporter failure without breaking the main workflow.

### `core.decorators`

The `monitor_tool` decorator wraps tool execution and produces `MCPEvent` payloads. It also:

- records execution time
- redact sensitive fields
- sets tool status
- sends events to the registry

### `core.event`

`MCPEvent` is the shared event model with fields such as:

- `tool_name`
- `args`
- `timestamp`
- `delta`
- `status`
- `error`
- `metadata`
- `result`

## Exporters

Exporters are responsible for persisting or forwarding captured events.

### `FileExporter`

Writes JSONL lines to disk and performs rotation if needed.

### `SQLiteExporter`

Persists events in SQLite tables, useful for local debugging and simple storage.

### `PrometheusExporter`

Exposes `MetricEvent` signals as Prometheus counters, gauges, or histograms. It does not export raw `MCPEvent`, log, or span payloads; if one of those signals needs to produce a Prometheus observation, instrumentation should emit a corresponding `MetricEvent`.

Each metric name has one stable metric type and label-name set for the lifetime of the exporter. Counter events increment by their value and reject negative increments; gauge events set the current value; histogram events observe the value.

See [built-in exporters](./exporters.md) for the purpose, supported signals, and delivery model of each native exporter.

### `OpenTelemetryExporter`

Converts `MCPEvent` objects into OpenTelemetry spans without coupling them to internal SDK telemetry.
Each span's start and end times are derived from the event timestamp and execution duration.

## Internal telemetry vs event export

AIMonitor separates two observability flows:

1. Internal SDK telemetry
   - lives in `telemetry/api.py`
   - `TelemetryProducer` records internal events, exporter healthchecks, and metrics
   - `TelemetryConsumer` reads local telemetry availability and registry-owned SDK readiness
   - can be enabled by `AIMONITOR_INNER_TELEMETRY`

2. MCP event export
   - uses the exporter registry
   - sends actual tool usage events and metrics
   - can be exported to OpenTelemetry or other supported backends

The OpenTelemetry integration is write-oriented. AIMonitor does not expose a generic query API for traces or metrics stored in an external backend; backend queries must use that backend's own client or HTTP API.

## Configuration

Settings are managed by `AIMonitorSettings` in `configs/config.py` and can be loaded from:

- environment variables
- `.env` files
- YAML or JSON configuration files

The settings class also validates URLs and optional feature flags.

## Testing

The repository includes unit and integration tests under `tests/`.
The CI workflow runs unit tests on every pull request to `main`.

## How to extend

To add an exporter, implement `export()` and register it in
`core.registry`. `exporters.base.ProtocolExporter` is the minimal contract.
Inherit from `BaseExporter` when health checks and recovery management are
needed; only those exporters appear in readiness snapshots.
