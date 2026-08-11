# AIMonitor Architecture

## High-level design

AIMonitor is built as a modular monitoring framework for MCP workflows, with a clear separation between:

- internal SDK telemetry
- user-facing event export

The repository is organized into:

- `core/`: event model, registry and decorators for tool monitoring
- `exporters/`: output adapters for file, SQLite, Prometheus, and OpenTelemetry
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

Exposes metrics as Prometheus counters and histograms.

### `OpenTelemetryExporter`

Converts `MCPEvent` objects into OpenTelemetry spans without coupling them to internal SDK telemetry.

## Internal telemetry vs event export

AIMonitor separates two observability flows:

1. Internal SDK telemetry
   - lives in `telemetry/api.py`
   - tracks library health and internal behavior
   - can be enabled by `AIMONITOR_INNER_TELEMETRY`

2. MCP event export
   - uses the exporter registry
   - sends actual tool usage events and metrics
   - can be exported to OpenTelemetry or other supported backends

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

To add a new exporter:

1. inherit from `exporters.base.BaseExporter`
2. implement `export` and optionally `export_batch`
3. register the exporter in `core.registry`
4. add tests under `tests/unit`
