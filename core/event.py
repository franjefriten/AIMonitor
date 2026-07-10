from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum

class Status(str, Enum):
    """
    Status enum for tool success
    """
    SUCCESS = "success"
    ERROR = "error"
    FAILURE = "failure"
    WARNING = "warning"

class MCPEvent(BaseModel):
    """
    Basic MCPEvent class that all events inherit from.
    """
    tool_name: str = Field(..., description="The name of the tool that generated the event.")
    args: dict = Field(..., description="The arguments passed to the tool that generated the event.")
    timestamp: datetime = Field(..., description="The timestamp of when the event was generated.", default_factory=datetime.now(UTC))
    delta: float = Field(..., description="The execution time of the event.", default=0.0)
    status: Status  = Field(..., description="The status of the event.", default=Status.SUCCESS)
    error: str = Field(..., description="The error message of the event if any.", default="")
    metadata: str = Field(..., description="The metadata of the event.", default="")
    result: dict = Field(..., description="The result of the event.", default={})