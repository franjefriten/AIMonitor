# Healthcheck API

AIMonitor provides a small asynchronous Python API for health information. It does not start an HTTP server and does not require FastAPI, Flask, or another web framework.

## Available functions

```python
from telemetry.api import get_process_liveness, get_sdk_readiness, get_telemetry_status

liveness = await get_process_liveness()
readiness = await get_sdk_readiness()
telemetry = get_telemetry_status()
```

`get_process_liveness()` only confirms that the process and SDK are running. It does not contact exporters:

```json
{"status": "alive"}
```

`get_sdk_readiness()` returns the latest cached snapshot maintained by the `ExporterRegistry`. It does not call exporter healthchecks or diagnostic methods during the request:

```json
{
  "status": "healthy",
  "checked_at": "2026-10-13T12:00:00+00:00",
  "summary": {
    "total_exporters": 1,
    "healthy_count": 1,
    "unhealthy_count": 0
  },
  "exporters": [
    {
      "name": "PrometheusExporter",
      "status": "healthy",
      "message": "Health check completed."
    }
  ]
}
```

Possible aggregate statuses are `healthy`, `degraded`, `down`, `starting`, and `empty`.

The registry snapshot is the source of truth for health. Exporters may implement `describe()` to expose backend-specific diagnostic information, but that method does not determine readiness.

`get_telemetry_status()` is a local query of OpenTelemetry provider availability. It reports whether the SDK has an active tracer and meter; it does not query an external telemetry backend. Backend queries require the backend's own client or API.

## FastAPI integration

The host application owns the HTTP server and decides which routes to expose:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from bootstrap import initialize_monitor
from telemetry.api import get_process_liveness, get_sdk_readiness


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_monitor("config.yaml")
    yield
    from core.registry import registry
    await registry.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/health/live")
async def health_live():
  return await get_process_liveness()


@app.get("/health/ready")
async def health_ready():
  return await get_sdk_readiness()
```

The same functions can be connected to Starlette, Flask through an adapter, or any custom HTTP layer.

## Operational guidance

- Keep process liveness cheap and independent from external services.
- Use SDK readiness for exporter connectivity and dependency checks.
- Protect diagnostic routes at the application or network layer.
- Do not expose credentials or unsanitized configuration in health responses.
- Do not add a public reload endpoint unless it is explicitly authenticated and required by the host application.

## How to implement a custom exporter

A custom exporter must implement `export_batch()`, `healthcheck()`, `describe()`, and `recover()`:

```python
from exporters.base import BaseExporter


class CustomExporter(BaseExporter):
  async def export_batch(self, event_batch):
    ...

  async def healthcheck(self) -> bool:
    # Return True only when the exporter can perform its job.
    return True

  async def describe(self) -> dict:
    # Diagnostic data only; this does not control readiness.
    return {"destination": "custom-backend"}

  async def recover(self) -> bool:
    # Reconnect or restore local exporter resources.
    return True
```

The registry maps healthcheck results to snapshots:

| Snapshot status | Meaning |
| --- | --- |
| `healthy` | The healthcheck completed and returned `True`. |
| `down` | The healthcheck completed and returned `False`. The exporter is known to be unhealthy. |
| `failure` | The healthcheck could not complete because it raised an exception or timed out. The exporter is also considered unhealthy, but its health could not be evaluated normally. |
| `recovering` | Recovery is in progress after an unhealthy result. |

Recovery is followed by another healthcheck before the exporter can become `healthy` again.
