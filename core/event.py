from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict
from uuid import uuid4


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


class BaseSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for the signal.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="The timestamp of when the signal was generated.")
    event_type: SignalType
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata associated with the signal.")

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
