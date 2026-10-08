# Healthcheck API

AIMonitor provides a small asynchronous Python API for health information. It does not start an HTTP server and does not require FastAPI, Flask, or another web framework.

## Available functions

```python
from telemetry.api import get_liveness, get_readiness

liveness = await get_liveness()
readiness = await get_readiness()
```

`get_liveness()` only confirms that the process and SDK are running. It does not contact exporters:

```json
{"status": "alive"}
```

`get_readiness()` asks the registered exporters for their status and returns an aggregate result:

```json
{
  "status": "healthy",
  "overall": "healthy",
  "summary": {
    "total_exporters": 1,
    "healthy_count": 1,
    "unhealthy_count": 0
  },
  "exporters": [
    {
      "name": "PrometheusExporter",
      "status": "healthy",
      "message": "Exporter is operational.",
      "details": {}
    }
  ]
}
```

Possible aggregate statuses are `healthy`, `degraded`, `unhealthy`, and `empty`.

## FastAPI integration

The host application owns the HTTP server and decides which routes to expose:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from bootstrap import initialize_monitor
from telemetry.api import get_liveness, get_readiness


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_monitor("config.yaml")
    yield
    from core.registry import registry
    await registry.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/health/live")
async def health_live():
    return await get_liveness()


@app.get("/health/ready")
async def health_ready():
    return await get_readiness()
```

The same functions can be connected to Starlette, Flask through an adapter, or any custom HTTP layer.

## Operational guidance

- Keep liveness cheap and independent from external services.
- Use readiness for exporter connectivity and dependency checks.
- Protect diagnostic routes at the application or network layer.
- Do not expose credentials or unsanitized configuration in health responses.
- Do not add a public reload endpoint unless it is explicitly authenticated and required by the host application.
