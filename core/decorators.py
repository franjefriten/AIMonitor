import functools
from typing import Callable, Any
import time
import asyncio
from core.registry import registry
from core.event import MCPEvent
import inspect
from utils.logger import logger
from utils.security import redact_sensitive_data


def monitor_tool(func: Callable):

    is_couroutine = inspect.iscoroutinefunction(func)

    @functools.wraps(func)
    async def async_wrapper(is_couroutine=is_couroutine, **kwargs):
        return await _execute_and_monitor(func, **kwargs, is_couroutine=is_couroutine)
    
    @functools.wraps(func)
    def sync_wrapper(is_couroutine=is_couroutine, **kwargs):
        return _execute_and_monitor(func, **kwargs, is_couroutine=is_couroutine)

    return async_wrapper if is_couroutine else sync_wrapper
    

def _execute_and_monitor(func: Callable, is_couroutine: bool, **kwargs) -> Any:
    start_time = time.perf_counter()

    safe_args = redact_sensitive_data(kwargs)
    event_data = {
        "tool_name": func.__name__,
        "arguments": safe_args,
        "timestamp": start_time,
    }

    try:
        if is_couroutine:
            result = asyncio.run_coroutine_threadsafe(func(**kwargs))
        else:
            result = func(**kwargs)
        event_data["status"] = "success"
        event_data["result"] = result
    
    except Exception as e:
        event_data["status"] = "error"
        event_data["error"] = str(e)
        raise e
    finally:
        end_time = time.perf_counter()
        delta = end_time - start_time
        event_data["delta"] = delta
        event = MCPEvent(**event_data)
        registry.dispatch(event)
        logger.info(f"Monitor tool: {func.__name__} tool with duration {delta:.4f} Event dispatched: {event.model_dump_json()}")