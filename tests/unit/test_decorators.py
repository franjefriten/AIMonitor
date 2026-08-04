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
    registry.register(exporter=spy)
    
    # Define tool with decorator monitor_tool
    @monitor_tool(track_duration=True, track_call_count=True)
    async def sample_tool(name: str, api_key: str):
        return f"Hello {name}"

    # Call the tool
    await sample_tool(name="DeepSeek", api_key="secret_abc")

    await asyncio.sleep(3)

    # now check
    assert len(captured_events) == 3
    event = captured_events[0]
    assert event.tool_name == "sample_tool"
    assert event.args["api_key"] == "********"  # Verificamos redacción

    # flush captured events for next test
    captured_events = []

    # Define a tool with decorator monitor_tool but dont track any metrics tracking
    @monitor_tool()
    async def sample_tool_no_metrics_track(name: str, api_key: str):
        return f"Hello {name}"
    
    await sample_tool_no_metrics_track(name="Gemini", api_key="secret_123")
        
    await asyncio.sleep(3)

    # now check
    assert len(captured_events) == 3
    event = captured_events[0]
    assert event.tool_name == "sample_tool_no_metrics_track"
    assert event.args["api_key"] == "********"  # Verificamos redacción

    # shutdown exporters
    await registry.shutdown()
    