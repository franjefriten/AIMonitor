from pathlib import Path

import pytest

from bootstrap import initialize_monitor
from configs.config import AIMonitorSettings


@pytest.mark.asyncio
async def test_initialize_monitor_uses_valid_runtime_fields(tmp_path):
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
    enabled: true
    url: "http://localhost:9000"
  file:
    enabled: true
    path: "./tmp_runtime_logs"
  otel:
    enabled: true
    service_name: "aimonitor-test"
    span_prefix: "mcp.test"
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.prometheus_enabled is True
    assert str(settings.prometheus_url) == "http://localhost:9000/"
    assert settings.file_enabled is True
    assert settings.file_exporter_logs == Path("./tmp_runtime_logs")
    assert settings.otel_mcp_exporter_enabled is True
    assert settings.otel_mcp_service_name == "aimonitor-test"

    initialized = await initialize_monitor(config_path)
    assert initialized.prometheus_enabled is True
    assert initialized.file_enabled is True


@pytest.mark.asyncio
async def test_initialize_monitor_reads_kafka_worker_and_batch_settings(tmp_path):
    config_path = tmp_path / "kafka_aimonitor.yaml"
    config_path.write_text(
        """
exporters:
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    producer:
      acks: all
      batch_size: 2048
      max_workers: 12
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.kafka_enabled is True
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.kafka_batch_size == 2048
    assert settings.kafka_max_workers == 12
