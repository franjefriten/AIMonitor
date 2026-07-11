from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Any

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
    timestamp: datetime = Field(default_factory=datetime.now(UTC), description="The timestamp of when the event was generated.")
    delta: float = Field(default=0.0, description="The execution time of the event.")
    status: Status  = Field(default=Status.SUCCESS, description="The status of the event.")
    error: str = Field(default="", description="The error message of the event if any.")
    metadata: str = Field(default="", description="The metadata of the event.")
    result: Any = Field(..., description="The result of the event.")