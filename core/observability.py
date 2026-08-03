from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import uuid4

from core.event import MCPEvent, SignalType, LogEvent, MetricEvent, Status, LogStatus, BaseSignal, MetricType, SpanEvent
from core.registry import registry
from utils.logger import logger
from configs.config import get_settings
from contextlib import asynccontextmanager
from utils.context import _span_context

settings = get_settings()


class ObservabilityAPI:
    """Public entry point for emitting structured observability signals."""

    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(ObservabilityAPI, cls).__new__(cls)
        return cls.instance

    async def emit_event(self, event: BaseSignal) -> None:
        """
        Default method to emit a custom event created by the user. Needs to inherit from BaseSignal and have a SignalType defined.
        """

        if not settings.track_events:
            logger.error(
                """Events are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            return None
        await registry.dispatch(events=[event])
        logger.info(f"Event with id: '{event.id}' dispatched")

    async def emit_tool_execution_event(
        self,
        tool_name: str,
        args: dict | None = None,
        result: Any = None,
        status: str | Status = Status.SUCCESS,
        error: str = "",
        delta: float = 0.0,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ) -> BaseSignal:
        if not settings.track_events:
            logger.error(
                """Events are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            return None
        event = MCPEvent(
            tool_name=tool_name,
            args=args or {},
            result=result,
            status=status if isinstance(status, Status) else Status(status),
            error=error,
            delta=delta,
            timestamp=timestamp or datetime.now(UTC),
            metadata=metadata or {},
            event_type=SignalType.EVENT,
        )
        await registry.dispatch(events=[event])
        logger.info(f"Tool execution event with id: '{event.id}' dispatched")
        return event

    async def log(
        self,
        message: str,
        metadata: Optional[dict[Any, str]] = {},
        level: str | LogStatus = LogStatus.INFO,
        source: str = ""
    ) -> BaseSignal:
        if not settings.track_logs:
            logger.error(
                """Logs are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            return None
        event = LogEvent(
            message = message,
            metadata = metadata,
            level = level,
            source = source
        )
        await registry.dispatch(events=[event])
        logger.info(f"Log event with id: '{event.id}' dispatched")
        return event

    async def record_metric(
        self,
        name: str,
        value: float | int,
        metric_type: MetricType = MetricType.GAUGE,
        labels: dict | None = None,
        metadata: dict | None = None,
    ) -> BaseSignal:
        if not settings.track_metrics:
            logger.error(
                """Metrics are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            return None
        event = MetricEvent(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels or {},
            metadata=metadata or {},
        )
        await registry.dispatch(events=[event])
        logger.info(f"Metric event with id '{event.id}' dispatched")
        return event

    @asynccontextmanager
    async def span(self, operation_name: str, metadata: Optional[dict] = None):
        """Asynchronous context manager for creating a span event."""
        if not settings.track_events:
            logger.error(
                """Spans are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            yield
            return
        
        current = _span_context.get()
        parent_id = current.get("span_id") if current.get("span_id") else None # parent id is the span id of the current context, if it exists
        trace_id = current.get("trace_id") if current.get("trace_id") else str(uuid4())
        span_id = f"{operation_name}_{uuid4()}"  # Unique identifier for the child span

        span_event = SpanEvent(
            event_type=SignalType.SPAN,
            operation_name=operation_name,
            parent_id=parent_id,
            trace_id=trace_id,
            span_id=span_id,
            metadata=metadata or {},
        )

        token = {
            "parent_id": parent_id,
            "trace_id": trace_id,
            "span_id": span_id
        }
        token = _span_context.set(token)
        start_time = datetime.now(UTC)
        try:
            yield span_event
        except Exception as e:
            logger.error(f"Exception occurred during span '{operation_name}': {e}")
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            span_event.delta = delta
            span_event.status = Status.FAILURE
            raise e
        finally:
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            span_event.delta = delta
            span_event.status = Status.SUCCESS

            await registry.dispatch(events=[span_event])
            logger.info(f"Span event with id '{span_event.id}' dispatched")
            _span_context.reset(token)

    @asynccontextmanager
    def span(self, operation_name: str, metadata: Optional[dict] = None):
        """Synchronous context manager for creating a span event."""
        if not settings.track_events:
            logger.error(
                """Spans are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            yield
            return
        
        current = _span_context.get()
        parent_id = current.get("span_id") if current.get("span_id") else None # parent id is the span id of the current context, if it exists
        trace_id = current.get("trace_id") if current.get("trace_id") else str(uuid4())
        span_id = f"{operation_name}_{uuid4()}"  # Unique identifier for the child span

        span_event = SpanEvent(
            event_type=SignalType.SPAN,
            operation_name=operation_name,
            parent_id=parent_id,
            trace_id=trace_id,
            span_id=span_id,
            metadata=metadata or {},
        )

        token = {
            "parent_id": parent_id,
            "trace_id": trace_id,
            "span_id": span_id
        }
        token = _span_context.set(token)
        start_time = datetime.now(UTC)
        try:
            yield span_event
        except Exception as e:
            logger.error(f"Exception occurred during span '{operation_name}': {e}")
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            span_event.delta = delta
            span_event.status = Status.FAILURE
            raise e
        finally:
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            span_event.delta = delta
            span_event.status = Status.SUCCESS

            registry.sync_dispatch(events=[span_event])
            logger.info(f"Span event with id '{span_event.id}' dispatched")
            _span_context.reset(token)


monitor = ObservabilityAPI()
