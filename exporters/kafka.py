try:
    from confluent_kafka.aio import AIOProducer
except ImportError as e:
    raise ImportError(
        "confluent_kafka is required for KafkaMetricsExporters. Install it with pip install .[kafka] uv sync --extra kafka"
    )
   
from exporters.base import BaseExporter, with_retry
from core.event import MCPEvent

import socket
import hashlib
import json
from typing import List, Optional
import string

from configs.config import get_settings
from utils.logger import logger

settings = get_settings()

def _encode_partition_key(tool_name: str) -> bytes:
    """
    Convert a tool_name into a stable byte key for Kafka.
    Kafka uses the key to determine the partitioning internally, so the
    value is a deterministic byte-string rather than an arbitrary integer.
    """
    if not tool_name:
        return b"default"

    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()
    return digest[:16].encode("utf-8")


class KafkaExporter(BaseExporter):

    def __init__(
            self, 
            topic: str = "aimonitor-events", 
            kafka_configs: dict = settings.get_kafka_config(),
            max_workers: int = 5,
            batch_size: int = 10,
            buffer_timeout: float = 1.0,
        ):
        super().__init__()
        self.kafka_configs = kafka_configs
        self.topic = topic
        try:
            self.producer = AIOProducer(
                producer_conf=self.kafka_configs,
                max_workers=max_workers,
                batch_size=batch_size,
                buffer_timeout=buffer_timeout,
            )
            logger.info("Kafka producer initialized correctly")
        except Exception:
            logger.error("Kafka producer could not be initialized")
            raise

    @staticmethod
    def _report_delivery(err: str | None, msg: str | None): # helper function for acked
        if err is not None:
            logger.info(f"Failed to deliver message: {str(msg)}")
        else:
            logger.info(f"Event delivered! {str(msg)}")

    @staticmethod
    def _encode_partition_key(tool_name: str) -> bytes:
        """
        Convert a tool_name into a stable byte key for Kafka.
        Kafka uses the key to determine the partitioning internally, so the
        value is a deterministic byte-string rather than an arbitrary integer.
        """
        return _encode_partition_key(tool_name)

    async def export_batch(self, events: List[MCPEvent]):
        for event in events:
            event_data = json.dumps(event.model_dump_json()).encode("utf-8")
            key = self._encode_partition_key(event.tool_name)

            try:
                await self.producer.produce(
                    topic=self.topic,
                    key=key,
                    value=event_data,
                    callback=self._report_delivery,
                )
                await self.producer.poll(0)
            except BufferError:
                logger.warning("Kafka queue overloaded (BufferError), forcing flush...")
                await self.producer.flush()
            except Exception as exc:
                logger.error(f"Unexpected error happened: {repr(exc)}")

    async def close(self) -> None:
        logger.info("Closing kafka producer and flushing queue...")
        await self.producer.flush()
