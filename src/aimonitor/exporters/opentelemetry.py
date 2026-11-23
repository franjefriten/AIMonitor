import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from sys import version_info
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from aimonitor.core.event import (
    BaseSignal,
    LogEvent,
    LogStatus,
    MCPEvent,
    MetricEvent,
    MetricType,
    SignalType,
    SpanEvent,
    Status,
)
from aimonitor.core.exceptions import (
    ExporterConfigurationError,
    OpenTelemetryCompatibilityError,
    OptionalDependencyMissingError,
)
from aimonitor.exporters.base import BaseExporter
from aimonitor.utils.logger import logger


_PENDING_SPAN_TTL_SECONDS = 300
_MAX_PENDING_SPANS = 1000
_MAX_TRACE_STATES = 1000


@dataclass
class _TraceState:
    root_context: Any = None
    span_contexts: dict[str, Any] = field(default_factory=dict)
    pending_spans: list[tuple[SpanEvent, float]] = field(default_factory=list)
    last_updated: float = field(default_factory=time.monotonic)


class OpenTelemetryExporter(BaseExporter):
    """Convert AIMonitor signals to OpenTelemetry and export them over OTLP/HTTP."""

    SUPPORTED_SIGNALS = {
        SignalType.EVENT,
        SignalType.SPAN,
        SignalType.METRIC,
        SignalType.LOG,
    }

    def __init__(
        self,
        enabled: bool = False,
        service_name: str = "aimonitor-mcp",
        span_prefix: str = "mcp.tool",
        endpoint: str = "http://localhost:4318",
        traces_enabled: bool = False,
        metrics_enabled: bool = False,
        logs_enabled: bool = False,
        metrics_export_interval_ms: int = 60_000,
    ):
        self.enabled = bool(enabled)
        self.service_name = service_name
        self.span_prefix = span_prefix
        self.endpoint = endpoint
        self.traces_enabled = bool(traces_enabled)
        self.metrics_enabled = bool(metrics_enabled)
        self.logs_enabled = bool(logs_enabled)
        self.metrics_export_interval_ms = metrics_export_interval_ms

        self.tracer = None
        self.meter = None
        self.otel_logger = None
        self._tracer_provider = None
        self._meter_provider = None
        self._logger_provider = None
        self._log_record_class = None
        self._connected = False
        self._cleanup_task: asyncio.Task | None = None
        self._metric_instruments: dict[tuple[str, MetricType, str], Any] = {}
        self._traces: dict[str, _TraceState] = {}
        self._pending_span_count = 0

    async def connect(self) -> None:
        if self._connected:
            return
        if not self.enabled:
            self._connected = True
            return

        if os.getenv("OTEL_SDK_DISABLED", "false").strip().lower() == "true":
            logger.warning("OTEL_SDK_DISABLED=true; OpenTelemetry exporter is disabled.")
            self.enabled = False
            self._connected = True
            return

        active_signals = self.traces_enabled or self.metrics_enabled or self.logs_enabled
        if not active_signals:
            logger.warning(
                "OpenTelemetry exporter is enabled, but traces, metrics, and logs are all disabled."
            )
            self._connected = True
            return

        parsed_endpoint = urlparse(self.endpoint)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.netloc
            or parsed_endpoint.query
            or parsed_endpoint.fragment
        ):
            raise ExporterConfigurationError(
                f"Invalid OTLP/HTTP endpoint: {self.endpoint!r}"
            )
        if self.metrics_enabled and self.metrics_export_interval_ms <= 0:
            raise ExporterConfigurationError(
                "metrics_export_interval_ms must be greater than zero."
            )

        if version_info >= (3, 14):
            try:
                sdk_version = version("opentelemetry-sdk")
            except PackageNotFoundError:
                pass
            else:
                release = re.match(r"^(\d+)\.(\d+)\.(\d+)", sdk_version)
                if release is None or tuple(map(int, release.groups())) < (1, 35, 0):
                    raise OpenTelemetryCompatibilityError(sdk_version)

        try:
            from opentelemetry import context as otel_context
            from opentelemetry._logs import SeverityNumber
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk import _logs as sdk_logs
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.trace import (
                NonRecordingSpan,
                Status as OTelStatus,
                StatusCode,
                set_span_in_context,
            )
        except ImportError as exc:
            raise OptionalDependencyMissingError(
                "opentelemetry-exporter-otlp-proto-http"
            ) from exc

        self._otel_context = otel_context
        self._non_recording_span = NonRecordingSpan
        self._set_span_in_context = set_span_in_context
        self._otel_status = OTelStatus
        self._status_code = StatusCode
        self._severity_number = SeverityNumber
        self._log_record_class = getattr(sdk_logs, "LogRecord", None)

        resource = Resource.create({"service.name": self.service_name})
        base_endpoint = self.endpoint.rstrip("/")
        try:
            if self.traces_enabled:
                self._tracer_provider = TracerProvider(resource=resource)
                self._tracer_provider.add_span_processor(
                    BatchSpanProcessor(
                        OTLPSpanExporter(endpoint=f"{base_endpoint}/v1/traces")
                    )
                )
                self.tracer = self._tracer_provider.get_tracer("aimonitor")

            if self.metrics_enabled:
                metric_reader = PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=f"{base_endpoint}/v1/metrics"),
                    export_interval_millis=self.metrics_export_interval_ms,
                )
                self._meter_provider = MeterProvider(
                    resource=resource,
                    metric_readers=[metric_reader],
                )
                self.meter = self._meter_provider.get_meter("aimonitor")

            if self.logs_enabled:
                self._logger_provider = LoggerProvider(resource=resource)
                self._logger_provider.add_log_record_processor(
                    BatchLogRecordProcessor(
                        OTLPLogExporter(endpoint=f"{base_endpoint}/v1/logs")
                    )
                )
                self.otel_logger = self._logger_provider.get_logger("aimonitor")
        except Exception:
            try:
                await self._shutdown_providers()
            except Exception as cleanup_error:
                logger.error(
                    "Failed to clean up partially initialized OpenTelemetry providers: %s",
                    cleanup_error,
                )
            raise

        self._connected = True
        if self.traces_enabled:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_traces())
        logger.debug("OpenTelemetry exporter connected for service %s", self.service_name)

    async def export_batch(self, event_batch: Sequence[BaseSignal]) -> None:
        if not self.enabled:
            return
        if not self._connected:
            await self.connect()

        self._prune_expired_traces()
        for event in event_batch:
            if event.event_type == SignalType._INNER:
                continue
            if isinstance(event, MCPEvent) and self.traces_enabled:
                self._export_root_span(event)
            elif isinstance(event, SpanEvent) and self.traces_enabled:
                self._export_nested_span(event)
            elif isinstance(event, MetricEvent) and self.metrics_enabled:
                self._record_metric(event)
            elif isinstance(event, LogEvent) and self.logs_enabled:
                self._record_log(event)

    def _export_root_span(self, event: MCPEvent) -> None:
        trace_id = event.trace_id
        state = self._trace_state(trace_id)
        tool_name = event.tool_name or "healthcheck"
        span_name = f"{self.span_prefix}.{tool_name}"
        end_time = self._timestamp_ns(event.timestamp)
        delta = float(event.delta)
        start_time = end_time - int(delta * 1_000_000_000)
        try:
            span = self.tracer.start_span(
                span_name,
                context=self._otel_context.Context(),
                start_time=start_time,
            )
            try:
                self._set_span_attributes(span, event.status, delta, event.error)
                span.set_attribute("mcp.tool_name", tool_name)
            finally:
                span.end(end_time=end_time)
            state.root_context = span.get_span_context()
            state.last_updated = time.monotonic()
            self._flush_pending_spans(trace_id, state)
        except Exception:
            logger.exception(
                "Failed to export MCP event '%s' to OpenTelemetry.", tool_name
            )
            raise

    def _export_nested_span(self, event: SpanEvent) -> None:
        state = self._trace_state(event.trace_id)
        state.last_updated = time.monotonic()
        parent_context = (
            state.root_context
            if event.parent_id is None
            else state.span_contexts.get(event.parent_id)
        )
        if parent_context is None:
            self._queue_pending_span(state, event)
            return
        self._emit_nested_span(event, state, parent_context)
        self._flush_pending_spans(event.trace_id, state)

    def _emit_nested_span(
        self,
        event: SpanEvent,
        state: _TraceState,
        parent_context: Any,
    ) -> None:
        start_time = self._timestamp_ns(event.timestamp)
        end_time = start_time + int(float(event.delta) * 1_000_000_000)
        parent = self._non_recording_span(parent_context)
        context = self._set_span_in_context(parent, self._otel_context.Context())
        span = self.tracer.start_span(
            event.operation_name or "mcp.span",
            context=context,
            start_time=start_time,
        )
        try:
            self._set_span_attributes(span, event.status, float(event.delta), event.error)
        finally:
            span.end(end_time=end_time)
        state.span_contexts[event.span_id] = span.get_span_context()
        state.last_updated = time.monotonic()

    def _flush_pending_spans(self, trace_id: str, state: _TraceState) -> None:
        if state.root_context is None:
            return
        pending = state.pending_spans
        state.pending_spans = []
        self._pending_span_count -= len(pending)

        while pending:
            remaining: list[tuple[SpanEvent, float]] = []
            progressed = False
            for event, queued_at in pending:
                parent_context = (
                    state.root_context
                    if event.parent_id is None
                    else state.span_contexts.get(event.parent_id)
                )
                if parent_context is None:
                    remaining.append((event, queued_at))
                    continue
                self._emit_nested_span(event, state, parent_context)
                progressed = True
            if not progressed:
                state.pending_spans.extend(remaining)
                self._pending_span_count += len(remaining)
                return
            pending = remaining

        logger.debug("Exported pending OpenTelemetry spans for trace %s", trace_id)

    def _queue_pending_span(self, state: _TraceState, event: SpanEvent) -> None:
        self._enforce_pending_span_limit()
        state.pending_spans.append((event, time.monotonic()))
        self._pending_span_count += 1

    def _enforce_pending_span_limit(self) -> None:
        while self._pending_span_count >= _MAX_PENDING_SPANS:
            oldest_state = None
            oldest_index = -1
            oldest_time = float("inf")
            for state in self._traces.values():
                for index, (_, queued_at) in enumerate(state.pending_spans):
                    if queued_at < oldest_time:
                        oldest_state = state
                        oldest_index = index
                        oldest_time = queued_at
            if oldest_state is None:
                return
            oldest_state.pending_spans.pop(oldest_index)
            self._pending_span_count -= 1
            logger.warning(
                "Discarded the oldest pending OpenTelemetry span after reaching the %d-span limit.",
                _MAX_PENDING_SPANS,
            )

    def _trace_state(self, trace_id: str) -> _TraceState:
        state = self._traces.get(trace_id)
        if state is not None:
            state.last_updated = time.monotonic()
            return state
        if len(self._traces) >= _MAX_TRACE_STATES:
            oldest_trace_id = min(
                self._traces,
                key=lambda key: self._traces[key].last_updated,
            )
            self._remove_trace(oldest_trace_id)
            logger.warning(
                "Discarded the oldest OpenTelemetry trace state after reaching the %d-trace limit.",
                _MAX_TRACE_STATES,
            )
        state = _TraceState(last_updated=time.monotonic())
        self._traces[trace_id] = state
        return state

    def _prune_expired_traces(self) -> None:
        now = time.monotonic()
        for trace_id, state in list(self._traces.items()):
            retained_spans = [
                (event, queued_at)
                for event, queued_at in state.pending_spans
                if now - queued_at < _PENDING_SPAN_TTL_SECONDS
            ]
            expired_count = len(state.pending_spans) - len(retained_spans)
            if expired_count:
                state.pending_spans = retained_spans
                self._pending_span_count -= expired_count
                logger.warning(
                    "Expired %d pending OpenTelemetry span(s) for trace %s.",
                    expired_count,
                    trace_id,
                )
            if (
                not state.pending_spans
                and now - state.last_updated >= _PENDING_SPAN_TTL_SECONDS
            ):
                self._remove_trace(trace_id)

    def _remove_trace(self, trace_id: str) -> None:
        state = self._traces.pop(trace_id, None)
        if state is not None:
            self._pending_span_count -= len(state.pending_spans)

    async def _cleanup_expired_traces(self) -> None:
        while True:
            await asyncio.sleep(30)
            self._prune_expired_traces()

    def _record_metric(self, event: MetricEvent) -> None:
        key = (event.name, event.metric_type, event.unit)
        instrument = self._metric_instruments.get(key)
        if instrument is None:
            if event.metric_type == MetricType.COUNTER:
                instrument = self.meter.create_counter(event.name, unit=event.unit)
            elif event.metric_type == MetricType.HISTOGRAM:
                instrument = self.meter.create_histogram(event.name, unit=event.unit)
            else:
                instrument = self.meter.create_gauge(event.name, unit=event.unit)
            self._metric_instruments[key] = instrument

        attributes = dict(event.labels)
        if event.environment:
            attributes["environment"] = event.environment
        if event.version:
            attributes["version"] = event.version

        if event.metric_type == MetricType.COUNTER:
            instrument.add(event.value, attributes=attributes)
        elif event.metric_type == MetricType.HISTOGRAM:
            instrument.record(event.value, attributes=attributes)
        else:
            instrument.set(event.value, attributes=attributes)

    def _record_log(self, event: LogEvent) -> None:
        severity_names = {
            LogStatus.CRITICAL: "FATAL",
            LogStatus.ERROR: "ERROR",
            LogStatus.WARNING: "WARN",
            LogStatus.INFO: "INFO",
            LogStatus.DEBUG: "DEBUG",
        }
        severity_name = severity_names[event.level]
        severity = getattr(self._severity_number, severity_name)
        attributes = {"source": event.source}
        if event.environment:
            attributes["environment"] = event.environment
        if event.version:
            attributes["version"] = event.version

        if self._log_record_class is not None:
            log_record = self._log_record_class(
                severity_number=severity,
                severity_text=event.level.value,
                body=event.message,
                resource=self._logger_provider.resource,
                attributes=attributes,
            )
            self.otel_logger.emit(log_record)
        else:
            self.otel_logger.emit(
                severity_number=severity,
                severity_text=event.level.value,
                body=event.message,
                attributes=attributes,
            )

    def _set_span_attributes(
        self,
        span: Any,
        status: Status,
        delta: float,
        error: str,
    ) -> None:
        status_value = status.value if isinstance(status, Status) else str(status)
        span.set_attribute("mcp.status", status_value)
        span.set_attribute("mcp.delta", delta)
        if error:
            span.set_attribute("mcp.error", error)
        if status in {Status.ERROR, Status.FAILURE}:
            span.set_status(
                self._otel_status(
                    self._status_code.ERROR,
                    description=error or status_value,
                )
            )

    @staticmethod
    def _timestamp_ns(timestamp: datetime) -> int:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return int(timestamp.timestamp() * 1_000_000_000)

    async def _shutdown_providers(self) -> None:
        providers = [
            provider
            for provider in (
                self._tracer_provider,
                self._meter_provider,
                self._logger_provider,
            )
            if provider is not None
        ]
        self._tracer_provider = None
        self._meter_provider = None
        self._logger_provider = None
        self._log_record_class = None
        self.tracer = None
        self.meter = None
        self.otel_logger = None
        self._metric_instruments.clear()

        errors: list[Exception] = []
        for provider in providers:
            try:
                await asyncio.to_thread(provider.force_flush)
            except Exception as exc:
                errors.append(exc)
            try:
                await asyncio.to_thread(provider.shutdown)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError(
                f"Failed to flush or shut down {len(errors)} OpenTelemetry provider operation(s)."
            ) from errors[0]

    async def close(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        try:
            await self._shutdown_providers()
        finally:
            self._traces.clear()
            self._pending_span_count = 0
            self._connected = False

    async def healthcheck(self) -> bool:
        if not self.enabled:
            logger.warning("OpenTelemetry exporter healthcheck skipped because it is disabled.")
            return False
        if not self._connected:
            return False
        return (
            (not self.traces_enabled or self._tracer_provider is not None)
            and (not self.metrics_enabled or self._meter_provider is not None)
            and (not self.logs_enabled or self._logger_provider is not None)
        )

    async def describe(self) -> dict[str, object]:
        healthy = await self.healthcheck()
        return {
            "status": "healthy" if healthy else "unhealthy",
            "message": (
                "OpenTelemetry exporter providers are ready locally."
                if healthy
                else "OpenTelemetry exporter is not ready."
            ),
            "service_name": self.service_name,
            "endpoint": self.endpoint,
            "enabled": self.enabled,
            "signals": {
                "traces": self.traces_enabled,
                "metrics": self.metrics_enabled,
                "logs": self.logs_enabled,
            },
            "connected": self._connected,
        }

    async def recover(self) -> bool:
        if not self.enabled:
            return False
        try:
            await self.close()
            await self.connect()
            return True
        except Exception as exc:
            logger.error("Recovery failed for OpenTelemetry exporter: %s", exc)
            return False
