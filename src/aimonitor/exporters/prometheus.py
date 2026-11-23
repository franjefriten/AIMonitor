import asyncio
from collections.abc import Sequence
from threading import Thread
from typing import Any, List, Optional
from urllib.parse import urlparse
from wsgiref.simple_server import WSGIServer

import httpx

from aimonitor.configs.config import settings
from aimonitor.core.event import BaseSignal, MetricEvent, MetricType, SignalType
from aimonitor.exporters.base import BaseExporter
from aimonitor.utils.logger import logger
from aimonitor.core.exceptions import OptionalDependencyMissingError

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server
except ImportError as exc:  # pragma: no cover - import guard
    logger.warning("prometheus_client is not installed. PrometheusExporter will not work.")
    CollectorRegistry = None
    Counter = None
    Gauge = None
    Histogram = None
    start_http_server = None
    _PROMETHEUS_IMPORT_ERROR = exc
else:
    _PROMETHEUS_IMPORT_ERROR = None

class PrometheusExporter(BaseExporter):
    """Expose MetricEvent signals as Prometheus metrics for Prometheus to scrape.

    Metric names are registered with one metric type and one label-name set.
    Counter values increment, gauge values replace the current value, and
    histogram values are observed. Non-metric signals are ignored.
    """

    SUPPORTED_SIGNALS = {SignalType.METRIC}

    def __init__(self, address: str = "http://0.0.0.0:9000"): # type: ignore
        super().__init__()
        if (
            CollectorRegistry is None
            or Counter is None
            or Gauge is None
            or Histogram is None
            or start_http_server is None
        ):
            self._server_started = False
            raise OptionalDependencyMissingError(
                "prometheus_client is required for PrometheusExporter. "
                "Install it with pip install .[prometheus] or uv sync --extra prometheus"
            )
        self.address = address
        self.registry = CollectorRegistry(auto_describe=True)
        self._server_started = False
        self._http_server: WSGIServer
        self._server_thread: Thread
        self._metrics: dict[str, tuple[MetricType, tuple[str, ...], Any]] = {}

        parsed_url = urlparse(self.address)
        self.port = parsed_url.port or 9000
        self.addr = parsed_url.hostname or "0.0.0.0"

    async def connect(self) -> None:
        if self._server_started:
            if self._server_thread.is_alive():
                return
            await self.close()
        start_server = start_http_server
        if start_server is None:
            raise OptionalDependencyMissingError(
                "prometheus_client is required for PrometheusExporter. "
                "Install it with pip install .[prometheus] or uv sync --extra prometheus"
            ) from _PROMETHEUS_IMPORT_ERROR
        self._http_server, self._server_thread = start_server(
            port=self.port,
            addr=self.addr,
            registry=self.registry,
        )
        self._server_started = True

    def _metrics_url(self) -> str:
        host = self.addr
        if host == "0.0.0.0":
            host = "127.0.0.1"
        elif host == "::":
            host = "::1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}/metrics"

    def _metric_for_event(self, event: MetricEvent) -> Any:
        label_names = tuple(sorted(event.labels))
        existing_metric = self._metrics.get(event.name)
        if existing_metric is not None:
            existing_type, existing_label_names, metric = existing_metric
            if existing_type != event.metric_type:
                raise ValueError(
                    f"Metric '{event.name}' was already registered as "
                    f"{existing_type.value}, not {event.metric_type.value}"
                )
            if existing_label_names != label_names:
                raise ValueError(
                    f"Metric '{event.name}' was already registered with labels "
                    f"{existing_label_names}, not {label_names}"
                )
            return metric

        metric_classes = {
            MetricType.COUNTER: Counter,
            MetricType.GAUGE: Gauge,
            MetricType.HISTOGRAM: Histogram,
        }
        metric_class = metric_classes.get(event.metric_type)
        if metric_class is None:
            raise ValueError(f"Unsupported Prometheus metric type: {event.metric_type}")

        metric = metric_class(
            name=event.name,
            documentation=f"AIMonitor metric '{event.name}'",
            labelnames=label_names,
            registry=self.registry,
        )
        self._metrics[event.name] = (event.metric_type, label_names, metric)
        return metric

    async def export(self, event_batch: Sequence[BaseSignal]) -> None:
        for event in event_batch:
            if event.event_type not in self.SUPPORTED_SIGNALS:
                logger.warning(
                    "Event type '%s' with id: '%s' is not supported by PrometheusExporter. Skipping export for event.",
                    event.event_type,
                    event.id
                )
                continue

            if not isinstance(event, MetricEvent):
                raise TypeError(
                    "PrometheusExporter requires MetricEvent instances for metric signals"
                )

            if event.metric_type == MetricType.COUNTER and event.value < 0:
                raise ValueError(f"Counter metric '{event.name}' cannot be incremented by a negative value")

            metric = self._metric_for_event(event)
            sample = metric.labels(**event.labels) if event.labels else metric
            if event.metric_type == MetricType.COUNTER:
                sample.inc(event.value)
            elif event.metric_type == MetricType.GAUGE:
                sample.set(event.value)
            elif event.metric_type == MetricType.HISTOGRAM:
                sample.observe(event.value)

    async def close(self) -> None:
        if not self._server_started:
            return

        http_server = self._http_server
        server_thread = self._server_thread
        if server_thread.is_alive():
            await asyncio.to_thread(http_server.shutdown)
        await asyncio.to_thread(http_server.server_close)
        await asyncio.to_thread(server_thread.join, 5.0)
        if server_thread.is_alive():
            raise RuntimeError("Prometheus metrics server did not stop")
        self._server_started = False

    async def healthcheck(self) -> bool:
        """
        Health check for the PrometheusExporter. This exporter is considered healthy if it can start the HTTP server and expose metrics.
        """
        if not self._server_started or not self._server_thread.is_alive():
            return False
        server_thread = self._server_thread
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(self._metrics_url())
        except httpx.HTTPError as exc:
            logger.error("Health check failed for PrometheusExporter: %s", exc)
            return False
        return response.status_code == 200 and server_thread.is_alive()

    async def describe(self) -> dict[str, object]:
        """
        Return diagnostic details for the PrometheusExporter.
        """
        server_is_healthy = await self.healthcheck()
        return {
            "status": "healthy" if server_is_healthy else "unhealthy",
            "message": "PrometheusExporter is operational." if server_is_healthy else "PrometheusExporter is not operational.",
            "address": self.address,
            "port": self.port,
            "registry": str(self.registry),
        }

    async def recover(self) -> bool:
        """
        Attempt to recover the PrometheusExporter. Recovery is considered successful if the HTTP server can be started.
        """
        try:
            if await self.healthcheck():
                return True
            if self._server_started:
                await self.close()
            await self.connect()
            return True
        except Exception as e:
            logger.error(f"Recovery failed for PrometheusExporter: {e}")
            return False
