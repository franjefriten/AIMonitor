from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict
from uuid import uuid4
import socket
from configs.config import get_settings
from datetime import datetime

settings = get_settings()

class Status(str, Enum):
    """
    Status enum for tool success
    List of possible statuses:
    - success: the tool executed successfully.
    - error: The tool returned an error field, but executed successfully.
    - failure: the tool failed to execute successfully.
    - warning: the tool executed with warnings.
    """
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"
    WARNING = "warning"


class LogStatus(str, Enum):
    """
    Status for logs. List of possible log statuses:
    - critical: a critical error occurred.
    - error: an error occurred.
    - warning: a warning was generated.
    - info: informational message.
    - debug: debug message.
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
    """
    Type of observability signal emitted by the public API.
    List of possible signal types:
    - event: a generic event signal.
    - log: a log signal.
    - metric: a metric signal.
    - span: a tracing span signal.
    - inner: an internal SDK signal related to the health of the SDK, not meant for user consumption.
    """
    EVENT = "event"
    LOG = "log"
    METRIC = "metric"
    SPAN = "span"
    _INNER = "inner"  # Internal SDK signal, not meant for user consumption


class HealthStatus(str, Enum):
    """
    Health status of the exporters of the SDK, but not the SDK itself.
    List of possible health statuses:
    - healthy: the last health check was successful.
    - starting: the exporter was registered but has not yet completed its first health check.
    - recovering: last health check failed but the exporter is attempting to recover.
    - down: the exporter is not healthy and not attempting to recover.
    - stopped: the exporter has been stopped manually and is no longer operational.
    - unused: the exporter is not being used.
    """
    HEALTHY = "healthy" # the last health check was successful.
    STARTING = "starting" # the exporter was registered but has not yet completed its first health check.
    RECOVERING = "recovering" # last health check failed but the exporter is attempting to recover.
    DOWN = "down" # the exporter is not healthy and not attempting to recover.
    FAILURE = "failure" # the exporter failed while exporting a batch.
    STOPPED = "stopped" # the exporter has been stopped and is not operational.
    UNUSED = "unused" # the exporter is not being used.
    # NOTE: given that the user can create any custom health statuses, this list may not be exhaustive. To do so, we'd have to account for every class that inherits from BaseExporter


class SDKHealthStatus(str, Enum):
    """
    Health status of the SDK itself.
    List of possible health statuses:
    - healthy: the SDK is fully operational.
    - starting: the SDK is initializing.
    - degraded: the SDK is operational but experiencing issues.
    - down: the SDK is not operational.
    """
    HEALTHY = "healthy"
    STARTING = "starting"
    DEGRADED = "degraded"
    DOWN = "down"
    EMPTY = "empty"


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
    message: str = Field(default="", description="Message describing the health check status.")


class HealthCheckSnapshot(InnerEvent):
    """
    This event is used to track the health of exporters, not the SDK itself. It is not meant to be used by the user.
    """
    exporter_name: str = Field(default="", description="The exporter associated with this health snapshot.")
    status: HealthStatus = Field(default=HealthStatus.STARTING, description="The status of the exporter health check.")
    last_check_started_at: datetime | None = Field(default=None, description="The timestamp when the last health check started.")
    last_check_finished_at: datetime | None = Field(default=None, description="The timestamp when the last health check finished.")
    last_success_at: datetime | None = Field(default=None, description="The timestamp when the last successful health check occurred.")
    last_failure_at: datetime | None = Field(default=None, description="The timestamp when the last failed health check occurred.")
    consecutive_failures: int = Field(default=0, description="The number of consecutive failed health checks.")
    consecutive_successes: int = Field(default=0, description="The number of consecutive successful health checks.")

class SDKHealthSnapshot(InnerEvent):
    status: SDKHealthStatus = Field(default=SDKHealthStatus.HEALTHY, description="The health status of the SDK.")
    checked_at: datetime | None = Field(default=None, description="The timestamp when the SDK health was last checked.")
    summary: dict[str, int] = Field(default_factory=dict, description="A summary of the SDK health status.")
    exporters: dict[str, HealthCheckSnapshot] = Field(default_factory=dict, description="The health status of individual exporters.")


# Backwards-compatible names for callers using the original event terminology.
HealthCheckEvent = HealthCheckSnapshot
SDKHealthCheckEvent = SDKHealthSnapshot