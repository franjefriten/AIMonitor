# AIMonitor Usage Guide

## Overview

AIMonitor is an async-first observability toolkit for MCP workflows. It tracks tool execution, captures events, and exports them through file, SQLite, Prometheus, Redis, Kafka, and OpenTelemetry exporters.

## Installation

Install the package from PyPI or GitHub:

```bash
pip install aimonitor-sdk
```

Optional integrations:

```bash
pip install "aimonitor-sdk[opentelemetry,sqlite,prometheus,kafka]"
```

## Async bootstrap

The runtime entry point is now the async bootstrap:

```python
from bootstrap import initialize_monitor

async def main():
    settings = await initialize_monitor("config.yaml")
    print(settings.kafka_enabled, settings.prometheus_enabled)
```

This loads YAML/JSON config and registers only enabled exporters.

## Configuration

AIMonitor supports environment variables, `.env` files, and runtime YAML/JSON files.

### Environment variables

```bash
AIMONITOR_ENV=ENV
AIMONITOR_TRACK_METRICS=true
AIMONITOR_TRACK_EVENTS=true
AIMONITOR_TRACK_LOGS=true
AIMONITOR_INNER_TELEMETRY=false
AIMONITOR_HEALTHCHECK_ENABLED=true
AIMONITOR_HEALTHCHECK_INTERVAL=60
AIMONITOR_PROMETHEUS_URL=http://localhost:9000
AIMONITOR_SQLITE_URI=./aimonitor.sqlite
AIMONITOR_FILE_EXPORTER_LOGS=./logs
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service
AIMONITOR_OTEL_MCP_SPAN_PREFIX=mcp.tool
```

## Basic usage

### Instrumenting a tool

```python
from core.decorators import monitor_tool

@monitor_tool
async def fetch_data(user_id: str, limit: int = 10):
    return {"user_id": user_id, "records": []}

result = await fetch_data("user123", limit=20)
```

The decorator automatically records:

- tool name
- arguments
- execution time
- status
- returned payload or error

### Registering exporters

```python
from exporters.file import FileExporter
from core.registry import registry

exporter = FileExporter(base_uri="./logs")
await exporter.connect()
registry.register(exporter)
```

## Available exporters

### FileExporter

```python
from exporters.file import FileExporter

exporter = FileExporter(base_uri="./monitoring_logs")
await exporter.connect()
registry.register(exporter)
```

### SQLiteExporter

```python
from exporters.sqlite import SQLiteExporter

exporter = SQLiteExporter(dsn="./aimonitor.sqlite")
await exporter.connect()
registry.register(exporter)
```

### PrometheusExporter

```python
from exporters.prometheus import PrometheusExporter

exporter = PrometheusExporter(address="http://0.0.0.0:9000")
await exporter.connect()
registry.register(exporter)
```

### KafkaExporter

```python
from exporters.kafka import KafkaExporter

exporter = KafkaExporter(
    kafka_configs={
        "bootstrap.servers": "localhost:9092",
        "acks": "all",
    },
    max_workers=12,
    batch_size=2048,
    buffer_timeout=1.0,
)
await exporter.connect()
registry.register(exporter)
```

The preferred configuration path is via `AIMonitorSettings` and `initialize_monitor` so the values are loaded from the model instead of being hand-built at runtime.

## YAML example

```yaml
app:
  env: ENV

tracking:
  enabled: true
  track_metrics: true
  track_events: true
  track_logs: true

telemetry:
  inner_telemetry: false
  healthcheck_enabled: true
  healthcheck_interval: 60

exporters:
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12

  prometheus:
    enabled: true
    url: "http://localhost:9000"

  file:
    enabled: true
    path: "./logs"
```

Load it like this:

```python
from configs.config import get_settings

settings = get_settings()
await settings.load_from_yaml("config.yaml")
```

## Sensitive data protection

Sensitive values are automatically redacted:

- password
- token
- api_key
- secret
- apikey
- access_token
- client_secret
- private_key
- credentials

Custom additions:

```bash
AIMONITOR_SENSITIVE_KEYS=password,token,my_custom_field
```

## Error handling

```python
@monitor_tool
async def risky_operation():
    try:
        raise ValueError("Something went wrong")
    except ValueError:
        raise
```

Errors are captured in the emitted event payload with status and error details.

## Graceful shutdown

```python
from core.registry import registry

async def main():
    try:
        pass
    finally:
        await registry.shutdown()
```

## Complete example

```python
import asyncio
from bootstrap import initialize_monitor
from core.decorators import monitor_tool

@monitor_tool
async def process_request(request_id: str, api_key: str):
    await asyncio.sleep(0.1)
    return {"status": "processed", "request_id": request_id}

async def main():
    await initialize_monitor("config.yaml")

    for i in range(10):
        await process_request(f"req_{i}", "secret_key_123")

await main()
```

## Notes

- The bootstrap flow is async by design.
- Exporters register only when enabled in config.
- Kafka producer tuning is driven by the settings model, including `max_workers` and `batch_size`.

## Next steps

- Review [Configuration Guide](configuration.md)
- Check [Architecture](architecture.md)
- See [Examples](examples.md)
