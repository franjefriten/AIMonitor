import asyncio

import pytest

from core.event import SignalType
from core.observability import monitor
from exporters.base import BaseExporter
from core.registry import ExporterRegistry
from utils.logger import logger


@pytest.mark.asyncio
async def test_observability_api_emits_event_log_and_metric_signals():
    captured = []

    class SpyExporter(BaseExporter):
        async def export(self, event):
            captured.append(event)

        async def export_batch(self, event_batch):
            captured.extend(event_batch)

        async def healthcheck(self):
            pass

        async def status(self):
            pass

    registry = ExporterRegistry(batch_size=3, flush_delta=0.1, num_workers=1)
    registry._exporters = []
    registry.register(exporter=SpyExporter())

    await monitor.emit_tool_execution_event("sample_tool", args={"name": "Ada"}, result={"ok": True})
    await monitor.log("hello from api", level="info", source="tests")
    await monitor.record_metric("requests_total", 3, metric_type="counter", labels={"route": "/health"})

    await asyncio.sleep(0.3)
    await registry.shutdown()

    assert len(captured) == 3
    event_types = {signal.event_type for signal in captured}
    assert event_types == {SignalType.EVENT, SignalType.LOG, SignalType.METRIC}

    event_signal = next(signal for signal in captured if signal.event_type == SignalType.EVENT)
    assert event_signal.tool_name == "sample_tool"
    assert event_signal.result == {"ok": True}

    log_signal = next(signal for signal in captured if signal.event_type == SignalType.LOG)
    assert log_signal.message == "hello from api"
    assert log_signal.level == "info"

    metric_signal = next(signal for signal in captured if signal.event_type == SignalType.METRIC)
    assert metric_signal.value == 3
    assert metric_signal.metric_type == "counter"
    assert metric_signal.labels["route"] == "/health"
