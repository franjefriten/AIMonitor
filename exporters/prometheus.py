from typing import List, Optional
from urllib.parse import urlparse

from configs.config import settings
from core.event import MCPEvent
from exporters.base import BaseExporter
from utils.logger import logger

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "prometheus_client is required for PrometheusExporter. Install it with pip install .[metrics]"
    ) from exc


class PrometheusExporter(BaseExporter):
    """Exporter that exposes AIMonitor events as Prometheus metrics."""

    def __init__(self, address: Optional[str] = None, registry: Optional[CollectorRegistry] = None):
        super().__init__()
        self.address = address or settings.prometheus_url
        self.registry = registry if registry is not None else CollectorRegistry(auto_describe=True)
        self._server_started = False

        parsed_url = urlparse(self.address)
        self.port = parsed_url.port or 9000
        self.addr = parsed_url.hostname or "0.0.0.0"

        self.counter = Counter(
            name="mcp_total_calls_total",
            documentation="Total tool executions",
            labelnames=["tool_name", "status"],
            registry=self.registry,
        )
        self.histogram = Histogram(
            name="mcp_tool_duration_seconds",
            documentation="Total execution duration",
            labelnames=["tool_name"],
            registry=self.registry,
        )

    async def connect(self) -> None:
        if self._server_started:
            return
        start_http_server(port=self.port, addr=self.addr, registry=self.registry)
        self._server_started = True

    async def export(self, event: MCPEvent) -> None:
        await self.export_batch([event])

    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        for event in event_batch:
            status = event.status.value if hasattr(event.status, "value") else str(event.status)
            self.counter.labels(tool_name=event.tool_name, status=status).inc()
            self.histogram.labels(tool_name=event.tool_name).observe(event.delta)

    async def close(self) -> None:
        self._server_started = False

