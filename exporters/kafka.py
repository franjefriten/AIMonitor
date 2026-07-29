try:
    from confluent_kafka.aio import AIOProducer
except ImportError as e:
    raise ImportError(
        "confluent_kafka is required for KafkaMetricsExporters. Install it with pip install .[kafka] uv sync --extra kafka"
    )
   
from exporters.base import BaseExporter, with_retry
from core.event import MCPEvent

import socket
import json
from hashlib import s
from configs.config import get_settings
from utils.logger import logger

settings = get_settings()

class KafkaMetricsExporter(BaseExporter):

    def __init__(self, topic: str = "aimonitor-events", kafka_configs: dict = settings.get_kafka_config()):
        super().__init__()
        self.kafka_configs = kafka_configs
        self.topic = topic
        try:
            self.producer = AIOProducer(config=self.kafka_configs)
            logger.info("Kafka producer intialized correctly")
        except Exception as e:
            logger.error("Kafka producer could not be initialized")
            raise
    
    @staticmethod
    def _report_delivery(err: str | None, msg: str | None): # helper function for acked
        if err is not None:
            logger.info(f"Failed to deliver message: {str(msg)}")
        else:
            logger.info(f"Event delivered! {str(msg)}")

    @with_retry
    async def send(self, event: MCPEvent):
        event_data = json.dumps(MCPEvent.model_dump_json()).encode('utf-8')
        key = event.tool_name

        try:
            await self.producer.produce(
                topic=self.topic,
                key=key,
                value=event_data,
                partition=key,
                callback=self._report_delivery
            )
            await self.producer.poll(0) # force callback call
        except BufferError as exc:
            logger.warning("Kafka queue overloaded (BufferError), forcing flush...")
            await self.producer.flush()
        except Exception as e:
            logger.error(f"Unexpected error happened: {repr(e)}")
    
    async def close(self) -> None:
        logger.info("CLosing kafka producer and flushing queue...")
        await self.producer.flush()
