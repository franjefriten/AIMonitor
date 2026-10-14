from contextvars import ContextVar
from aimonitor.core.trace import Trace

_trace_context: ContextVar[Trace] = ContextVar("span_context", default=Trace())
