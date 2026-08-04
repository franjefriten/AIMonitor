import asyncio
import socket
from datetime import datetime, UTC
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry, generate_latest

import core.decorators as decorators_module
from core.decorators import monitor_tool
from core.event import MCPEvent
from core.registry import ExporterRegistry
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prometheus_exporter_integration_with_registry_and_tool():
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            response = await client.get("http://127.0.0.1:9090/-/healthy")
        except Exception as exc:  # pragma: no cover - depends on Docker availability
            pytest.skip(f"Prometheus server is not available at localhost:9090 ({exc})")

    assert response.status_code == 200

    registry = ExporterRegistry()
    exporter = PrometheusExporter(address="http://127.0.0.1:9000")
    exporter.counter._registry = None
    exporter.histogram._registry = None
    registry.register(exporter)

    decorators_module.registry = registry

    @monitor_tool
    async def sample_tool(value: str) -> dict[str, Any]:
        return {"value": value}

    await exporter.connect()
    try:
        await sample_tool("demo")
        await asyncio.sleep(0.3)

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://127.0.0.1:9000/metrics")

        assert response.status_code == 200
        body = response.text
        assert "mcp_total_calls_total" in body
        assert "mcp_tool_duration_seconds" in body
        assert 'tool_name="sample_tool"' in body
    finally:
        await exporter.close()
        await registry.shutdown()
