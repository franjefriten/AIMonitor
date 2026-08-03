from contextvars import ContextVar

_span_context: ContextVar[dict] = ContextVar("span_context", default={})
