import os
import json
from typing import Any, List, Optional

from configs.config import get_settings
from core.event import MCPEvent
from exporters.base import BaseExporter
from utils.logger import logger


class OpenTelemetryExporter(BaseExporter):
    """
    Exporter that converts monitored MCP events into OpenTelemetry spans.

    This exporter is intentionally separated from telemetry/api.py:
    - telemetry/api.py handles AIMonitor internal observability.
    - This class handles user-facing export of monitored MCP events.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        service_name: Optional[str] = None,
        span_prefix: Optional[str] = None,
    ):
        settings = get_settings()
        self.enabled = settings.otel_mcp_exporter_enabled if enabled is None else bool(enabled)
        self.service_name = service_name or settings.otel_mcp_service_name
        self.span_prefix = span_prefix or settings.otel_mcp_span_prefix

        self.tracer = None
        if self.enabled:
            self._initialize_otel()

    def _initialize_otel(self) -> None:
        try:
            if os.getenv("OTEL_SDK_DISABLED", "false").strip().lower() == "true":
                self.enabled = False
                logger.debug("OTEL_SDK_DISABLED=true detected. OpenTelemetry MCP exporter disabled.")
                return

            from opentelemetry import trace

            self.tracer = trace.get_tracer(self.service_name)
            logger.debug("OpenTelemetry MCP exporter initialized for service %s", self.service_name)
        except ImportError:
            self.enabled = False
            logger.warning(
                "OpenTelemetry is not installed. MCP OpenTelemetry exporter disabled. "
                "Install with pip install .[opentelemetry] or uv sync --extra opentelemetry"
            )
        except Exception as exc:
            self.enabled = False
            logger.warning("Unexpected error initializing OpenTelemetry MCP exporter: %s", exc)

    async def export(self, event: MCPEvent) -> None:
        if not self.enabled or not self.tracer:
            return

        self._export_event_to_span(event)

    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        if not self.enabled or not self.tracer:
            return

        for event in event_batch:
            self._export_event_to_span(event)

    def _export_event_to_span(self, event: MCPEvent) -> None:
        span_name = f"{self.span_prefix}.{event.tool_name}"

        try:
            with self.tracer.start_as_current_span(span_name) as span:
                status = event.status.value if hasattr(event.status, "value") else str(event.status)

                span.set_attribute("mcp.tool_name", event.tool_name)
                span.set_attribute("mcp.status", status)
                span.set_attribute("mcp.delta", float(event.delta))

                if event.error:
                    span.set_attribute("mcp.error", str(event.error))

                if event.args:
                    span.set_attribute("mcp.args", self._to_json_attribute(event.args))

                if event.metadata not in (None, ""):
                    span.set_attribute("mcp.metadata", self._to_json_attribute(event.metadata))

                if event.result is not None:
                    span.set_attribute("mcp.result", self._to_json_attribute(event.result))
        except Exception as exc:
            logger.error("Failed to export MCP event '%s' to OpenTelemetry span: %s", event.tool_name, exc)

    @staticmethod
    def _to_json_attribute(value: Any) -> str:
        try:
            return json.dumps(value, default=str, ensure_ascii=True)
        except Exception:
            return str(value)
