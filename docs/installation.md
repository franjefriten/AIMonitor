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
pip install "aimonitor[opentelemetry]"

# SQLite export
pip install "aimonitor[sqlite]"

# Prometheus metrics
pip install "aimonitor[metrics]"

# Redis export
pip install "aimonitor[redis]"

# Kafka producer
pip install "aimonitor[kafka]"

# Multiple extras
pip install "aimonitor[opentelemetry,sqlite,metrics,kafka]"

# All extras
pip install "aimonitor[opentelemetry,sqlite,metrics,redis,kafka]"
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
uv pip install "aimonitor[opentelemetry,sqlite,metrics]"
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
from core.decorators import monitor_tool
from core.registry import registry

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
pip install "aimonitor[opentelemetry]"
```

### ImportError: No module named 'aiosqlite'

For SQLite exporter:

```bash
pip install "aimonitor[sqlite]"
```

### ImportError: No module named 'prometheus_client'

For Prometheus exporter:

```bash
pip install "aimonitor[metrics]"
```

## Next steps

- Read the [Usage Guide](usage.md)
- Check [Configuration](configuration.md)
- Explore [Examples](examples.md)
