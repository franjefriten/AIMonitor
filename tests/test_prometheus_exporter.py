import pytest
from datetime import datetime, UTC
from prometheus_client import CollectorRegistry, generate_latest

from core.event import MCPEvent
from exporters.prometheus import PrometheusExporter


def _build_event(tool_name: str = "some_tool", status: str = "success", delta: float = 0.25) -> MCPEvent:
    return MCPEvent(
        tool_name=tool_name,
        args={"arg": "value"},
        timestamp=datetime.now(UTC),
        delta=delta,
        status=status,
        error="",
        metadata="",
        result={},
    )


@pytest.mark.asyncio
async def test_prometheus_exporter_records_metrics_for_batch():
    registry = CollectorRegistry(auto_describe=True)
    exporter = PrometheusExporter(address="http://127.0.0.1:9000", registry=registry)

    event = _build_event()
    await exporter.export_batch([event])

    payload = generate_latest(registry).decode("utf-8")

    assert "mcp_total_calls_total" in payload
    assert 'tool_name="some_tool"' in payload
    assert 'status="success"' in payload
    assert "mcp_tool_duration_seconds" in payload
