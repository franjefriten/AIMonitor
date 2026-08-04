import pytest

from exporters.base import BaseExporter
from core.registry import ExporterRegistry, registry
from tests.conftest import _generate_mcp_event

import asyncio

@pytest.mark.asyncio
async def test_exporter_on_successful_events_batches():
    class SuccessfulExporter(BaseExporter):
        async def export(self, event):
            return await super().export(event)
        async def export_batch(self, event_batch):
            return await super().export_batch(event_batch)
        
    total_events = 20
    tool_names = ["some_tool", "some_other_tool", "another_tool"]
    args_set = [
        {"arg1": "some_sting", "arg2": 2},
        {"var": [1, 2, 3], "Var": "result successful"},
        {"Pop": [1, 33, 2], "list_of_trues": [True, False, True, True]}
    ]
    
    events = [_generate_mcp_event() for _ in range(total_events)]

    #registry = ExporterRegistry(batch_size=3, flush_delta=0.1, num_workers=1)
    registry.start_workers()
    registry.register(exporter=SuccessfulExporter())
    registry.register(exporter=SuccessfulExporter()) # 2
    await registry.dispatch(events=events)
    await asyncio.sleep(5) # wait for events to be processed

    assert registry._queue.empty() == True
    assert len(registry._exporters) == 2

    await registry.shutdown() # kills workers, empties and destroys queue, unsubscribes exporters

    assert registry._queue == None
    assert len(registry._exporters) == 0


@pytest.mark.asyncio
async def test_exporter_auto_removal_on_failure():
    class FailingExporter(BaseExporter):
        async def export():
            raise ConnectionError("Service Down")
        async def export_batch(self, event_batch):
            raise ConnectionError("Service Down")

    event1 = _generate_mcp_event()

    event2 = _generate_mcp_event()

    event3 = _generate_mcp_event()

    events = [event1, event2, event3]
    registry = ExporterRegistry(batch_size=3, flush_delta=0.1, num_workers=1)
    registry.start_workers()
    registry.register(exporter=FailingExporter())
    await registry.dispatch(events=events)
    await registry.shutdown()
    await asyncio.sleep(3)

    assert len(registry._exporters) == 0