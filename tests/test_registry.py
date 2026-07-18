import pytest
import pytest_asyncio
from exporters.base import BaseExporter
from core.registry import ExporterRegistry
from core.event import MCPEvent
from datetime import datetime, UTC
import asyncio
import random


@pytest.mark.asyncio
async def test_exporter_auto_removal_on_failure():
    class FailingExporter(BaseExporter):
        async def export():
            raise ConnectionError("Service Down")
        async def export_batch(self, event_batch):
            raise ConnectionError("Service Down")

    event1 = MCPEvent(
        tool_name="some_tool",
        args = {"arg1": "string__"},
        delta=0.5,
        error="",
        status="success",
        timestamp=datetime.now(UTC),
        result="Result of tool"
    )

    event2 = MCPEvent(
        tool_name="some_other_tool",
        args = {"arg1": 1},
        delta=0.5,
        error="The result was unsuccessful",
        status="failure",
        timestamp=datetime.now(UTC),
        result={"error": "The input parameters were not correct"}
    )

    event3 = MCPEvent(
        tool_name="some_tool",
        args = {"arg1": 0},
        delta=0.5,
        status="error",
        error="The tool returned an error",
        timestamp=datetime.now(UTC),
        result=Exception
    )

    events = [event1, event2, event3]
    registry = ExporterRegistry(batch_size=3)
    registry.start_workers()
    registry.register(exporter=FailingExporter())
    registry.dispatch(events=events)
    await asyncio.sleep(3)

    assert len(registry._exporters) == 0