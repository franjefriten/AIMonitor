import asyncio
import socket
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import aio

import aimonitor.core.decorators as decorators_module
from aimonitor.core.decorators import monitor_tool
from aimonitor.core.event import MCPEvent
from aimonitor.core.registry import ExporterRegistry
from aimonitor.exporters.kafka import KafkaExporter
from aimonitor.configs.config import get_settings

settings = get_settings()

def _build_event(tool_name: str = "some_tool", status: str = "success", delta: float = 0.25) -> MCPEvent:
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


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_exporter_sends_events_to_kakfa(tmp_path):
    config_path = tmp_path / "aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: ENV
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
    
    producer:
      acks: "all"
      retries: 3
      linger_ms: 5
      compression: "none"
      batch_size: 2048
      max_workers: 12
    """.strip()
    )
    await settings.load_from_yaml(config_path)
    registry = ExporterRegistry(batch_size=3)
    print(f"[kafka_settings] {settings.get_kafka_config()}")
    kafka_exporter = KafkaExporter(kafka_configs=settings.get_kafka_config())
    registry.register(kafka_exporter)

    events = [_build_event() for _ in range(12)]
    await kafka_exporter.export_batch(
        events=events
    )
    await kafka_exporter.producer.flush()

    print(f"[kafka_exporter_config] {kafka_exporter.kafka_configs}")

    configs_consumer = settings.get_kafka_config().copy()
    configs_consumer.update({
        "group.id": f"test-group-{uuid4()}",
    }) 
    configs_consumer.pop("client.id", None)

    consumer = aio.AIOConsumer(consumer_conf=configs_consumer)
    try:
        await consumer.subscribe(["aimonitor-events"])
        deadline = asyncio.get_running_loop().time() + 15
        msg = None
        while asyncio.get_running_loop().time() < deadline:
            candidate = await consumer.poll(timeout=1.0)
            if candidate is None:
                continue
            if candidate.error():
                if candidate.error().code() == 1:  # _PARTITION_EOF
                    continue
                pytest.fail(f"Error while consuming message: {candidate.error()}")
            msg = candidate
            break

        print(msg)
        if msg is None:
            pytest.fail("No message received from Kafka before the deadline")
        print(msg.value())
        assert msg.value() is not None
    finally:
        await consumer.close()
