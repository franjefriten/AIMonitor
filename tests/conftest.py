import random
from datetime import datetime, UTC
from core.event import MCPEvent , SpanEvent
import pytest_asyncio

from configs.config import get_settings
from core.registry import registry
from telemetry.api import internal_telemetry_manager


@pytest_asyncio.fixture(autouse=True)
async def reset_runtime_singletons():
    """Start each test with a clean registry, settings singleton, and telemetry manager."""
    await registry.reset()
    get_settings().reset()
    internal_telemetry_manager.reset()
    yield
    await registry.reset()


def _generate_mcp_event():
    return MCPEvent(
        tool_name="some_tool",
        args={"args": {"some_list": [random.randint(0, 10) for _ in range(10)]}},
        status="success",
        error="",
        metadata={},
        delta=random.random(),
        timestamp=datetime.now(UTC).strftime('%Y-%m-%d'),
        result={}
    )

def _generate_span_event(
        parent_id: str = "parent_id", 
        span_id: str = "span_id", 
        trace_id: str = "trace_id",
        operation_name: str = "operation_name"
    ) -> SpanEvent:
    return SpanEvent(
        parent_id=parent_id,
        span_id=span_id,
        trace_id=trace_id,
        operation_name=operation_name,
        status="success",
        delta=random.random()
    )