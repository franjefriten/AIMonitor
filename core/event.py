from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict
from uuid import uuid4
import socket
from configs.config import get_settings

settings = get_settings()

class Status(str, Enum):
    """
    Status enum for tool success
    """
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"
    WARNING = "warning"


class LogStatus(str, Enum):
    """
    Status para logs
    """
    CRITICAL = "critical" 
    ERROR = "error",
    WARNING = "warning",
    INFO = "info",
    DEBUG = "debug"


class MetricType(str, Enum):
    """
    Allowed types of metrics
    """
    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"


class SignalType(str, Enum):
    """Type of observability signal emitted by the public API."""
    EVENT = "event"
    LOG = "log"
    METRIC = "metric"
    SPAN = "span"
    _INNER = "inner"  # Internal SDK signal, not meant for user consumption


class HealthStatus(str, Enum):
    """Health status of the SDK or its components."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

class BaseSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for the signal.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="The timestamp of when the signal was generated.")
    event_type: SignalType
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata associated with the signal.")
    environment: str = Field(default=settings.env_code, description="The environment in which the signal was generated, e.g., 'production', 'staging', etc.")
    hostname: str = Field(default_factory=lambda: socket.gethostname(), description="The hostname of the machine where the signal was generated.")
    version: str = Field(default="", description="The version of the application or service generating the signal.")


    @classmethod
    def as_sqlite_table(cls, table_name: str = "signal") -> str:
        vars = cls.model_fields
        columns = ["    id TEXT PRIMARY KEY"]
        for var_name, var_metadata in vars.items():
            if var_name == "id":
                continue
            var_type = var_metadata.annotation
            sql_type = _MAP_SQLITE_TYPING.get(var_type, "TEXT")
            columns.append(f"    {var_name} {sql_type}")
        query = ",\n".join(columns)
        return f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
{query}
            );
        """

_MAP_SQLITE_TYPING = {
    str: "TEXT",
    float: "REAL",
    datetime: "NUMERIC",
    Status: f"TEXT CHECK (status IN ({'\''+'\',\''.join(Status._member_map_.values())+'\''}))",
    Any: "BLOB",
    dict: "BLOB"
}

class MCPEvent(BaseSignal):
    """
    Basic MCPEvent class that all events inherit from.
    """
    event_type: SignalType = Field(default=SignalType.EVENT, description="The kind of signal being emitted.")
    tool_name: str = Field(default="", description="The name of the tool that generated the event.")
    args: dict = Field(default_factory=dict, description="The arguments passed to the tool that generated the event.")
    delta: float = Field(default=0.0, description="The execution time of the event.")
    status: Status = Field(default=Status.SUCCESS, description="The status of the event.")
    error: str = Field(default="", description="The error message of the event if any.")
    result: Any = Field(default=None, description="The result of the event.")
    event_type: SignalType = Field(default=SignalType.EVENT, description="The kind of signal being emitted.")


class LogEvent(BaseSignal):
    event_type: SignalType = SignalType.LOG
    message: str
    level: LogStatus = LogStatus.INFO
    source: str


class MetricEvent(BaseSignal):
    event_type: SignalType = SignalType.METRIC
    name: str
    value: float | int
    metric_type: MetricType = MetricType.GAUGE
    labels: Dict[str, str] = Field(default_factory=dict)


class SpanEvent(BaseSignal):
    """
    This event is used to mark inner call tools for better atomic tracing.
    Used as a context manager to wrap inner calls and mark them as spans.
    """
    event_type: SignalType = Field(default=SignalType.SPAN, description="The kind of signal being emitted.")
    parent_id: str | None = Field(default=None, description="The ID of the parent span, if any. Used for nested span events. None if first event")
    trace_id: str = Field(default_factory=lambda: str(uuid4()), description="The ID of the trace that this span belongs to, base parent of a tool call trace. Used for distributed tracing.")
    span_id: str = Field(default="", description="The ID of the span. Used for distributed tracing. Different from inherited id of the BaseSignal, which is unique for each signal. This is used to identify the individual span in a distributed tracing system by context manager.")
    operation_name: str = Field(default="", description="Name of the operation being traced.")
    status: Status = Field(default=Status.SUCCESS, description="The status of the span.")
    error: str = Field(default="", description="Error message in a tool executed found within a span if any.")
    delta: float = Field(default=0.0, description="The execution time of the span.")

    def register_error(self, msg: str) -> None:
        """
        When tool execution does not fail, but returns an 'error' or unwanted result, we can register it as an error in the span event.
        This method is meant to be used inside a span context manager. Gets the current span event from the context and registers the error in it.
        """
        self.status = Status.ERROR
        self.error = msg


class InnerEvent(BaseSignal):
    """
    This event is used for aimonitor self tracking, to track inner events of the SDK itself. It is not meant to be used by the user.
    """
    event_type: SignalType = Field(default=SignalType._INNER, description="The kind of signal being emitted.")
    delta: float = Field(default=0.0, description="The execution time of the inner event.")
    status: Status = Field(default=Status.SUCCESS, description="The status of the inner event.")
    error: str = Field(default="", description="Error message in the inner event if any.")


class HealthCheckEvent(BaseSignal):
    """
    This event is used to track the health of the SDK and its exporters. It is not meant to be used by the user.
    """
    event_type: SignalType = Field(default=SignalType._INNER, description="The kind of signal being emitted.")
    status: HealthStatus = Field(default=HealthStatus.HEALTHY, description="The status of the health check.")
    message: str = Field(default="", description="Message describing the health check status.")
