from pathlib import Path

from aimonitor.configs.config import AIMonitorSettings, get_settings
from aimonitor.core.registry import registry
from aimonitor.exporters.file import FileExporter
from aimonitor.exporters.kafka import KafkaExporter
from aimonitor.exporters.opentelemetry import OpenTelemetryExporter
from aimonitor.exporters.prometheus import PrometheusExporter
from aimonitor.exporters.sqlite import SQLiteExporter
from aimonitor.utils.logger import setup_logging


async def initialize_monitor(config_path: str | Path | None = None) -> AIMonitorSettings:
    """Load runtime config and register only enabled exporters."""
    settings = get_settings()

    await registry.shutdown()
    settings.reset()

    if config_path is not None:
        path = Path(config_path)
        if path.suffix.lower() in {".yaml", ".yml"}:
            await settings.load_from_yaml(path)
        elif path.suffix.lower() == ".json":
            await settings.load_from_json(path)

    setup_logging(env_code=settings.app.env_code)

    from telemetry.api import telemetry_producer
    telemetry_producer.reset()

    exporters = []

    if settings.exporters.sqlite.enabled and settings.exporters.sqlite.uri is not None:
        exporters.append(SQLiteExporter(settings.exporters.sqlite.uri))

    if settings.exporters.kafka.enabled and settings.exporters.kafka.bootstrap_servers:
        kafka_settings = settings.get_kafka_config()
        exporters.append(
            KafkaExporter(
                kafka_configs=kafka_settings,
                max_workers=settings.exporters.kafka.producer.max_workers or 5,
                batch_size=settings.exporters.kafka.producer.batch_size or 10,
                buffer_timeout=settings.exporters.kafka.buffer_timeout if settings.exporters.kafka.buffer_timeout is not None else 1.0,
            )
        )

    if settings.exporters.otel.enabled:
        exporters.append(
            OpenTelemetryExporter(
                enabled=True,
                service_name=settings.exporters.otel.service_name,
                span_prefix=settings.exporters.otel.span_prefix,
            )
        )

    if settings.exporters.prometheus.enabled and settings.exporters.prometheus.url is not None:
        exporters.append(PrometheusExporter(address=str(settings.exporters.prometheus.url), registry=None))

    if settings.exporters.file.enabled and settings.exporters.file.path is not None:
        exporters.append(FileExporter(settings.exporters.file.path))

    for exporter in exporters:
        registry.register(exporter)

    return settings

async def shutdown_monitor() -> None:
    """Shutdown all registered exporters and the registry."""
    await registry.shutdown()
    settings = get_settings()
    settings.reset()

    from telemetry.api import telemetry_producer
    telemetry_producer.reset()
