import socket
from datetime import datetime, UTC

import httpx
import pytest
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


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


@pytest.mark.asyncio
async def test_prometheus_exporter_exposes_metrics_over_http():
    port = _get_free_port()
    exporter = PrometheusExporter(address=f"http://127.0.0.1:{port}")

    await exporter.connect()
    try:
        await exporter.export_batch([_build_event()])

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://127.0.0.1:{port}/metrics")

        assert response.status_code == 200
        body = response.text
        assert "mcp_total_calls_total" in body
        assert "mcp_tool_duration_seconds" in body
        assert 'tool_name="some_tool"' in body
    finally:
        await exporter.close()
