from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Optional

from core.event import MCPEvent, SignalType, LogEvent, MetricEvent, Status, LogStatus, BaseSignal, MetricType
from core.registry import registry
from utils.logger import logger
from configs.config import get_settings

settings = get_settings()


class ObservabilityAPI:
    """Public entry point for emitting structured observability signals."""

    async def emit_event(self, event: BaseSignal) -> None:
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


monitor = ObservabilityAPI()
