import asyncio
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4
import httpx
import pytest
import pytest_asyncio
from confluent_kafka import KafkaException, aio
import json

from aimonitor.core.event import Status
import aimonitor.core.decorators as decorators_module
from aimonitor.core.decorators import monitor_tool
from aimonitor.core.event import MCPEvent
from aimonitor.core.registry import ExporterRegistry
from aimonitor.exporters.kafka import KafkaExporter, KafkaHealthProbe
from aimonitor.configs.config import get_settings
from aimonitor.core.event import SignalType


@pytest.fixture
def isolated_settings():
    settings = get_settings()
    settings.reset()
    yield settings
    settings.reset()


@pytest_asyncio.fixture
async def kafka_container():
    if not _port_for_kafka():
        if shutil.which("docker") is None:
            pytest.skip("Kafka is not running and Docker is unavailable")
        _run_kafka_container()
        if not await _wait_for_kafka(timeout=60):
            pytest.fail("Kafka did not become available after starting its container")

    try:
        yield
    finally:
        if not _port_for_kafka():
            if shutil.which("docker") is None:
                pytest.fail("Kafka was stopped during the test and Docker is unavailable to restart it")
            _restart_kafka_container()
            if not await _wait_for_kafka(timeout=60):
                pytest.fail("Kafka did not become available after restarting its container")


@pytest_asyncio.fixture
async def kafka_sasl_container():
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for the Kafka SASL integration test")

    container_name = _run_kafka_sasl_container()
    try:
        if not await _wait_for_kafka(port=_SASL_KAFKA_PORT, timeout=60):
            pytest.fail("SASL Kafka broker did not become available")
        yield
    finally:
        repo_root = Path(__file__).resolve().parents[2]
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=90,
        )


def _build_event(tool_name: str = "some_tool", status: Status = Status.SUCCESS, delta: float = 0.25) -> MCPEvent:
    return MCPEvent(
        tool_name=tool_name,
        args={"arg": "value"},
        timestamp=datetime.now(timezone.utc),
        delta=delta,
        status=status,
        error="",
        metadata={},
        result={},
    )


async def _wait_for_kafka(host: str = "localhost", port: int = 9092, timeout: float = 20.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if _port_for_kafka(host=host, port=port, timeout=1.0):
            return True
        await asyncio.sleep(0.5)
    return _port_for_kafka(host=host, port=port, timeout=1.0)


def _run_kafka_container() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if os.name == "nt":
        script = repo_root / "scripts" / "kafka" / "bat" / "run_kafka.bat"
        subprocess.run(["cmd", "/c", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), timeout=90)
    else:
        script = repo_root / "scripts" / "kafka" / "sh" / "run_kafka.sh"
        subprocess.run(["bash", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), timeout=90)


def _run_kafka_sasl_container() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    container_name = f"aimonitor-kafka-sasl-{uuid4().hex[:8]}"
    jaas_file = repo_root / "scripts" / "kafka" / "sasl" / "broker_jaas.conf"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--hostname",
            "localhost",
            "-p",
            f"{_SASL_KAFKA_PORT}:9094",
            "--mount",
            f"type=bind,source={jaas_file.resolve()},target=/etc/kafka/secrets/broker_jaas.conf,readonly",
            "-e",
            "KAFKA_NODE_ID=1",
            "-e",
            "KAFKA_PROCESS_ROLES=broker,controller",
            "-e",
            "KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:29093",
            "-e",
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,SASL_PLAINTEXT:SASL_PLAINTEXT,SASL_PLAINTEXT_HOST:SASL_PLAINTEXT",
            "-e",
            "KAFKA_ADVERTISED_LISTENERS=SASL_PLAINTEXT_HOST://localhost:9094,SASL_PLAINTEXT://localhost:19094",
            "-e",
            "KAFKA_LISTENERS=CONTROLLER://:29093,SASL_PLAINTEXT_HOST://:9094,SASL_PLAINTEXT://:19094",
            "-e",
            "KAFKA_INTER_BROKER_LISTENER_NAME=SASL_PLAINTEXT",
            "-e",
            "KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER",
            "-e",
            "KAFKA_SASL_ENABLED_MECHANISMS=PLAIN",
            "-e",
            "KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL=PLAIN",
            "-e",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
            "-e",
            "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1",
            "-e",
            "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1",
            "-e",
            "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0",
            "-e",
            "KAFKA_LOG_DIRS=/tmp/kraft-combined-logs",
            "-e",
            "KAFKA_OPTS=-Djava.security.auth.login.config=/etc/kafka/secrets/broker_jaas.conf",
            "apache/kafka:latest",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=120,
    )
    return container_name


def _stop_kafka_container() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if os.name == "nt":
        script = repo_root / "scripts" / "kafka" / "bat" / "stop_kafka_container.bat"
        subprocess.run(["cmd", "/c", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), timeout=90)
    else:
        script = repo_root / "scripts" / "kafka" / "sh" / "stop_kafka_container.sh"
        subprocess.run(["bash", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), timeout=90)


def _restart_kafka_container() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if os.name == "nt":
        script = repo_root / "scripts" / "kafka" / "bat" / "restart_kafka.bat"
        subprocess.run(["cmd", "/c", str(script)], check=True, capture_output=True, text=True, cwd=str(repo_root), timeout=180)
    else:
        script = repo_root / "scripts" / "kafka" / "sh" / "restart_kafka.sh"
        subprocess.run(["bash", str(script)], check=True, cwd=str(repo_root), timeout=180)


_TEST_TOPIC = "aimonitor-events-{0}".format(uuid4())
_SASL_KAFKA_PORT = 9094
_SASL_KAFKA_USERNAME = "aimonitor"
_SASL_KAFKA_PASSWORD = "integration-test-secret"

# NOTE: this function assumes we are running kafka broker in port 9092 on localhost
# check scripts/kafka/* for consistency with the Kafka broker configuration
def _port_for_kafka(host: str = "localhost", port: int = 9092, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False

@pytest.mark.integration
@pytest.mark.kafka
@pytest.mark.asyncio
async def test_kafka_exporter_sends_events_to_kakfa(tmp_path, isolated_settings, kafka_container):
    config_path = tmp_path / "aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: DEV
tracking:
  enabled: true
  track_metrics: true
  track_events: true
  track_logs: true
exporters:
  prometheus:
    enabled: false
  file:
    enabled: false
  otel:
    enabled: false
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "PLAINTEXT"
    auto_offset_reset: "earliest"
    topics:
      event: "{0}"
      metric: "aimonitor-metrics"
      log: "aimonitor-logs"
      span: "aimonitor-spans"

    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
    """.strip().format(_TEST_TOPIC)
    )
    await isolated_settings.load_from_yaml(config_path)
    registry = ExporterRegistry(batch_size=3)
    print(f"[kafka_settings] {isolated_settings.get_kafka_config()}")
    kafka_exporter = KafkaExporter(
        kafka_configs=isolated_settings.get_kafka_config(),
        topics={
            SignalType.EVENT: _TEST_TOPIC,
        }
    )
    registry.register(kafka_exporter)

    events = [_build_event() for _ in range(12)]
    await kafka_exporter.export(
        event_batch=events
    )
    await asyncio.sleep(0.5)

    print(f"[kafka_exporter_config] {kafka_exporter.kafka_configs}")
    print(f"[test_topic] {_TEST_TOPIC}")
    print(f"[settings] {isolated_settings.exporters.kafka}")

    configs_consumer = isolated_settings.get_kafka_config().copy()
    configs_consumer.update({
        "group.id": f"test-group-{uuid4()}",
    }) 
    configs_consumer.pop("client.id", None)

    consumed_events = []
    consumer = aio.AIOConsumer(consumer_conf=configs_consumer)
    registered_topics = await consumer.list_topics()
    assert _TEST_TOPIC in registered_topics.topics.keys()
    try:
        await consumer.subscribe([_TEST_TOPIC])
        deadline = asyncio.get_running_loop().time() + 15

        while len(consumed_events) < len(events) and asyncio.get_running_loop().time() < deadline:
            message = await consumer.poll(timeout=1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == 1:  # _PARTITION_EOF
                    continue
                pytest.fail(f"Error while consuming message: {message.error()}")
            consumed_events.append(message)

        assert len(consumed_events) > 0
        assert len(consumed_events) == len(events), (
            f"Expected {len(events)} messages but only consumed {len(consumed_events)}. "
            f"The loop stopped early or Kafka still had stale state."
        )

        for message, event in zip(consumed_events, events):
            payload = json.loads(message.value())
            assert payload["tool_name"] == event.tool_name
            assert message.key() == kafka_exporter._encode_partition_key(tool_name=event.event_type.value)

    finally:
        await consumer.close()
        await kafka_exporter.close()
        await registry.shutdown()


@pytest.mark.integration
@pytest.mark.kafka
@pytest.mark.asyncio
async def test_kafka_healthcheck_returns_true_when_kafka_is_healthy(tmp_path, isolated_settings, kafka_container):
    config_path = tmp_path / "aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: DEV
tracking:
  enabled: true
  track_metrics: true
  track_events: true
  track_logs: true
exporters:
  prometheus:
    enabled: false
  file:
    enabled: false
  otel:
    enabled: false
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "PLAINTEXT"
    auto_offset_reset: "earliest"
    topics:
      event: "{0}"
      metric: "aimonitor-metrics"
      log: "aimonitor-logs"
      span: "aimonitor-spans"

    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
""".strip().format(_TEST_TOPIC)
    )
    await isolated_settings.load_from_yaml(config_path)
    registry = ExporterRegistry(batch_size=3)
    print(f"[kafka_settings] {isolated_settings.get_kafka_config()}")
    kafka_exporter = KafkaExporter(
        kafka_configs=isolated_settings.get_kafka_config(),
        topics={
            SignalType.EVENT: _TEST_TOPIC,
        }
    )
    registry.register(kafka_exporter)
    result = await kafka_exporter.healthcheck()
    assert result is True

    await kafka_exporter.close()
    await registry.shutdown()

@pytest.mark.integration
@pytest.mark.kafka
@pytest.mark.asyncio
async def test_kafka_exporter_recovery_cycle_after_broker_restart(tmp_path, isolated_settings, kafka_container):
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for this Kafka recovery test")

    topic_name = _TEST_TOPIC
    config_path = tmp_path / "aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: DEV
tracking:
  enabled: true
  track_metrics: true
  track_events: true
  track_logs: true
exporters:
  prometheus:
    enabled: false
  file:
    enabled: false
  otel:
    enabled: false
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "PLAINTEXT"
    auto_offset_reset: "earliest"
    topics:
      event: "{0}"
      metric: "aimonitor-metrics"
      log: "aimonitor-logs"
      span: "aimonitor-spans"
    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
""".strip().format(topic_name)
    )
    await isolated_settings.load_from_yaml(config_path)
    registry = ExporterRegistry(batch_size=3)
    kafka_exporter = KafkaExporter(
        kafka_configs=isolated_settings.get_kafka_config(),
        topics={SignalType.EVENT: topic_name},
    )
    registry.register(kafka_exporter)

    assert await kafka_exporter.healthcheck() is True

    _stop_kafka_container()
    await asyncio.sleep(2)
    assert await kafka_exporter.healthcheck() is False

    lost_event = _build_event(tool_name="broker_down_event")
    with pytest.raises(Exception):
        await asyncio.wait_for(kafka_exporter.export([lost_event]), timeout=30)

    _restart_kafka_container()
    assert await _wait_for_kafka(timeout=30)

    assert await kafka_exporter.recover() is True
    assert await kafka_exporter.healthcheck() is True

    event = _build_event(tool_name="broker_recovered_event")
    await kafka_exporter.export([event])
    await asyncio.sleep(0.5)

    configs_consumer = isolated_settings.get_kafka_config().copy()
    configs_consumer.update({"group.id": f"recovery-group-{uuid4()}"})
    configs_consumer.pop("client.id", None)

    consumer = aio.AIOConsumer(consumer_conf=configs_consumer)
    try:
        await consumer.subscribe([topic_name])
        deadline = asyncio.get_running_loop().time() + 20
        message = None
        while asyncio.get_running_loop().time() < deadline:
            message = await consumer.poll(timeout=1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == 1:
                    continue
                pytest.fail(f"Error while consuming recovered Kafka message: {message.error()}")
            break

        assert message is not None, "No event received after Kafka recovery"
        payload = json.loads(message.value())
        assert payload["tool_name"] == event.tool_name
        assert message.key() == kafka_exporter._encode_partition_key(tool_name=event.event_type.value)
    finally:
        await consumer.close()
        await kafka_exporter.close()
        await registry.shutdown()


@pytest.mark.integration
@pytest.mark.kafka
@pytest.mark.asyncio
async def test_kafka_exporter_describe_topics_and_idempotent_closure(tmp_path, isolated_settings, kafka_container):
    config_path = tmp_path / "aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: DEV
tracking:
  enabled: true
  track_metrics: true
  track_events: true
  track_logs: true
exporters:
  prometheus:
    enabled: false
  file:
    enabled: false
  otel:
    enabled: false
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "PLAINTEXT"
    auto_offset_reset: "earliest"
    topics:
      event: "aimonitor-events"
      metric: "aimonitor-metrics"
      log: "aimonitor-logs"
      span: "aimonitor-spans"

    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
    """
    )
    await isolated_settings.load_from_yaml(config_path)
    registry = ExporterRegistry(batch_size=3)
    print(f"[kafka_settings] {isolated_settings.get_kafka_config()}")
    kafka_exporter = KafkaExporter(
        kafka_configs=isolated_settings.get_kafka_config(),
        topics={
            SignalType.EVENT: _TEST_TOPIC,
        }
    )
    registry.register(kafka_exporter)

    events = [_build_event() for _ in range(12)]
    await kafka_exporter.export(
        event_batch=events
    )
    await asyncio.sleep(0.5)
    description = await kafka_exporter.describe()
    assert description["status"] == "healthy"
    assert "message" in description
    assert description["brokers"]


    await kafka_exporter.close()
    await kafka_exporter.close()
    await registry.shutdown()


@pytest.mark.integration
@pytest.mark.kafka
@pytest.mark.asyncio
async def test_kafka_exporter_authenticates_with_sasl_plaintext(kafka_sasl_container):
    kafka_configs = {
        "bootstrap.servers": f"localhost:{_SASL_KAFKA_PORT}",
        "security.protocol": "SASL_PLAINTEXT",
        "sasl.mechanism": "PLAIN",
        "sasl.username": _SASL_KAFKA_USERNAME,
        "sasl.password": _SASL_KAFKA_PASSWORD,
        "client.id": "aimonitor-auth-integration-test",
    }

    invalid_probe = KafkaHealthProbe(
        {**kafka_configs, "sasl.password": "invalid-test-password"}
    )
    try:
        with pytest.raises(KafkaException):
            await invalid_probe.check()
    finally:
        invalid_probe.close()

    exporter = KafkaExporter(
        kafka_configs=kafka_configs,
        topics={SignalType.EVENT: _TEST_TOPIC},
    )
    try:
        assert await exporter.healthcheck() is True
        await exporter.export([_build_event(tool_name="authenticated-tool")])
    finally:
        await exporter.close()