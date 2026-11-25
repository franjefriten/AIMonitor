import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

from aimonitor.configs.config import get_settings
from aimonitor.core.event import BaseSignal, SignalType
from aimonitor.core.exceptions import (
    ExporterClosedError,
    ExporterDeliveryError,
    ExporterNotReadyError,
    OptionalDependencyMissingError,
    SignalTypeNotFound,
    UnsupportedSignalError,
)
from aimonitor.exporters.base import BaseExporter, with_retry
from aimonitor.utils.logger import logger

try:
    from confluent_kafka import Producer
except ImportError as exc:
    Producer = None
    _PRODUCER_IMPORT_ERROR = exc
else:
    _PRODUCER_IMPORT_ERROR = None

try:
    from confluent_kafka.aio import AIOProducer
except ImportError as exc:
    AIOProducer = None
    _AIO_PRODUCER_IMPORT_ERROR = exc
else:
    _AIO_PRODUCER_IMPORT_ERROR = None


settings = get_settings()


def _build_topic_map(topics: dict[SignalType, str] | None = None) -> dict[SignalType, str]:
    configured_topics = topics or {}
    return {
        SignalType.EVENT: configured_topics.get(SignalType.EVENT, ""),
        SignalType.METRIC: configured_topics.get(SignalType.METRIC, ""),
        SignalType.SPAN: configured_topics.get(SignalType.SPAN, ""),
        SignalType.LOG: configured_topics.get(SignalType.LOG, ""),
    }


class KafkaHealthProbe:
    """Check broker readiness without publishing an application event."""

    def __init__(self, kafka_configs: dict[str, Any]):
        if Producer is None:
            raise OptionalDependencyMissingError("confluent-kafka") from _PRODUCER_IMPORT_ERROR
        self._producer = Producer(kafka_configs)

    def check_sync(self) -> bool:
        metadata = self._producer.list_topics(timeout=5.0)
        return bool(metadata.brokers)

    async def check(self) -> bool:
        return await asyncio.to_thread(self.check_sync)

    def describe_sync(self) -> dict[str, Any]:
        metadata = self._producer.list_topics(timeout=5.0)
        return {
            "status": "healthy" if metadata.brokers else "unhealthy",
            "message": (
                "KafkaExporter is operational."
                if metadata.brokers
                else "No Kafka brokers reported."
            ),
            "brokers": [broker.host for broker in metadata.brokers.values()],
            "topics": list(metadata.topics.keys()),
        }

    def close(self) -> None:
        self._producer.flush(timeout=5.0)


def _encode_partition_key(tool_name: str) -> bytes:
    """Convert a tool name into a stable byte key for Kafka."""
    if not tool_name:
        return b"default"
    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()
    return digest[:16].encode("utf-8")


def _topic_for_signal(event: BaseSignal, supported_signals: set[SignalType], topics_by_signal: dict[SignalType, str]) -> str:
    try:
        topic = topics_by_signal.get(event.event_type, "")
    except KeyError as exc:
        raise SignalTypeNotFound(str(event.event_type)) from exc
    if event.event_type not in supported_signals:
        raise UnsupportedSignalError(str(event.event_type), "KafkaExporter")
    if not topic:
        logger.warning("No Kafka topic configured for signal type %s", event.event_type)
        return ""
    return topic


class KafkaExporter(BaseExporter):
    def __init__(
        self,
        kafka_configs: dict[str, Any] = settings.get_kafka_config(),
        max_workers: int = 5,
        batch_size: int = 10,
        buffer_timeout: float = 1.0,
        topics: dict[SignalType, str] | None = None,
    ):
        super().__init__()
        if AIOProducer is None:
            raise OptionalDependencyMissingError("confluent-kafka[aio]") from _AIO_PRODUCER_IMPORT_ERROR

        producer_class = AIOProducer
        self.kafka_configs = kafka_configs
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.buffer_timeout = buffer_timeout
        self._topics_by_signal = _build_topic_map(topics)
        self.producer = producer_class(
            producer_conf=self.kafka_configs,
            max_workers=max_workers,
            batch_size=batch_size,
            buffer_timeout=buffer_timeout,
        )
        self._closed = False
        self._health_probe = KafkaHealthProbe(self.kafka_configs)
        logger.info("Kafka producer initialized correctly")

    @staticmethod
    def _encode_partition_key(tool_name: str) -> bytes:
        return _encode_partition_key(tool_name)

    @with_retry
    async def export(self, event_batch: Sequence[BaseSignal]) -> None:
        if self.producer is None or self._closed:
            raise ExporterNotReadyError("Kafka producer is not initialized or is closed")

        futures = []
        for event in event_batch:
            topic = _topic_for_signal(event, self.SUPPORTED_SIGNALS, self._topics_by_signal)
            if not topic:
                continue
            future = await self.producer.produce(
                topic=topic,
                key=self._encode_partition_key(event.event_type.value),
                value=event.model_dump_json().encode("utf-8"),
            )
            futures.append((event.id, future))

        for event_id, future in futures:
            try:
                await future
            except Exception as exc:
                raise ExporterDeliveryError(
                    f"Kafka failed to deliver message for event {event_id}"
                ) from exc

    async def close(self) -> None:
        logger.info("Closing kafka producer and flushing queue...")
        producer = self.producer
        if producer is None or self._closed:
            logger.info("Kafka producer is already closed")
            return None

        try:
            await producer.close()
            await asyncio.to_thread(self._health_probe.close)
            self._closed = True
            logger.info("Kafka producer closed successfully")
        except Exception as exc:
            raise ExporterClosedError("Failed to close Kafka producer") from exc

    async def healthcheck(self) -> bool:
        if self.producer is None or self._closed:
            logger.error("Health check failed for KafkaExporter: producer is closed")
            return False
        try:
            success = await self._health_probe.check()
        except Exception as exc:
            logger.error("Health check failed for KafkaExporter: %s", exc)
            return False
        if success:
            logger.info("Health check passed for KafkaExporter.")
        else:
            logger.error("Health check failed for KafkaExporter.")
        return success

    async def describe(self) -> dict[str, object]:
        try:
            return await asyncio.to_thread(self._health_probe.describe_sync)
        except Exception as exc:
            logger.error("Failed to retrieve Kafka metadata: %s", exc)
            return {
                "status": "unhealthy",
                "message": str(exc),
            }

    async def recover(self) -> bool:
        try:
            await self.close()
            if AIOProducer is None:
                raise OptionalDependencyMissingError(
                    "confluent-kafka[aio]"
                ) from _AIO_PRODUCER_IMPORT_ERROR

            producer_class = AIOProducer
            self.producer = producer_class(
                producer_conf=self.kafka_configs,
                max_workers=self.max_workers,
                batch_size=self.batch_size,
                buffer_timeout=self.buffer_timeout,
            )
            self._closed = False
            self._health_probe = KafkaHealthProbe(self.kafka_configs)
            return True
        except Exception as exc:
            logger.error("Recovery failed for KafkaExporter: %s", exc)
            self.producer = None
            return False
