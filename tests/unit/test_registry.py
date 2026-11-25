import pytest

from aimonitor.exporters.base import BaseExporter
from aimonitor.core.event import HealthStatus, SDKHealthStatus
from aimonitor.core.registry import ExporterRegistry, registry
from tests.conftest import _generate_mcp_event

import asyncio

@pytest.mark.asyncio
async def test_exporter_on_successful_events_batches():
    class SuccessfulExporter(BaseExporter):
        async def export(self, event_batch):
            return await super().export(event_batch)
        async def healthcheck(self):
            return True
        async def describe(self):
            return {
                "status": "healthy",
                "message": "Exporter is healthy and connected to the destination.",
                "timestamp": "2023-01-01T12:00:00Z"
            }
        async def recover(self):
            return True
        
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
        async def export(self, event_batch):
            raise ConnectionError("Service Down")

        async def healthcheck(self):
            return False

        async def describe(self):
            return {"status": "unhealthy", "message": "Service Down"}
        
        async def recover(self):
            return True

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


@pytest.mark.asyncio
async def test_registry_tracks_export_failure_and_shutdown_status():
    class FailingExporter(BaseExporter):
        async def export(self, event_batch):
            raise ConnectionError("Service Down")

        async def healthcheck(self):
            return True

        async def describe(self):
            return {"status": "healthy"}
        
        async def recover(self):
            return True

    exporter = FailingExporter()
    registry.register(exporter)

    await registry._send_batch([_generate_mcp_event()])
    snapshot = await registry.health_snapshot()
    exporter_snapshot = next(iter(snapshot.exporters.values()))

    assert exporter_snapshot.status == HealthStatus.FAILURE
    assert snapshot.summary["failure_count"] == 1
    assert len(registry.exporters) == 1

    await registry.shutdown()
    snapshot = await registry.health_snapshot()
    exporter_snapshot = next(iter(snapshot.exporters.values()))

    assert exporter_snapshot.status == HealthStatus.STOPPED


@pytest.mark.asyncio
async def test_minimal_exporter_protocol_dispatches_without_readiness_lifecycle():
    exported_batches = []

    class MinimalExporter:
        async def export(self, event_batch):
            exported_batches.append(list(event_batch))

    registry = ExporterRegistry(batch_size=1, num_workers=1)
    exporter = MinimalExporter()
    registry.register(exporter)

    snapshot = await registry.health_snapshot()
    assert snapshot.status == SDKHealthStatus.EMPTY
    assert snapshot.exporters == {}
    assert registry.exporters == (exporter,)

    event = _generate_mcp_event()
    await registry.dispatch(event)
    await asyncio.wait_for(registry._queue.join(), timeout=1)

    assert exported_batches == [[event]]
    snapshot = await registry.health_snapshot()
    assert snapshot.status == SDKHealthStatus.EMPTY
    assert snapshot.exporters == {}

    await registry.shutdown()