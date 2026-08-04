import asyncio
import socket
from datetime import datetime, UTC
from typing import Any

import httpx
import pytest
from confluent_kafka import aio

import core.decorators as decorators_module
from core.decorators import monitor_tool
from core.event import MCPEvent
from core.registry import ExporterRegistry
from exporters.kafka import KafkaExporter
from configs.config import get_settings

settings = get_settings()

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
async def test_kafka_exporter_sends_events_to_kakfa():
    registry = ExporterRegistry(batch_size=3)
    kafka_exporter = KafkaExporter(topic="test-topic", kafka_configs=settings.get_kafka_config())
    registry.register(kafka_exporter)

    events = [_build_event() for _ in range(12)]
    await kafka_exporter.export_batch(
        events=events
    )

    await asyncio.sleep(2)  # Allow some time for the events to be sent

    print(f"[kafka_exporter_config] {kafka_exporter.kafka_configs}")

    configs_consumer = settings.get_kafka_config().copy()
    configs_consumer.update({
        "group.id": "test-group",
    }) 
    configs_consumer.pop("client.id", None)

    consumer = aio.AIOConsumer(consumer_conf=configs_consumer)
    await consumer.subscribe(["test-topic"])
    await asyncio.sleep(1.0)

    msg = await consumer.poll(timeout=5.0)
    print(msg)
    if msg is None:
        pytest.fail("No message received from Kafka")
    if msg.error():
        if msg.error().code() == 1:  # _PARTITION_EOF
            pytest.fail("Reached end of partition, no message received")
        pytest.fail(f"Error while consuming message: {msg.error()}")
    
    print(msg.value())
    assert msg.value() is not None






