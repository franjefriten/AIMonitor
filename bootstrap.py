from pathlib import Path

from configs.config import AIMonitorSettings, get_settings
from core.registry import registry
from exporters.file import FileExporter
from exporters.kafka import KafkaExporter
from exporters.opentelemetry import OpenTelemetryExporter
from exporters.prometheus import PrometheusExporter
from exporters.redis import RedisExporter
from exporters.sqlite import SQLiteExporter


async def initialize_monitor(config_path: str | Path | None = None) -> AIMonitorSettings:
    """Load runtime config and register only enabled exporters."""
    settings = get_settings()

    if config_path is not None:
        path = Path(config_path)
        if path.suffix.lower() in {".yaml", ".yml"}:
            await settings.load_from_yaml(path)
        elif path.suffix.lower() == ".json":
            await settings.load_from_json(path)

    exporters = []

    if settings.redis_enabled and settings.redis_url is not None:
        exporters.append(RedisExporter(settings.redis_url))

    if settings.sqlite_enabled and settings.sqlite_uri is not None:
        exporters.append(SQLiteExporter(settings.sqlite_uri))

    if settings.kafka_enabled and settings.kafka_bootstrap_servers:
        kafka_settings = settings.get_kafka_config()
        exporters.append(
            KafkaExporter(
                kafka_configs=kafka_settings,
                max_workers=settings.kafka_max_workers or 5,
                batch_size=settings.kafka_batch_size or 10,
                buffer_timeout=settings.kafka_buffer_timeout if settings.kafka_buffer_timeout is not None else 1.0,
            )
        )

    if settings.otel_mcp_exporter_enabled:
        exporters.append(
            OpenTelemetryExporter(
                enabled=True,
                service_name=settings.otel_mcp_service_name,
                span_prefix=settings.otel_mcp_span_prefix,
            )
        )

    if settings.prometheus_enabled and settings.prometheus_url is not None:
        exporters.append(PrometheusExporter(address=str(settings.prometheus_url), registry=None))

    if settings.file_enabled and settings.file_exporter_logs is not None:
        exporters.append(FileExporter(settings.file_exporter_logs))

    for exporter in exporters:
        registry.register(exporter)

    return settings