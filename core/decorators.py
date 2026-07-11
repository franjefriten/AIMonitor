import functools
import time
import asyncio
import inspect
from typing import Callable, Any
from core.registry import registry
from core.event import MCPEvent
from utils.logger import logger
from utils.security import redact_sensitive_data

def monitor_tool(func: Callable):
    """
    Decorador para monitorizar herramientas MCP.
    Maneja tanto funciones síncronas como asíncronas de forma transparente.
    """
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        
        # Redactamos argumentos tanto posicionales como nombrados
        # Nota: redact_sensitive_data debería manejar un dict con ambos
        safe_args = redact_sensitive_data(kwargs)
        
        event_data = {
            "tool_name": func.__name__,
            "args": safe_args,
            "timestamp": start_time,
            "status": "pending"
        }

        try:
            # Ejecución centralizada
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            event_data["status"] = "success"
            event_data["result"] = result
            return result

        except Exception as e:
            event_data["status"] = "error"
            event_data["error"] = str(e)
            raise e
            
        finally:
            end_time = time.perf_counter()
            event_data["delta"] = end_time - start_time
            
            # Despacho al registry
            try:
                event = MCPEvent(**event_data)
                registry.dispatch(event)
                logger.info(f"Tool '{func.__name__}' monitored in {event_data['delta']:.4f}s")
            except Exception as registry_err:
                # Nunca permitas que el sistema de logs rompa la ejecución de la herramienta
                logger.error(f"Failed to dispatch monitor event: {registry_err}")

    return wrapper