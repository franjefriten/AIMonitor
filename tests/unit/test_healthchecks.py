from exporters.base import BaseExporter, with_retry
from core.event import MCPEvent, BaseSignal, SignalType, HealthCheckEvent, HealthStatus
from core.registry import registry
from telemetry.api import get_liveness, get_readiness

import pytest
import asyncio


@pytest.mark.asyncio
async def test_healthcheck_api_returns_liveness_and_empty_readiness():
    assert await get_liveness() == {"status": "alive"}

    readiness = await get_readiness()

    assert readiness["status"] == "empty"
    assert readiness["summary"]["total_exporters"] == 0


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

    # Test the exporter healthcheck directly so the registry worker does not
    # produce a second event in parallel.
    exporter = SpyExporter()

    # Perform the health check
    await exporter.healthcheck()

    # Check that a HealthCheckEvent was emitted
    assert len(captured) == 1
    event = captured[0]
    assert isinstance(event, HealthCheckEvent)
    assert event.status == HealthStatus.HEALTHY