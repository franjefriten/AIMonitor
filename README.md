🔍 AIMonitor

> A lightweight, modular observability toolkit for MCP (Multi-Channel Processing) workflows

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/franjefriten/AIMonitor/actions/workflows/python-tests.yml/badge.svg)](https://github.com/franjefriten/AIMonitor/actions)

AIMonitor tracks tool execution, exports monitoring events, and supports **OpenTelemetry** integration alongside file, SQLite, and Prometheus backends.

## ✨ Features

- 🎯 **Tool Monitoring** — Automatic event capture with `@monitor_tool` decorator
- 📤 **Multiple Exporters** — File, SQLite, Prometheus, Redis, Kafka, Webhook, OpenTelemetry
- 🔐 **Sensitive Data Redaction** — Automatically masks API keys and secrets
- 🛡️ **Authentication for exporters** — The sdk provides an authentication layer for safe monitoring 
- 🧠 **Internal Telemetry** — Optional SDK observability via OpenTelemetry
- ⚡ **Async-first** — Built for async workflows
- 🛠️ **Extensible** — Simple interface for custom exporters

## 🚀 Quick start

### Install

```bash
pip install ai-monitor-sdk
```

This will install the most basic implementation of AIMonitor, but most exporters will not work with it, as it depends on their own sdk to use them. Run the following command to install their optional dependencies depending on which exporters you want to make use of.

```bash
pip install "ai-monitor-sdk[opentelemetry,sqlite,prometheus,kafka]"
```

### Exporters

In AIMonitor, an *Exporter* implements the `ProtocolExporter` batch interface.
Inheriting from `BaseExporter` additionally opts into health checks and recovery.
Exporters serve as clients to your custom storage for tool traces, tokens, etc.
AIMonitor comes with a set of programmed exporters:

#### 🔌 Available Exporters

| Exporter                        | Purpose                         | Status                       |
| ------------------------------- | ------------------------------- | ---------------------------- |
| **FileExporter**          | JSONL file output with rotation | ✅ Stable                    |
| **SQLiteExporter**        | Local database storage          | ✅ Stable                    |
| **PrometheusExporter**    | Prometheus metrics endpoint     | ✅ Stable                    |
| **OpenTelemetryExporter** | OTel span export                | ✅ Stable                    |
| **WebhookExporter**       | HTTP endpoint POST              | ✅ Stable                    |
| **KafkaExporter**         | Kafka topic producer            | ✅ Stable                   |
| **PostgreSQLExporter**    | Postgres implementation         | ❌ Coming on future releases |
| **MongoDBExporter**       | MongoDb implementation          | ❌ Coming on future releases |

However, AIMonitor is designed as a flexible SDK. Custom exporters can implement
the minimal `ProtocolExporter` contract by providing `export()` only, or
inherit from `BaseExporter` to participate in health checks and recovery.
Simple protocol exporters are dispatched normally but are not included in
health/readiness snapshots.

#### 🔧 Configuration

AIMonitor is thought from the beginning with one core idea: **simple configuration**. As such, setting up exporters requires only two simple steps

* Create a YAML/JSON config file following the example below. This will be used as the source of truth for your exporters' configuration

```yaml
app:
  env: DEV
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

* Inside the lifespan of your desired server, execute the `initialize_monitor` function

```Python
from aimonitor.bootstrap import initialize_monitor, shutdown_monitor
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_monitor(config_path="aimonitor_config.yaml")
	yield
	await shutdown_monitor()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def hello_world():
    return {"msg": "Hellow World!", "status": 200}
```

AIMonitor is **fully async** with options for syncronicity if necessary. The SDK also allows to use JSON files for the config file as well as using env variables, starting with `AIMONITOR_`. Refer to the documentation for extra examples and description.

### Monitor a tool

AIMonitor allows you to monitor tools that are executed by an LLM or even tools executed through the MCP protocol, on an MCP server. The most basic example is this one

```python
from aimonitor.core.decorators import monitor_tool

@monitor_tool
async def fetch_data(user_id: str):
    return {"data": "example"}
```

Assuming we are using FastMCP to create an mcp server, we can set up

```Python
from aimonitor.core.decorators import monitor_tool
from fastmcp import FastMCP
from aimonitor.bootstrap import initialize_monitor, shutdown_monitor
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_monitor(config_path="aimonitor_config.yaml")
	yield
	await shutdown_monitor()

mcp = FastMCP(name="CalculatorServer", lifespan=lifespan)

@mcp.tool
@monitor_tool(track_duration=False, track_tool_count=True)
def add(a: int, b: int) -> int:
    """Adds two integer numbers together."""
    return a + b
```

Refer to the documentation on [usage](docs/usage.md) for further explanation on how to set up

### Export events

```python
from aimonitor.exporters.file import FileExporter
from aimonitor.core.registry import registry
from aimonitor.core.event import MCPEvent

exporter = FileExporter(base_uri="./logs")
await exporter.connect()
registry.register(exporter)

# Monitored tool calls are exported automatically. Signals can also be
# dispatched explicitly through the SDK registry:
await registry.dispatch(MCPEvent(tool_name="manual_event"))
```

## 📚 Documentation

- **[Usage Guide](docs/usage.md)** — Configuration, exporters, and examples
- **[Architecture](docs/architecture.md)** — Core components and design
- **[Installation](docs/installation.md)** — Dependency management
- **[Healthchecks](docs/healthchecks.md)** — Liveness, readiness, and recovery
- **[Exporter Guide](docs/exporters.md)** — Built-in exporter contracts
- **[Contributing](docs/CONTRIBUTING.md)** — Development workflow

Design reports for package layout, configuration, exceptions, healthchecks,
the roadmap, Kafka, and OpenTelemetry are available under [reports/](reports/).

## 🧪 Testing

Run the test suite:

```bash
# Unit tests
python -m pytest tests/unit -q

# Integration tests
# Run furst the setup scripts foumd om /scripts

# Prometheus
sh scripts/prometheus/sh/run_prometheus.sh
# Restart Prometheus
sh scripts/prometheus/sh/restart_prometheus.sh
# Kafka
sh scripts/kafka/sh/run_kafka.sh

python -m pytest tests/integration

The Prometheus scripts use container name `prometheus` and host port `9090` by default. Override `PROMETHEUS_CONTAINER_NAME` and `PROMETHEUS_HOST_PORT` to run an isolated instance.

# All tests
python -m pytest tests/ -v
```

Tests run automatically on every PR to `main`. Scripts for batch/Powershell are also found under the  `/batch` subfolder for test running

## Python compatibility and optional exporter dependencies

AIMonitor supports Python 3.10–3.14. Optional exporters need their corresponding dependencies; you can install them with extras such as `ai-monitor-sdk[opentelemetry,sqlite]`. The minimum dependency versions covered by the test setup are:

| Exporter extra | Minimum dependency |
| ---------------- | ------------------ |
| OpenTelemetry (API, SDK, OTLP/HTTP exporter), Python <3.14 | `1.24.0` |
| OpenTelemetry (API, SDK, OTLP/HTTP exporter), Python 3.14 | `1.35.0` |
| SQLite (`aiosqlite`) | `0.21.0` |
| Prometheus (`prometheus-client`) | `0.20.0` |
| Kafka (`confluent-kafka`) | `2.13.0` |

CI runs the unit and integration suites on every supported Python version with both dependency sets:

| Dependency set | Python versions | What CI checks |
| -------------- | --------------- | -------------- |
| Minimum | 3.10–3.14 | All unit and integration tests except those marked `opentelemetry` |
| Latest | 3.10–3.14 | All unit and integration tests, including OpenTelemetry tests |

OpenTelemetry 1.24 is incompatible with Python 3.14: its Protobuf constraint can select Protobuf 4.25.9, which fails to import on that Python version. For Python 3.14, install OpenTelemetry SDK 1.35.0 or newer; AIMonitor raises `OpenTelemetryCompatibilityError` if an older SDK is installed. Python 3.10–3.13 can use the 1.24.0 minimum.

## 📦 Deployment

### Publish to PyPI

```bash
# Update version in pyproject.toml
python -m build
python -m twine upload dist/*
```

### Docker

AIMonitor works in containerized environments. Set environment variables and mount config files as needed.

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md).

1. Fork the repo
2. Create a feature branch
3. Add tests for new features
4. Open a PR to `main`

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🎯 Roadmap

- [ ] Enhanced A2A (Agent-to-Agent) support
- [ ] Skills framework integration
- [ ] Web dashboard for event visualization
- [ ] Advanced filtering and querying
- [ ] Multi-backend batch export

---

**Questions?** Open an [issue](https://github.com/franjefriten/AIMonitor/issues) or check the [docs](docs/).
