import pytest
import asyncio
from core.registry import registry
from exporters.base import BaseExporter
from core.decorators import monitor_tool

@pytest.mark.asyncio
async def test_tool_monitoring_workflow():
    # 1. Store in a buffer all captured events
    captured_events = []

    # 2. Mock exporter will store those events
    class SpyExporter(BaseExporter):
        async def export(self, event):
            captured_events.append(event)
        async def export_batch(self, event_batch: list):
            captured_events.extend(event_batch)

    spy = SpyExporter()
    
    # Clean up registry and add spy mock
    registry._exporters = [spy]
    
    # Define tool with decorator monitor_tool
    @monitor_tool
    async def sample_tool(name: str, api_key: str):
        return f"Hello {name}"
    
    await sample_tool(name="Gemini", api_key="secret_123")
    
    # shutdown exporters
    await registry.shutdown()
    # now check
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.tool_name == "sample_tool"
    assert event.args["api_key"] == "********"  # Verificamos redacción