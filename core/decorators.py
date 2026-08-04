import functools
import time
import inspect
from datetime import datetime, UTC
from typing import Callable, Literal, Any, Dict, List
from uuid import uuid4
from core.observability import monitor
from utils.logger import logger
from utils.security import redact_sensitive_data
from configs.config import get_settings
from utils.context import _trace_context
from core.trace import Trace, SpanEvent

settings = get_settings()

def monitor_tool(
        track_duration: bool = True,
        track_call_count: bool = True,
        version: str = ""
    ) -> Callable:
    """
    Decorator used to monitor general tools executed by agents. Must be used as a wrapper
    around the mcp tool, completely agonostic to the underlying sdk.
    
    Example
    ```python
    @monitor_tool(track_duration: bool = True, track_call_count = True)
    @mcp.tool
    def some_mcp_tool
        ...
    ```

    This function will send to all subscribed exporters
    - A tool execution (MCPEvent) event with:
        - tool name
        - args
        - result
        - status: ERROR, SUCCESS, WARNING, FAILURE
        - error message if status = FAILURE or ERROR
        - delta: time performance
    - A metric for execution time if `track_duration = True`:
        - name: "tool_execution_duration_seconds"
        - value: time performance
        - metric_type: "histogram"
        - labels: tool_name, status
    - A metric for execution count if `track_call_count = True`:
        - name: "tool_execution_count"
        - value: 1
        - metric_type: "counter"
        - labels: tool_name, status

    NOTE: tool kwargs will be censored by sensitive keys set in config .yaml/.json file plus default ones
    when dispatched to exporters.

    NOTE: if tool call event tracking is disabled by env vars, it will not be dispatched
    
    NOTE: if metrics tracking is disabled by env vars, it will not be dispatched
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            status = "success"
            error_message = ""
            result = None
            trace = Trace(
                func_name=func.__name__,
                metadata=kwargs or {}
            )
            token = _trace_context.set(trace)

            # Redactamos argumentos tanto posicionales como nombrados
            safe_args = redact_sensitive_data(kwargs)

            try:
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result

            except Exception as exc:
                status = "failure"
                error_message = str(exc)
                raise

            finally:
                end_time = time.perf_counter()
                delta = end_time - start_time
                _trace_context.reset(token)
                if isinstance(result, dict) and "error" in result:
                    status = "error"
                    error_message = result.get("error", "")

                try:
                    if settings.enabled and settings.track_events:
                        logger.info(f"Emiting tool execution event for {func.__name__}")
                        await monitor.emit_tool_execution_event(
                            tool_name=func.__name__,
                            args=safe_args,
                            result=result,
                            status=status,
                            error=error_message,
                            delta=delta,
                            environment=settings.env_code,
                            version=version
                        )
                    if settings.enabled and settings.track_metrics and track_duration:
                        logger.info(f"Emiting tool metrics event for {func.__name__}")
                        await monitor.record_metric(
                            name="tool_execution_duration_seconds",
                            value=delta,
                            metric_type="histogram",
                            labels={"tool_name": func.__name__, "status": status},
                            environment=settings.env_code,
                            version=version
                        )
                    if settings.enabled and settings.track_metrics and track_call_count:
                        logger.info(f"Emiting tool metrics event for {func.__name__}")
                        await monitor.record_metric(
                            name="tool_execution_count",
                            value=1,
                            metric_type="counter",
                            labels={"tool_name": func.__name__, "status": status},
                            environment=settings.env_code,
                            version=version
                        )
                    logger.info(f"Tool '{func.__name__}' monitored in {delta:.4f}s")
                except Exception as registry_err:
                    logger.error(f"Failed to dispatch monitor event: {registry_err}")

        return wrapper
    return decorator


async def record_log(
        message: str, 
        level: Literal["critical", "error", "warning", "info", "debug"] = "info",
        version: str = "",
        *args, 
        **kwargs
    ):
    """Generic log function
    used for telemetry data and can be invoked when necessary
    inside a tool and dispatched to exporters

    Keyword arguments:

    - message (str) -- custom message for the log
    - level (str: critical|error|warning|info|debug) -- log level, default to info
    - *args
    - **kwargs

    NOTE: kwargs are redacted to remove sensitive data before dispatching to exporters and added to metadata field of the log signal
    
    Return: None
    """
    
    kwargs = redact_sensitive_data(kwargs)
    await monitor.log(
        message=message,
        level=level,
        metadata={**kwargs, "extra_data": args},
        environment=settings.env_code,
        version=version
    )


def track_tool_call_event(func: Callable) -> Callable: 
    """
    Decorator used to monitor general tools executed by agents. Must be used as a wrapper
    around the mcp tool, completely agonostic to the underlying sdk.
    
    Example
    ```python
    @track_tool_call_event
    @mcp.tool
    def some_mcp_tool
        ...
    ```

    This function will send to all subscribed exporters
    - A tool execution (MCPEvent) event with:
        - tool name
        - args
        - result
        - status: ERROR, SUCCESS, WARNING, FAILURE
        - error message if status = FAILURE or ERROR
        - delta: time performance

    NOTE: tool kwargs will be censored by sensitive keys set in config .yaml/.json file plus default ones
    when dispatched to exporters.

    NOTE: if tool call event tracking is disabled by env vars, it will not be dispatched
    
    NOTE: if metrics tracking is disabled by env vars, it will not be dispatched
    """
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        status = "success"
        error_message = ""
        result = None
        trace = Trace(
            func_name=func.__name__,
            metadata=kwargs or {}
        )
        token = _trace_context.set(trace)

        # Redactamos argumentos tanto posicionales como nombrados
        safe_args = redact_sensitive_data(kwargs)

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return result

        except Exception as exc:
            status = "failure"
            error_message = str(exc)
            raise

        finally:
            end_time = time.perf_counter()
            delta = end_time - start_time
            _trace_context.reset(token)
            if isinstance(result, dict) and "error" in result:
                status = "error"
                error_message = result.get("error", "")
            try:
                if settings.enabled and settings.track_events:
                    await monitor.emit_tool_execution_event(
                        tool_name=func.__name__,
                        args=safe_args,
                        result=result,
                        status=status,
                        error=error_message,
                        delta=delta,
                        environment=settings.env_code,
                    )
                logger.info(f"Tool '{func.__name__}' monitored in {delta:.4f}s")
            except Exception as registry_err:
                logger.error(f"Failed to dispatch monitor event: {registry_err}")

    return wrapper


def track_tool_metrics(
        track_duration: bool = True,
        track_call_count: bool = True
    ) -> Callable:
    """
    Decorator used to monitor general tools executed by agents. Must be used as a wrapper
    around the mcp tool, completely agonostic to the underlying sdk.
    
    Example
    ```python
    @track_tool_metrics(track_duration=True, track_call_count=True)
    @mcp.tool
    def some_mcp_tool
        ...
    ```

    This function will send to all subscribed exporters
    - A metric for execution time if `track_duration = True`:
        - name: "tool_execution_duration_seconds"
        - value: time performance
        - metric_type: "histogram"
        - labels: tool_name, status
    - A metric for execution count if `track_call_count = True`:
        - name: "tool_execution_count"
        - value: 1
        - metric_type: "counter"
        - labels: tool_name, status

    NOTE: tool kwargs will be censored by sensitive keys set in config .yaml/.json file plus default ones
    when dispatched to exporters.
    
    NOTE: if metrics tracking is disabled by env vars, it will not be dispatched
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            status = "success"
            error_message = ""
            result = None
            trace = Trace(
                func_name=func.__name__,
                metadata=kwargs or {}
            )
            token = _trace_context.set(trace)

            # Redactamos argumentos tanto posicionales como nombrados
            safe_args = redact_sensitive_data(kwargs)

            try:
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result

            except Exception as exc:
                status = "failure"
                error_message = str(exc)
                raise

            finally:
                _trace_context.reset(token)
                end_time = time.perf_counter()
                delta = end_time - start_time
                if isinstance(result, dict) and "error" in result:
                    status = "error"
                    error_message = result.get("error", "")
                try:
                    if settings.enabled and settings.track_metrics and track_duration:
                        await monitor.record_metric(
                            name="tool_execution_duration_seconds",
                            value=delta,
                            metric_type="histogram",
                            labels={"tool_name": func.__name__, "status": status},
                            environment=settings.env_code
                        )
                    if settings.enabled and settings.track_metrics and track_call_count:
                        await monitor.record_metric(
                            name="tool_execution_count",
                            value=1,
                            metric_type="counter",
                            labels={"tool_name": func.__name__, "status": status},
                            environment=settings.env_code
                        )
                    logger.info(f"Tool '{func.__name__}' monitored in {delta:.4f}s")
                except Exception as registry_err:
                    logger.error(f"Failed to dispatch monitor event: {registry_err}")

        return wrapper
    return decorator