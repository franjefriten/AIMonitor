from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import uuid4

from core.event import MCPEvent, SignalType, LogEvent, MetricEvent, Status, LogStatus, BaseSignal, MetricType, SpanEvent
from core.registry import registry
from utils.logger import logger
from configs.config import get_settings
from utils.context import _span_context
from pydantic import Field

from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict
from uuid import uuid4
import socket
from contextvars import ContextVar


class Trace:
    """
    Groups span events within the same object. Used mainly as internal logic
    """
    def __init__(
            self, 
            func_name: Optional[str] = None, 
            metadata: Optional[Dict[str, Any]] = None
        ):
        self.trace_id = f"{func_name}_{uuid4()}"
        self.spans: dict[str, SpanEvent] = {}
        self.active_span_id: str | None = None
        self.root_span_id: str = None
        self.metadata = metadata or {}

    def start_span(self, operation_name: str, metadata: Optional[Dict[str, Any]] = None) -> SpanEvent:
        span_id = str(uuid4())
        parent_id = self.active_span_id
        self.active_span_id = span_id
        metadata = metadata or {}
        span = SpanEvent(
            trace_id=self.trace_id,
            parent_id=parent_id,
            span_id=span_id,
            root_span_id=self.root_span_id,
            operation_name=operation_name,
            metadata=metadata or {},
            timestamp=datetime.now(UTC)
        )
        self.spans[span_id] = span
        if self.root_span_id is None:
            self.root_span_id = span_id
        return span
    

