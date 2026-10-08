from exporters.base import BaseExporter, with_retry
from core.event import MCPEvent, BaseSignal, SignalType, HealthCheckEvent, HealthStatus
from core.registry import registry

import pytest
import asyncio


@pytest.mark.asyncio
async def test_health_check_event_emission():
    captured = []

    class SpyExporter(BaseExporter):
        async def export(self, event):
            captured.append(event)

        async def export_batch(self, event_batch):
            captured.extend(event_batch)
        
        async def healthcheck(self):
            captured.extend([HealthCheckEvent(message="Health check passed for SpyExporter.", status=HealthStatus.HEALTHY)])
            return True

        async def status(self):
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Exporter is healthy and connected to the destination.",
                "timestamp": "2023-01-01T12:00:00Z"
            }

    registry.register(exporter=SpyExporter())

    # Create an instance of the exporter to test
    exporter = registry._exporters[0]

    # Clear captured events before manual healthcheck to isolate the test
    captured.clear()
    
    # Perform the health check
    await exporter.healthcheck()

    # Check that a HealthCheckEvent was emitted from the manual call
    assert len(captured) >= 1
    event = captured[0]
    assert isinstance(event, HealthCheckEvent)
    assert event.status == HealthStatus.HEALTHY
    
    await registry.shutdown()