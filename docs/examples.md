# Examples

Practical examples demonstrating AIMonitor features.

## Basic monitoring

Monitor an async function with the `@monitor_tool` decorator:

```python
from core.decorators import monitor_tool
import asyncio

@monitor_tool
async def fetch_user_data(user_id: str):
    """Fetch user data from a hypothetical API."""
    # Simulate API call
    await asyncio.sleep(0.5)
    return {"id": user_id, "name": "John Doe", "email": "john@example.com"}

# Call the monitored tool
await fetch_user_data("user123")
```

Events are automatically captured and sent to registered exporters.

## File export

Export events to JSONL files with automatic rotation:

```python
from exporters.file import FileExporter
from core.registry import registry

# Create and register exporter
exporter = FileExporter(
    base_uri="./monitoring_logs",
    max_bytes=1024 * 1024  # 1 MB rotation
)
await exporter.connect()
registry.register(exporter)

# Now all monitored tool calls write to ./monitoring_logs/*.jsonl
```

## SQLite export

Persist events to SQLite for querying:

```python
from exporters.sqlite import SQLiteExporter
from core.registry import registry

exporter = SQLiteExporter(dsn="./aimonitor.sqlite")
await exporter.connect()
registry.register(exporter)

# Query events later
import aiosqlite
async with aiosqlite.connect("./aimonitor.sqlite") as db:
    async with db.execute("SELECT * FROM aimonitor_event") as cursor:
        events = await cursor.fetchall()
        print(f"Total events: {len(events)}")
```

## Prometheus metrics

Expose metrics to Prometheus:

```python
from exporters.prometheus import PrometheusExporter
from core.registry import registry

exporter = PrometheusExporter(address="http://0.0.0.0:9000")
await exporter.connect()
registry.register(exporter)

# Metrics available at http://localhost:9000/metrics
# - mcp_total_calls_total (counter by tool_name and status)
# - mcp_tool_duration_seconds (histogram by tool_name)
```

## OpenTelemetry export

Export MCP events as OTel spans:

```python
from exporters.opentelemetry import OpenTelemetryExporter
from core.registry import registry

# Configure OTel collector
import os
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"

exporter = OpenTelemetryExporter(
    enabled=True,
    service_name="my-mcp-service",
    span_prefix="mcp.tool"
)
registry.register(exporter)

# Events exported as spans to OTEL_EXPORTER_OTLP_ENDPOINT
```

## Multiple exporters

Register multiple exporters simultaneously:

```python
from exporters.file import FileExporter
from exporters.sqlite import SQLiteExporter
from exporters.prometheus import PrometheusExporter
from core.registry import registry

# File export for archival
file_exp = FileExporter(base_uri="./logs")
await file_exp.connect()
registry.register(file_exp)

# SQLite for queries
sqlite_exp = SQLiteExporter(dsn="./aimonitor.sqlite")
await sqlite_exp.connect()
registry.register(sqlite_exp)

# Prometheus for real-time metrics
prom_exp = PrometheusExporter()
await prom_exp.connect()
registry.register(prom_exp)

# All exporters receive events in parallel
```

## Sensitive data redaction

Tool arguments containing sensitive keys are automatically redacted:

```python
from core.decorators import monitor_tool

@monitor_tool
async def authenticate(username: str, password: str, api_key: str):
    """Authentication with secrets."""
    # password and api_key will be masked in events
    return {"authenticated": True}

await authenticate("john", "secret123", "key_abc123")
# Event args: {"username": "john", "password": "********", "api_key": "********"}
```

Customize sensitive keys:

```python
from configs.config import get_settings

settings = get_settings()
settings.sensitive_keys.add("custom_secret")
```

## Internal SDK telemetry

Enable AIMonitor's own observability (separate from event export):

```python
from telemetry.api import configure_internal_telemetry

# Enable internal traces
manager = configure_internal_telemetry(
    enabled=True,
    service_name="aimonitor-sdk"
)

# Now AIMonitor itself emits spans to OTel
```

## Webhook export

Send events to an HTTP endpoint:

```python
from exporters.http import WebhookExporter
from core.registry import registry

exporter = WebhookExporter(
    url="https://example.com/webhooks/events",
    headers={"Authorization": "Bearer token123"}
)
await exporter.connect()
registry.register(exporter)

# All events posted as JSON to the webhook
```

## Kafka producer

Stream events to Kafka:

```python
from exporters.kafka import KafkaExporter
from core.registry import registry

exporter = KafkaExporter(
    topic="aimonitor-events",
    kafka_configs={
        "bootstrap.servers": "localhost:9092",
        "group.id": "aimonitor-group"
    }
)
registry.register(exporter)

# Events published to Kafka topic
await exporter.close()
```

## Error handling

Tools can emit error events:

```python
from core.decorators import monitor_tool

@monitor_tool
async def risky_operation():
    try:
        # Some operation that might fail
        raise ValueError("Something went wrong")
    except ValueError as e:
        # Decorator captures the error
        raise  # Re-raise for monitoring

await risky_operation()
# Event status: "error", error field populated
```

## Graceful shutdown

Always close exporters when done:

```python
from core.registry import registry

# Use with statement for safety
class MonitoredApp:
    async def __aenter__(self):
        # Setup exporters
        return self
    
    async def __aexit__(self, *args):
        # Graceful shutdown
        await registry.shutdown()

# Usage
async with MonitoredApp() as app:
    # Your code here
    pass
```

## Advanced: Custom exporter

Extend `BaseExporter` for custom behavior:

```python
from exporters.base import BaseExporter
from core.event import MCPEvent
from typing import List

class CustomExporter(BaseExporter):
    async def export(self, event: MCPEvent) -> None:
        print(f"Custom export: {event.tool_name}")
    
    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        for event in event_batch:
            await self.export(event)

# Register
from core.registry import registry
registry.register(CustomExporter())
```

## Next steps

- [Configuration Guide](configuration.md)
- [Architecture](architecture.md)
- [Contributing](CONTRIBUTING.md)
