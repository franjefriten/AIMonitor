import asyncio
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from prometheus_client import CollectorRegistry, generate_latest

import aimonitor.core.observability as observability_module
from aimonitor.core.decorators import monitor_tool
from aimonitor.core.event import LogEvent, MCPEvent, MetricEvent, MetricType, SpanEvent
from aimonitor.core.registry import ExporterRegistry
from aimonitor.exporters.prometheus import PrometheusExporter


def _build_metric_event(
    name: str = "tool_execution_duration_seconds",
    value: float = 0.25,
    metric_type: MetricType = MetricType.HISTOGRAM,
    labels: dict[str, str] | None = None,
) -> MetricEvent:
    return MetricEvent(
        name=name,
        value=value,
        metric_type=metric_type,
        labels=labels or {},
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _prometheus_port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _prometheus_script_environment(container_name: str, host_port: int) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PROMETHEUS_CONTAINER_NAME"] = container_name
    environment["PROMETHEUS_HOST_PORT"] = str(host_port)
    return environment


def _run_prometheus_container(container_name: str, host_port: int) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    environment = _prometheus_script_environment(container_name, host_port)
    if os.name == "nt":
        script = repo_root / "scripts" / "prometheus" / "bat" / "run_prometheus.bat"
        subprocess.run(["cmd", "/c", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), env=environment, timeout=180)
    else:
        script = repo_root / "scripts" / "prometheus" / "sh" / "run_prometheus.sh"
        subprocess.run(["bash", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), env=environment, timeout=180)


def _restart_prometheus_container(container_name: str, host_port: int) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    environment = _prometheus_script_environment(container_name, host_port)
    if os.name == "nt":
        script = repo_root / "scripts" / "prometheus" / "bat" / "restart_prometheus.bat"
        subprocess.run(["cmd", "/c", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), env=environment, timeout=180)
    else:
        script = repo_root / "scripts" / "prometheus" / "sh" / "restart_prometheus.sh"
        subprocess.run(["bash", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), env=environment, timeout=180)


async def _wait_for_prometheus_sample(
    client: httpx.AsyncClient,
    prometheus_url: str,
    selector: str,
    newer_than: float | None = None,
) -> tuple[float, str]:
    deadline = asyncio.get_running_loop().time() + 60
    while asyncio.get_running_loop().time() < deadline:
        try:
            response = await client.get(
                f"{prometheus_url}/api/v1/query",
                params={"query": selector},
            )
        except httpx.TransportError:
            await asyncio.sleep(0.25)
            continue

        if response.status_code in (502, 503, 504):
            await asyncio.sleep(0.25)
            continue
        response.raise_for_status()
        samples = response.json()["data"]["result"]
        if samples:
            timestamp, value = samples[0]["value"]
            if newer_than is None or float(timestamp) > newer_than:
                return float(timestamp), value
        await asyncio.sleep(0.25)

    raise AssertionError(f"Prometheus did not scrape {selector} before the timeout")


async def _wait_for_prometheus_health(port: int, timeout: float = 60.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(f"http://127.0.0.1:{port}/-/healthy")
            except httpx.TransportError:
                await asyncio.sleep(0.25)
                continue
            if response.status_code == 200:
                return True
            await asyncio.sleep(0.25)
    return False


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_records_metrics_for_batch():
    exporter = PrometheusExporter()
    registry = exporter.registry
    await exporter.export(
        [
            _build_metric_event(
                name="tool_execution_count",
                value=2,
                metric_type=MetricType.COUNTER,
                labels={"tool_name": "some_tool", "status": "success"},
            ),
            _build_metric_event(
                name="queue_depth",
                value=3,
                metric_type=MetricType.GAUGE,
            ),
            _build_metric_event(
                name="tool_execution_duration_seconds",
                value=0.25,
                metric_type=MetricType.HISTOGRAM,
                labels={"tool_name": "some_tool", "status": "success"},
            ),
        ]
    )

    payload = generate_latest(registry).decode("utf-8")

    assert 'tool_execution_count_total{status="success",tool_name="some_tool"} 2.0' in payload
    assert "queue_depth 3.0" in payload
    assert 'tool_execution_duration_seconds_count{status="success",tool_name="some_tool"} 1.0' in payload


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_ignores_non_metric_signals():
    registry = CollectorRegistry(auto_describe=True)
    exporter = PrometheusExporter()

    await exporter.export(
        [
            MCPEvent(tool_name="sample_tool"),
            LogEvent(message="not a metric", source="test"),
            SpanEvent(operation_name="sample_operation"),
        ]
    )

    assert generate_latest(registry) == b""


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_rejects_metric_schema_changes():
    exporter = PrometheusExporter()
    await exporter.export([
        _build_metric_event(
            name="active_workers",
            value=2,
            metric_type=MetricType.GAUGE,
            labels={"service": "api"},
        )
    ])

    with pytest.raises(ValueError, match="already registered with labels"):
        await exporter.export([
            _build_metric_event(
                name="active_workers",
                value=3,
                metric_type=MetricType.GAUGE,
                labels={"service": "api", "region": "west"},
            )
        ])

    with pytest.raises(ValueError, match="already registered as gauge"):
        await exporter.export([
            _build_metric_event(
                name="active_workers",
                value=3,
                metric_type=MetricType.COUNTER,
                labels={"service": "api"},
            )
        ])


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_rejects_negative_counter_values_without_registering_metric():
    exporter = PrometheusExporter()
    registry = exporter.registry

    with pytest.raises(ValueError, match="cannot be incremented by a negative value"):
        await exporter.export([
            _build_metric_event(
                name="requests",
                value=-1,
                metric_type=MetricType.COUNTER,
            )
        ])

    assert generate_latest(registry) == b""


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_exposes_metrics_over_http():
    port = _get_free_port()
    exporter = PrometheusExporter(
        address=f"http://127.0.0.1:{port}",
    )

    await exporter.connect()
    try:
        assert await exporter.healthcheck() is True
        await exporter.export(
            [
                _build_metric_event(
                    name="tool_execution_count",
                    value=1,
                    metric_type=MetricType.COUNTER,
                    labels={"tool_name": "some_tool"},
                ),
                _build_metric_event(
                    name="tool_execution_count",
                    value=2,
                    metric_type=MetricType.COUNTER,
                    labels={"tool_name": "some_tool"},
                ),
                _build_metric_event(
                    name="active_workers",
                    value=3,
                    metric_type=MetricType.GAUGE,
                    labels={"service": "api"},
                ),
                _build_metric_event(
                    name="active_workers",
                    value=5,
                    metric_type=MetricType.GAUGE,
                    labels={"service": "api"},
                ),
                _build_metric_event(
                    name="request_duration_seconds",
                    value=0.25,
                    metric_type=MetricType.HISTOGRAM,
                    labels={"route": "/health"},
                ),
                _build_metric_event(
                    name="request_duration_seconds",
                    value=0.75,
                    metric_type=MetricType.HISTOGRAM,
                    labels={"route": "/health"},
                ),
            ]
        )

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://127.0.0.1:{port}/metrics")

        assert response.status_code == 200
        assert 'tool_execution_count_total{tool_name="some_tool"} 3.0' in response.text
        assert 'active_workers{service="api"} 5.0' in response.text
        assert 'request_duration_seconds_count{route="/health"} 2.0' in response.text
        assert 'request_duration_seconds_sum{route="/health"} 1.0' in response.text

        await exporter.close()
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=0.2)
        assert await exporter.recover() is True
        assert await exporter.healthcheck() is True
        description = await exporter.describe()
        assert description["status"] == "healthy"
    finally:
        await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_describe_reports_http_probe_failure(monkeypatch):
    port = _get_free_port()
    exporter = PrometheusExporter(address=f"http://127.0.0.1:{port}")

    async def return_service_unavailable(client, url, **kwargs):
        request = httpx.Request("GET", str(url))
        return httpx.Response(503, request=request)

    try:
        await exporter.connect()
        assert exporter._server_thread.is_alive()
        monkeypatch.setattr(httpx.AsyncClient, "get", return_service_unavailable)

        description = await exporter.describe()

        assert exporter._server_thread.is_alive()
        assert description["status"] == "unhealthy"
        assert description["message"] == "PrometheusExporter is not operational."
    finally:
        await exporter.close()


@pytest.mark.asyncio
async def test_prometheus_exporter_requires_bearer_token_for_scrapes():
    port = _get_free_port()
    token = "prometheus-test-token"
    exporter = PrometheusExporter(
        address=f"http://127.0.0.1:{port}",
        bearer_token=token,
    )

    try:
        await exporter.connect()
        async with httpx.AsyncClient(timeout=2.0) as client:
            unauthorized = await client.get(f"http://127.0.0.1:{port}/metrics")
            invalid_token = await client.get(
                f"http://127.0.0.1:{port}/metrics",
                headers={"Authorization": "Bearer wrong-token"},
            )
            authorized = await client.get(
                f"http://127.0.0.1:{port}/metrics",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert unauthorized.status_code == 401
        assert invalid_token.status_code == 401
        assert authorized.status_code == 200
        assert await exporter.healthcheck() is True
        assert token not in repr(await exporter.describe())
    finally:
        await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_lifecycle_operations_are_idempotent():
    port = _get_free_port()
    exporter = PrometheusExporter(address=f"http://127.0.0.1:{port}")

    try:
        await exporter.connect()
        await exporter.connect()
        await exporter.export([
            _build_metric_event(
                name="lifecycle_probe",
                value=4,
                metric_type=MetricType.GAUGE,
            )
        ])

        await exporter.close()
        await exporter.close()
        assert await exporter.recover() is True
        assert await exporter.recover() is True
        assert await exporter.healthcheck() is True

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://127.0.0.1:{port}/metrics")

        assert response.status_code == 200
        assert "lifecycle_probe 4.0" in response.text
    finally:
        await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_recovers_after_server_thread_stops():
    port = _get_free_port()
    exporter = PrometheusExporter(address=f"http://127.0.0.1:{port}")

    try:
        await exporter.connect()
        await exporter.export([
            _build_metric_event(
                name="recovery_probe",
                value=6,
                metric_type=MetricType.GAUGE,
            )
        ])

        await asyncio.to_thread(exporter._http_server.shutdown)
        await asyncio.to_thread(exporter._server_thread.join, 5.0)
        assert not exporter._server_thread.is_alive()

        assert await exporter.recover() is True
        assert await exporter.healthcheck() is True

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://127.0.0.1:{port}/metrics")

        assert response.status_code == 200
        assert "recovery_probe 6.0" in response.text
    finally:
        await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_recovers_after_bind_conflict():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    exporter: PrometheusExporter | None = None
    try:
        exclusive_address_use = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive_address_use is not None:
            blocker.setsockopt(socket.SOL_SOCKET, exclusive_address_use, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        exporter = PrometheusExporter(address=f"http://127.0.0.1:{port}")

        assert await exporter.recover() is False

        blocker.close()
        assert await exporter.recover() is True
        assert await exporter.healthcheck() is True
    finally:
        blocker.close()
        if exporter is not None:
            await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_server_restart_resumes_scraping():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is not installed")

    try:
        docker_info = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("Docker daemon is unavailable")
    if docker_info.returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    run_id = uuid4().hex
    container_name = f"aimonitor-prometheus-{run_id[:12]}"
    prometheus_port = _get_free_port()
    existing_container = subprocess.run(
        [docker, "container", "inspect", container_name],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if existing_container.returncode == 0:
        pytest.skip("The test's Prometheus container name is already in use")
    if not _prometheus_port_is_available(9000):
        pytest.skip("Port 9000 is already in use")
    if not _prometheus_port_is_available(prometheus_port):
        pytest.skip(f"Prometheus test port {prometheus_port} is already in use")

    exporter = PrometheusExporter(address="http://0.0.0.0:9000")
    await exporter.export([
        _build_metric_event(
            name="prometheus_restart_probe",
            value=7,
            metric_type=MetricType.GAUGE,
            labels={"run_id": run_id},
        )
    ])

    prometheus_url = f"http://127.0.0.1:{prometheus_port}"
    selector = f'prometheus_restart_probe{{run_id="{run_id}"}}'
    container_started = False

    try:
        await exporter.connect()
        _run_prometheus_container(container_name, prometheus_port)
        container_started = True

        async with httpx.AsyncClient(timeout=3.0) as client:
            first_timestamp, first_value = await _wait_for_prometheus_sample(
                client,
                prometheus_url,
                selector,
            )
            assert first_value == "7"

            _restart_prometheus_container(container_name, prometheus_port)
            restarted_timestamp, restarted_value = await _wait_for_prometheus_sample(
                client,
                prometheus_url,
                selector,
                newer_than=first_timestamp,
            )

        assert restarted_timestamp > first_timestamp
        assert restarted_value == "7"
    finally:
        try:
            if container_started and not await _wait_for_prometheus_health(prometheus_port, timeout=5.0):
                _restart_prometheus_container(container_name, prometheus_port)
                if not await _wait_for_prometheus_health(prometheus_port):
                    pytest.fail("Prometheus did not become available after restarting its container")
        finally:
            try:
                if container_started:
                    subprocess.run(
                        [docker, "rm", "--force", container_name],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
            finally:
                await exporter.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_prometheus_exporter_integration_with_registry_and_tool(monkeypatch):
    registry = ExporterRegistry(batch_size=1)
    port = _get_free_port()
    exporter = PrometheusExporter(
        address=f"http://127.0.0.1:{port}",
    )
    registry.register(exporter)

    monkeypatch.setattr(observability_module, "registry", registry)

    @monitor_tool()
    async def sample_tool(value: str) -> dict[str, Any]:
        return {"value": value}

    try:
        await exporter.connect()
        await sample_tool("demo")

        async with httpx.AsyncClient(timeout=2.0) as client:
            deadline = asyncio.get_running_loop().time() + 5
            response = None
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"http://127.0.0.1:{port}/metrics")
                if 'tool_execution_count_total{status="success",tool_name="sample_tool"} 1.0' in response.text:
                    break
                await asyncio.sleep(0.05)

        assert response is not None
        assert response.status_code == 200
        assert 'tool_execution_count_total{status="success",tool_name="sample_tool"} 1.0' in response.text
        assert 'tool_execution_duration_seconds_count{status="success",tool_name="sample_tool"} 1.0' in response.text
    finally:
        await registry.shutdown()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.prometheus
async def test_incompatible_schema_for_prometheus_exporter(monkeypatch):

    registry = ExporterRegistry(batch_size=1)
    port = _get_free_port()
    exporter = PrometheusExporter(
        address=f"http://127.0.0.1:{port}",
    )
    registry.register(exporter)

    monkeypatch.setattr(observability_module, "registry", registry)

    @monitor_tool()
    async def sample_tool(value: str) -> dict[str, Any]:
        return {"value": value}

    try:
        await exporter.connect()
        await sample_tool("demo")

        async with httpx.AsyncClient(timeout=2.0) as client:
            deadline = asyncio.get_running_loop().time() + 5
            response = None
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"http://127.0.0.1:{port}/metrics")
                if 'tool_execution_count_total{status="success",tool_name="sample_tool"} 1.0' in response.text:
                    break
                await asyncio.sleep(0.05)

        assert response is not None
        assert response.status_code == 200
        assert 'tool_execution_count_total{status="success",tool_name="sample_tool"} 1.0' in response.text
        assert 'tool_execution_duration_seconds_count{status="success",tool_name="sample_tool"} 1.0' in response.text
    finally:
        await registry.shutdown()