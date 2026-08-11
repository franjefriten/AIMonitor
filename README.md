# 🔍 AIMonitor

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
pip install aimonitor
```

With optional dependencies:

```bash
pip install "aimonitor[opentelemetry,sqlite,metrics,kafka]"
```

### Monitor a tool

```python
from core.decorators import monitor_tool

@monitor_tool
async def fetch_data(user_id: str):
    return {"data": "example"}
```

### Export events

```python
from exporters.file import FileExporter
from core.registry import registry

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

## 🔌 Available Exporters

| Exporter | Purpose | Status |
|----------|---------|--------|
| **FileExporter** | JSONL file output with rotation | ✅ Stable |
| **SQLiteExporter** | Local database storage | ✅ Stable |
| **PrometheusExporter** | Prometheus metrics endpoint | ✅ Stable |
| **OpenTelemetryExporter** | OTel span export | ✅ Stable |
| **WebhookExporter** | HTTP endpoint POST | ✅ Stable |
| **RedisExporter** | Redis pub/sub | ⚠️ Beta |
| **KafkaExporter** | Kafka topic producer | ⚠️ Beta |

## 🔧 Configuration

### Environment variables

```bash
# Core settings
AIMONITOR_ENABLED=true
AIMONITOR_INNER_TELEMETRY=false

# Export targets
AIMONITOR_PROMETHEUS_URL=http://localhost:9000
AIMONITOR_SQLITE_URI=./aimonitor.db

# OpenTelemetry MCP exporter
AIMONITOR_OTEL_MCP_EXPORTER_ENABLED=true
AIMONITOR_OTEL_MCP_SERVICE_NAME=my-service
```

### Or with YAML

```yaml
enabled: true
inner_telemetry: false
prometheus_url: "http://localhost:9000"
otel_mcp_exporter_enabled: true
otel_mcp_service_name: "my-mcp-service"
```

## 🧪 Testing

Run the test suite:

```bash
# Unit tests
python -m pytest tests/unit -q

# All tests
python -m pytest tests/ -v
```

Tests run automatically on every PR to `main`.

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
