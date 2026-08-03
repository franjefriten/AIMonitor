from core.event import BaseSignal, SignalType, MCPEvent, LogEvent, MetricEvent, SpanEvent
from core.observability import monitor
from core.registry import registry
from core.decorators import monitor_tool

from typing import Any, Dict, List, Optional
import asyncio
import pytest


@pytest.mark.asyncio
async def test_emit_span_event():
    captured = []

    class SpyExporter:
        async def export(self, event):
            captured.append(event)

        async def export_batch(self, event_batch):
            captured.extend(event_batch)

    registry.register(exporter=SpyExporter())

    def _some_nested_function():
        pass

    @monitor_tool(track_duration=False, track_call_count=False)
    async def sample_function():
        await asyncio.sleep(0.1)

        async with monitor.span("nested_span") as span:
            _some_nested_function()
    
    await sample_function()

    await asyncio.sleep(0.3)

    assert len(captured) == 2 # One for the sample_function (MCPEvent) and one for the nested_span (SpanEvent)
    assert any(isinstance(event, SpanEvent) for event in captured)
    assert any(isinstance(event, MCPEvent) for event in captured)
    mcp_event = next(event for event in captured if isinstance(event, MCPEvent))
    nested_span_event = next(event for event in captured if isinstance(event, SpanEvent))
    assert nested_span_event.operation_name == "nested_span"
    assert "sample_function" in nested_span_event.parent_id
    assert "nested_span" in nested_span_event.span_id  

    captured = []  # Reset captured events for the next test
    await registry.shutdown()


@pytest.mark.asyncio
async def test_emit_multi_span_event():
    captured = []

    class SpyExporter:
        async def export(self, event):
            captured.append(event)

        async def export_batch(self, event_batch):
            captured.extend(event_batch)

    registry.register(exporter=SpyExporter())

    def _some_nested_function():
        pass

    @monitor_tool(track_duration=False, track_call_count=False)
    async def sample_function():
        await asyncio.sleep(0.1)

        async with monitor.span("nested_span") as span:
            _some_nested_function()
            async with monitor.span("another_nested_span") as another_span:
                _some_nested_function()
    
    await sample_function()

    await asyncio.sleep(0.3)

    assert len(captured) == 3 # One for the sample_function (MCPEvent) and two for the nested spans (SpanEvent)
    assert len([event for event in captured if isinstance(event, SpanEvent)]) == 2
    assert len([event for event in captured if isinstance(event, MCPEvent)]) == 1
    span_events = [event for event in captured if isinstance(event, SpanEvent)]
    #print(f"[span_events]\n{"\n".join(event.model_dump_json() for event in span_events)}")
    assert span_events[1].operation_name == "nested_span"
    assert span_events[0].operation_name == "another_nested_span"

    await registry.shutdown()

