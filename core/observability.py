from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import uuid4

from core.event import MCPEvent, SignalType, LogEvent, MetricEvent, Status, LogStatus, BaseSignal, MetricType, SpanEvent
from core.trace import Trace
from core.registry import registry
from utils.logger import logger
from configs.config import get_settings
from contextlib import asynccontextmanager, contextmanager
from utils.context import _trace_context

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
        self.register_error(event, error) if error and status == Status.ERROR else None
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
        self.register_error(event) if event.labels["status"] == Status.ERROR else None
        await registry.dispatch(events=[event])
        logger.info(f"Metric event with id '{event.id}' dispatched")
        return event

    @asynccontextmanager
    async def aspan(self, operation_name: str, metadata: Optional[dict] = None, capture_exceptions: bool = False):
        """Asynchronous context manager for creating a span event."""

        if not settings.track_events:
            logger.error(
                """Spans are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            yield
            return
        
        trace = _trace_context.get()
        root_span_event = trace.start_span(operation_name=operation_name, metadata=metadata)

        token = _trace_context.set(trace)
        start_time = datetime.now(UTC)
        try:
            yield root_span_event
        except Exception as e:
            logger.error(f"Exception occurred during span '{operation_name}': {e}")
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            root_span_event.delta = delta
            root_span_event.status = Status.FAILURE
            if not capture_exceptions:
                raise e
        finally:
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            root_span_event.delta = delta
            if root_span_event.status not in {Status.FAILURE, Status.ERROR}:
                root_span_event.status = Status.SUCCESS

            await registry.dispatch(events=[root_span_event])
            logger.info(f"Span event with id '{root_span_event.id}' dispatched")
            _trace_context.reset(token)

    @contextmanager
    def span(self, operation_name: str, metadata: Optional[dict] = None, capture_exceptions: bool = False):
        """Synchronous context manager for creating a span event."""
        if not settings.track_events:
            logger.error(
                """Spans are not being tracked by aimonitor due to environment configuration. 
                Check env vars or .yaml/.json config file"""
            )
            yield
            return
        
        trace = _trace_context.get()
        root_span_event = trace.start_span(operation_name=operation_name, metadata=metadata)

        token = _trace_context.set(trace)
        start_time = datetime.now(UTC)
        try:
            yield root_span_event
        except Exception as e:
            logger.error(f"Exception occurred during span '{operation_name}': {e}")
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            root_span_event.delta = delta
            root_span_event.status = Status.FAILURE
            if not capture_exceptions:
                raise e
        finally:
            end_time = datetime.now(UTC)
            delta = (end_time - start_time).total_seconds()
            root_span_event.delta = delta
            if root_span_event.status not in {Status.FAILURE, Status.ERROR}:
                root_span_event.status = Status.SUCCESS

            registry.sync_dispatch(events=[root_span_event])
            logger.info(f"Span event with id '{root_span_event.id}' dispatched")
            _trace_context.reset(token)

    
    def get_current_trace(self) -> Trace:
        """Returns the current trace object from the context variable."""
        return _trace_context.get()
    
    def get_current_span(self) -> SpanEvent | None:
        """Returns the current active span event from the trace, if any."""
        trace = _trace_context.get()
        return trace.current_span() if trace else None
    
    def start_span(self, operation_name: str, metadata: Optional[dict] = None) -> SpanEvent:
        """Starts a new span event and returns it. Use this when you want to manage the span manually."""
        trace = _trace_context.get()
        if not trace:
            trace = Trace(func_name=operation_name, metadata=metadata or {})
            _trace_context.set(trace)
        return trace.start_span(operation_name=operation_name, metadata=metadata)
    
    def end_span(self, span_id: str) -> None:
        """Ends the specified span event."""
        trace = _trace_context.get()
        if trace:
            trace.end_span(span_id=span_id)

    def get_parent_span(self) -> SpanEvent | None:
        """Returns the parent span of the current active span, if any."""
        trace = _trace_context.get()
        current_span = trace.current_span() if trace else None
        if current_span and current_span.parent_id:
            return trace.spans.get(current_span.parent_id)
        return None
    
    def register_error(self, event: MCPEvent, msg: str) -> None:
        """
        When tool execution does not fail, but returns an 'error' or unwanted result, we can register it as an error in the span event.
        This method is meant to be used inside a decorator that tracks tool. an event must be parsed to this method, along with the error message. The method will then register the error in the current span event, if any.
        """
        logger.error(f"Error found in tool execution: {msg}. Event ID: {event.id}", exc_info=True)
        event.status = Status.ERROR
        event.error = msg
        trace = self.get_current_trace() 
        current_span = trace.current_span() if trace else None
        if current_span:
            current_span.status = Status.ERROR
            current_span.error = msg
        return event


monitor = ObservabilityAPI()