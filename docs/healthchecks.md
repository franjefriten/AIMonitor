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

## How to write healthchecks for custom exporters

AIMonitor allows developers to create their own exporters as one of its main features as long as they follow the class inherits from `BaseExporter`. When writing the mandatory `healthcheck` method, users must always comply to the following contract

* When the function returns `True`, AIMonitor will send a `HEALTHY` status event under the hood
* When the function returns `False`, AIMonitor will send a `DOWN` status event. Then, AIMonitor will attempt to recover the exporter and send a `RECOVERING` status event.
* When the function raises an unexpected error, AIMonitor will catch it an emit a `FAILURE` status event. Always make sure to write solid code when to avoid this scenario.
* If a healthcheck exceeds the declared interval in the YAML/JSON file or env variables, AIMonitor will interpret the exporter failed and emit `FAILURE` status event	

```Python
from expoerters.base import BaseExporter

class CustomExporter(BaseExporter):

  async def healthcheck(self):
    try:
	    if ...:
	    	return True
		else:
      	   	return False
	except:
		# so somethinf
```

dfsfsda
