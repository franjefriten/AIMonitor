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

In AIMonitor, an *Exporter* refers to a class that inherits from *BaseExporter* class. Their purpose is to serve as a client to your custom storage for tool traces, tokens, etc. As such, AIMonitor comes with a set of programmed exporters:

#### 🔌 Available Exporters

| Exporter                        | Purpose                         | Status                       |
| ------------------------------- | ------------------------------- | ---------------------------- |
| **FileExporter**          | JSONL file output with rotation | ✅ Stable                    |
| **SQLiteExporter**        | Local database storage          | ✅ Stable                    |
| **PrometheusExporter**    | Prometheus metrics endpoint     | ⚠️ On development         |
| **OpenTelemetryExporter** | OTel span export                | ✅ Stable                    |
| **WebhookExporter**       | HTTP endpoint POST              | ✅ Stable                    |
| **KafkaExporter**         | Kafka topic producer            | ✅ Stable                   |
| **PostgreSQLExporter**    | Postgres implementation         | ❌ Coming on future releases |
| **MongoDBExporter**       | MongoDb implementation          | ❌ Coming on future releases |

However, AIMonitor is designed as a flexible sdk, meaning you can create your own custom exporters as long as you follow the contract explained later on the documentation of this repo.

#### 🔧 Configuration

AIMonitor is thought from the beginning with one core idea: **simple configuration**. As such, setting up exporters requires only two simple steps

* Create a YAML/JSON config file following the example below. This will be used as the source of truth for your exporters' configuration

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

exporter = FileExporter(base_uri="./logs")
await exporter.connect()
registry.register(exporter)

# Now all monitored tool calls are exported to ./logs
```

## 📚 Documentation

- **[Usage Guide](docs/usage.md)** — Configuration, exporters, and examples
- **[Architecture](docs/architecture.md)** — Core components and design
- **[Installation](docs/installation.md)** — Dependency management
- **[Contributing](docs/CONTRIBUTING.md)** — Development workflow

## 🧪 Testing

Run the test suite:

```bash
# Unit tests
python -m pytest tests/unit -q

# Integration tests
# Run furst the setup scripts foumd om /scripts

# kafka
sh scripts/prometheus/sh/run_prometheus.sh
# prometheus
sh scripts/kafka/sh/run_kafka.sh

python -m pytest tests/integration

# All tests
python -m pytest tests/ -v
```

Tests run automatically on every PR to `main`. Scripts for batch/Powershell are also found under the  `/batch` subfolder for test running

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
