# AIMonitor Usage Guide

## Overview

AIMonitor is a modular observability toolkit for MCP (Multi-Channel Processing) workflows. It provides:

- 🎯 tool monitoring and event tracking
- 📤 export support for file, SQLite, Prometheus, Redis, and OpenTelemetry
- 🔐 automatic sensitive data redaction
- 🧠 optional internal SDK telemetry for debugging and platform metrics

## Installation

Install the package from PyPI or GitHub:

```bash
pip install aimonitor
```

If you want optional integrations, install extras:

```bash
pip install "aimonitor[opentelemetry,sqlite,metrics,redis]"
```

See [Installation Guide](installation.md) for detailed setup options.

## Configuration

AIMonitor loads settings from environment variables, `.env` files, or explicit runtime configuration.

### Quick setup with environment variables

A few core examples:

```bash
AIMONITOR_ENABLED=true
AIMONITOR_INNER_TELEMETRY=false
AIMONITOR_PROMETHEUS_URL=http://localhost:9000
```

### Enable internal telemetry

To enable AIMonitor's own internal telemetry:

```bash
AIMONITOR_INNER_TELEMETRY=true
```

### OpenTelemetry exporter for MCP events

If you want monitored MCP events to be exported as OpenTelemetry spans:

```bash
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service
AIMONITOR_OTEL_MCP_SPAN_PREFIX=mcp.tool
```

See [Configuration Guide](configuration.md) for all options.

## Basic usage

### Instrumenting a tool with monitoring

Use the `@monitor_tool` decorator to automatically track tool execution:

```python
from core.decorators import monitor_tool
import asyncio

@monitor_tool
async def fetch_data(user_id: str, limit: int = 10):
    """Fetch data for a user."""
    # Your tool logic here
    return {"user_id": user_id, "records": []}

# Call the tool
result = await fetch_data("user123", limit=20)
# Event automatically captured with:
# - tool_name: "fetch_data"
# - args: {"user_id": "user123", "limit": 20}
# - delta: execution time
# - status: "success" or "error"
# - result: returned data
```

### Registering exporters

After decorating tools, register exporters to persist events:

```python
from exporters.file import FileExporter
from core.registry import registry

exporter = FileExporter(base_uri="./logs", max_bytes=10_000_000)
await exporter.connect()
registry.register(exporter)

# Now all monitored tool calls are exported
```

## Available exporters

### FileExporter

Writes events to JSONL files with automatic rotation:

```python
from exporters.file import FileExporter

exporter = FileExporter(
    base_uri="./monitoring_logs",
    max_bytes=1024 * 1024 * 10  # 10 MB rotation
)
await exporter.connect()
registry.register(exporter)
```

Output: `./monitoring_logs/2026-08-11_logfile.jsonl`

### SQLiteExporter

Stores events in SQLite tables for querying:

```python
from exporters.sqlite import SQLiteExporter

exporter = SQLiteExporter(
    dsn="./aimonitor.sqlite",
    table_name="aimonitor"
)
await exporter.connect()
registry.register(exporter)

# Query later
import aiosqlite
async with aiosqlite.connect("./aimonitor.sqlite") as db:
    async with db.execute("SELECT * FROM aimonitor_event") as cursor:
        events = await cursor.fetchall()
```

### PrometheusExporter

Exposes metrics to Prometheus:

```python
from exporters.prometheus import PrometheusExporter

exporter = PrometheusExporter(address="http://0.0.0.0:9000")
await exporter.connect()
registry.register(exporter)

# Metrics at http://localhost:9000/metrics
# - mcp_total_calls_total (counter)
# - mcp_tool_duration_seconds (histogram)
```

### OpenTelemetryExporter

Exports MCP events as OpenTelemetry spans:

```python
from exporters.opentelemetry import OpenTelemetryExporter
import os

# Configure OTel collector
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"

exporter = OpenTelemetryExporter(
    enabled=True,
    service_name="my-mcp-service",
    span_prefix="mcp.tool"
)
registry.register(exporter)
```

## Sensitive data protection

Sensitive fields are automatically redacted in events:

```python
@monitor_tool
async def authenticate(username: str, password: str):
    # password is automatically masked
    return {"authenticated": True}

# Event args: {"username": "john", "password": "****"}
```

Default masked fields:

- password
- token
- api_key
- secret
- apikey
- access_token
- client_secret
- private_key
- credentials

Customize:

```bash
AIMONITOR_SENSITIVE_KEYS=password,token,my_custom_field
```

## Error handling

Tools can emit error events automatically:

```python
@monitor_tool
async def risky_operation():
    try:
        raise ValueError("Something went wrong")
    except ValueError:
        # Decorator captures error
        raise  # Re-raise for monitoring
```

Event details:

- `status`: "error"
- `error`: exception message
- `result`: None

## Multiple exporters

Register multiple exporters simultaneously:

```python
from exporters.file import FileExporter
from exporters.sqlite import SQLiteExporter
from exporters.prometheus import PrometheusExporter
from core.registry import registry

# File export
file_exp = FileExporter(base_uri="./logs")
await file_exp.connect()
registry.register(file_exp)

# SQLite for queries
sqlite_exp = SQLiteExporter(dsn="./aimonitor.sqlite")
await sqlite_exp.connect()
registry.register(sqlite_exp)

# Prometheus for metrics
prom_exp = PrometheusExporter()
await prom_exp.connect()
registry.register(prom_exp)

# All receive events in parallel
```

## Graceful shutdown

Always close exporters when done:

```python
from core.registry import registry

async def main():
    # Setup code...
    try:
        # Your application logic
        pass
    finally:
        await registry.shutdown()  # Flush all exporters

await main()
```

## Internal SDK telemetry

Enable AIMonitor's own observability (separate from event export):

```python
from telemetry.api import configure_internal_telemetry

# Enable internal spans
manager = configure_internal_telemetry(
    enabled=True,
    service_name="aimonitor-sdk"
)

# AIMonitor now emits spans to OTel for its own operations
```

## Complete example

```python
import asyncio
from core.decorators import monitor_tool
from exporters.file import FileExporter
from exporters.prometheus import PrometheusExporter
from core.registry import registry

@monitor_tool
async def process_request(request_id: str, api_key: str):
    """Process an API request."""
    await asyncio.sleep(0.1)
    return {"status": "processed", "request_id": request_id}

async def main():
    # Setup exporters
    file_exp = FileExporter(base_uri="./logs")
    await file_exp.connect()
    registry.register(file_exp)
    
    prom_exp = PrometheusExporter()
    await prom_exp.connect()
    registry.register(prom_exp)
    
    try:
        # Use monitored tools
        for i in range(10):
            await process_request(f"req_{i}", "secret_key_123")
        
        print("✅ Events exported to ./logs and http://localhost:9000/metrics")
    finally:
        await registry.shutdown()

await main()
```

## Notes

AIMonitor is designed to separate internal SDK telemetry from user-facing MCP event export. Internal telemetry is for debugging the library itself and is disabled by default.

## Next steps

- Explore [Examples](examples.md)
- Review [Configuration Options](configuration.md)
- Check [Architecture](architecture.md)
- See [Contributing Guide](CONTRIBUTING.md)
