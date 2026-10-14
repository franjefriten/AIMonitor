# Installation Guide

## Prerequisites

- Python 3.10 or higher
- pip or uv package manager

## Package installation

### From PyPI

```bash
pip install aimonitor
```

### With optional dependencies

Install only what you need:

```bash
# OpenTelemetry integration
pip install "ai-monitor-sdk[opentelemetry]"

# SQLite export
pip install "ai-monitor-sdk[sqlite]"

# Prometheus metrics
pip install "ai-monitor-sdk[prometheus]"

# Kafka producer
pip install "ai-monitor-sdk[kafka]"

# Multiple extras
pip install "ai-monitor-sdk[opentelemetry,sqlite,prometheus,kafka]"
```

### From source

```bash
git clone https://github.com/franjefriten/AIMonitor.git
cd AIMonitor
pip install -e .
```

With optional dependencies:

```bash
pip install -e ".[opentelemetry,sqlite,metrics]"
```

## Using uv (faster)

If you're using `uv` as your Python package manager:

```bash
uv pip install aimonitor
uv pip install "aimonitor[opentelemetry,sqlite,prometheus]"
```

Or from source:

```bash
git clone https://github.com/franjefriten/AIMonitor.git
cd AIMonitor
uv sync --extra opentelemetry --extra sqlite --extra metrics
```

## Verifying installation

Check that AIMonitor is installed correctly:

```python
import aimonitor
from aimonitor.core.decorators import monitor_tool
from aimonitor.core.registry import registry

print("✅ AIMonitor installed successfully!")
```

## Virtual environment (recommended)

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install AIMonitor
pip install aimonitor
```

## Troubleshooting

### ImportError: No module named 'opentelemetry'

If you're using OpenTelemetry features, install the optional dependency:

```bash
pip install "ai-monitor-sdk[opentelemetry]"
```

### ImportError: No module named 'aiosqlite'

For SQLite exporter:

```bash
pip install "ai-monitor-sdk[sqlite]"
```

### ImportError: No module named 'prometheus_client'

For Prometheus exporter:

```bash
pip install "ai-monitor-sdk[metrics]"
```

## Next steps

- Read the [Usage Guide](usage.md)
- Check [Configuration](configuration.md)
- Explore [Examples](examples.md)
