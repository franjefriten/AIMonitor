from contextvars import ContextVar
from core.trace import Trace

_trace_context: ContextVar[Trace] = ContextVar("span_context", default=Trace())
