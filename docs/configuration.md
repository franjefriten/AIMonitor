# Configuration Guide

AIMonitor loads configuration from environment variables, `.env` files, YAML files, and JSON files. The runtime model is defined in `AIMonitorSettings`, and exporter registration is handled by the async bootstrap function.

## Runtime bootstrap

Use the async bootstrap instead of calling sync helpers from inside the active event loop:

```python
from bootstrap import initialize_monitor

async def main():
    settings = await initialize_monitor("config.yaml")
    print(settings.prometheus_enabled, settings.kafka_enabled)
```

The `initialize_monitor()` function:

1. Loads the config file into `AIMonitorSettings`
2. Applies environment variables with highest precedence
3. Registers only the exporters that are enabled in the config
4. Returns the settings instance for runtime use

## Environment variables

All settings accept the `AIMONITOR_` prefix. Common examples:

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
AIMONITOR_FILE_PATH=./logs
AIMONITOR_MAX_MB_PER_FILE=10.0
AIMONITOR_RETRIES_POLICY=3
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service
AIMONITOR_OTEL_MCP_SPAN_PREFIX=mcp.tool
```

## YAML configuration

AIMonitor accepts a nested exporter layout, including Kafka producer settings and internal SDK telemetry health checks:

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
  prometheus:
    enabled: true
    url: "http://localhost:9000"

  file:
    enabled: true
    file_path: "./tmp_runtime_logs"

  otel:
    enabled: true
    service_name: "aimonitor-test"
    span_prefix: "mcp.test"

  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "SASL_SSL"
    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
```

Then load it with:

```python
from configs.config import get_settings

settings = get_settings()
await settings.load_from_yaml("config.yaml")
```

## JSON configuration

```json
{
  "app": {
    "env": "ENV"
  },
  "tracking": {
    "enabled": true,
    "track_metrics": true,
    "track_events": true,
    "track_logs": true
  },
  "telemetry": {
    "inner_telemetry": false,
    "healthcheck_enabled": true,
    "healthcheck_interval": 60
  },
  "exporters": {
    "prometheus": {
      "enabled": true,
      "url": "http://localhost:9000"
    },
    "kafka": {
      "enabled": true,
      "bootstrap_servers": "localhost:9092",
      "producer": {
        "acks": "all",
        "batch_size": 2048,
        "max_workers": 12
      }
    }
  }
}
```

```python
from configs.config import get_settings

settings = get_settings()
await settings.load_from_json("config.json")
```

## Runtime fields

The config parser exposes both exporter runtime settings and internal telemetry settings on `AIMonitorSettings`:

### Internal telemetry

- `inner_telemetry`
- `healthcheck_enabled`
- `healthcheck_interval`

These control the SDK observability layer and the background exporter readiness loop.

### Kafka exporter

- `kafka_enabled`
- `kafka_bootstrap_servers`
- `kafka_producer_acks`
- `kafka_retry_policy`
- `kafka_max_workers`
- `kafka_batch_size`
- `kafka_buffer_timeout`
- `kafka_producer_linger_ms`

`get_kafka_config()` builds the exact dict expected by the Confluent Kafka producer.

## Configuration precedence

Settings are applied in this order (highest to lowest priority):

1. **Environment variables** (`AIMONITOR_*` prefix)
2. Runtime values from `load_from_yaml()` / `load_from_json()`
3. Built-in defaults in `AIMonitorSettings`

Environment variables always override file-based configuration. This enables secure credential injection and environment-specific overrides.

## Sensitive data redaction

These keys are redacted by default:

- password
- token
- api_key
- secret
- apikey
- access_token
- client_secret
- private_key
- credentials

You can extend this list with:

```python
settings = get_settings()
settings.sensitive_keys.add("my_secret_field")
```

## Troubleshooting

### Config is not loading

Check that the file exists and that the YAML/JSON structure matches the runtime schema:

```python
settings = get_settings()
await settings.load_from_yaml("config.yaml")
```

### Kafka values are ignored

Make sure they are placed in the correct structure:

```yaml
exporters:
  kafka:
    enabled: true
    producer:
      batch_size: 2048
      max_workers: 12
```

## References

- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Confluent Kafka Python client](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html)
