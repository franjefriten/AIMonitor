# Configuration Guide

AIMonitor uses environment variables, `.env` files, YAML, or JSON configuration to customize behavior.

## Environment variables

All settings can be set via environment variables with the `AIMONITOR_` prefix.

### Core settings

```bash
# Enable/disable monitoring
AIMONITOR_ENABLED=true

# Enable internal SDK telemetry
AIMONITOR_INNER_TELEMETRY=false

# Environment (ENV, STG, PRO)
AIMONITOR_ENV=ENV

# Sensitive keys to redact
AIMONITOR_SENSITIVE_KEYS=password,token,api_key,secret
```

### Export settings

```bash
# Prometheus endpoint
AIMONITOR_PROMETHEUS_URL=http://localhost:9000

# SQLite database path
AIMONITOR_SQLITE_URI=./aimonitor.sqlite

# File exporter logs directory
AIMONITOR_FILE_EXPORTER_LOGS=./logs

# Max file size in MB
AIMONITOR_MAX_MB_PER_FILE=10.0

# Retry policy count
AIMONITOR_RETRIES_POLICY=3
```

### Event tracking

```bash
# Track metrics
AIMONITOR_TRACK_METRICS=true

# Track events
AIMONITOR_TRACK_EVENTS=true

# Track logs
AIMONITOR_TRACK_LOGS=true
```

### OpenTelemetry MCP exporter

```bash
# Enable OTel export for MCP events
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true

# Service name for OTel
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service

# Span name prefix
AIMONITOR_OTEL_MCP_SPAN_PREFIX=mcp.tool

# OTel collector endpoint (set globally)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

## Configuration files

### YAML configuration

Create a `config.yaml`:

```yaml
enabled: true
inner_telemetry: false
env: ENV
track_events: true
track_metrics: true
prometheus_url: "http://localhost:9000"
sqlite_uri: "./aimonitor.sqlite"
file_exporter_logs: "./logs"
max_mb_per_file: 10.0
retries_policy: 3
otel_mcp_exporter_enabled: true
otel_mcp_service_name: "my-service"
otel_mcp_span_prefix: "mcp.tool"
```

Load it in your code:

```python
from configs.config import get_settings

settings = get_settings()
await settings.load_from_yaml("config.yaml")
```

### JSON configuration

Create a `config.json`:

```json
{
  "enabled": true,
  "inner_telemetry": false,
  "env": "ENV",
  "track_events": true,
  "track_metrics": true,
  "prometheus_url": "http://localhost:9000",
  "sqlite_uri": "./aimonitor.sqlite",
  "otel_mcp_exporter_enabled": true,
  "otel_mcp_service_name": "my-service"
}
```

Load it:

```python
from configs.config import get_settings

settings = get_settings()
await settings.load_from_json("config.json")
```

### .env file

Create a `.env` file in your project root:

```env
AIMONITOR_ENABLED=true
AIMONITOR_INNER_TELEMETRY=false
AIMONITOR_PROMETHEUS_URL=http://localhost:9000
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service
```

Python will automatically load `.env` via `python-dotenv`.

## Configuration precedence

Settings are loaded in this order (later overrides earlier):

1. Hardcoded defaults in `AIMonitorSettings`
2. Environment variables
3. `.env` file
4. Runtime `load_from_yaml()` or `load_from_json()`
5. Explicit constructor arguments

## Example: Full setup

```python
from configs.config import get_settings
from exporters.file import FileExporter
from exporters.prometheus import PrometheusExporter
from exporters.opentelemetry import OpenTelemetryExporter
from core.registry import registry

# Load settings
settings = get_settings()

# File exporter
file_exp = FileExporter(base_uri="./logs", max_bytes=10_000_000)
await file_exp.connect()
registry.register(file_exp)

# Prometheus exporter
if settings.track_metrics:
    prom_exp = PrometheusExporter()
    await prom_exp.connect()
    registry.register(prom_exp)

# OpenTelemetry exporter
if settings.otel_mcp_exporter_enabled:
    otel_exp = OpenTelemetryExporter()
    registry.register(otel_exp)

print("✅ AIMonitor configured and ready!")
```

## Sensitive data redaction

By default, these fields are redacted:

- password
- token
- api_key
- secret
- apikey
- access_token
- client_secret
- private_key
- credentials

To add more fields:

```bash
AIMONITOR_SENSITIVE_KEYS=password,token,api_key,secret,custom_field
```

Or programmatically:

```python
from configs.config import get_settings

settings = get_settings()
settings.sensitive_keys.add("my_secret_field")
```

## Troubleshooting

### Settings not being loaded from .env

Ensure the `.env` file is in your working directory, and use:

```python
from dotenv import load_dotenv
load_dotenv()  # Load .env before importing settings
from configs.config import get_settings
```

### OpenTelemetry not initialized

Check that:
- `AIMONITOR_INNER_TELEMETRY=true` is set
- `opentelemetry-api` and `opentelemetry-sdk` are installed
- Set valid `OTEL_*` environment variables

## References

- [Environment variables](https://docs.python.org/3/library/os.html)
- [python-dotenv](https://python-dotenv.readthedocs.io/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
