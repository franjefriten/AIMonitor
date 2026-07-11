import pytest
import pytest_asyncio
from exporters.base import BaseExporter
from core.registry import ExporterRegistry
from core.event import MCPEvent
from datetime import datetime, UTC
import asyncio


@pytest.mark.asyncio
def test_exporter_auto_removal_on_failure():
    class FailingExporter(BaseExporter):
        async def export():
            raise ConnectionError("Service Down")

    event = MCPEvent(
        tool_name="some_tool",
        args = {"arg1": "string__"},
        delta=0.5,
        error="",
        status="success",
        timestamp=datetime.now(UTC)
    )

    registry = ExporterRegistry()
    registry.register(exporter=FailingExporter())
    registry.dispatch(event=event)
    asyncio.sleep(1)

    assert len(registry._exporters) == 0