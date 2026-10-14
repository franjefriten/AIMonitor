import os
import json
from pathlib import Path

import pytest

from aimonitor.bootstrap import initialize_monitor, shutdown_monitor
from aimonitor.configs.config import AIMonitorSettings, get_settings
from aimonitor.core.registry import registry
from aimonitor.telemetry.api import telemetry_producer
from aimonitor.exporters.base import BaseExporter


@pytest.fixture(autouse=True)
def clear_aimonitor_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("AIMONITOR_"):
            monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_initialize_monitor_uses_valid_runtime_fields(tmp_path, monkeypatch):
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
    file_path: "./tmp_runtime_logs"
  otel:
    enabled: true
    service_name: "aimonitor-test"
    span_prefix: "mcp.test"
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.prometheus_enabled is True
    assert settings.prometheus_url is not None
    assert str(settings.prometheus_url).startswith("http://localhost:9000")
    assert settings.file_enabled is True
    assert settings.file_exporter_logs == Path("./tmp_runtime_logs")
    assert settings.otel_mcp_exporter_enabled is True
    assert settings.otel_mcp_service_name == "aimonitor-test"

    class PrometheusStub(BaseExporter):
        def __init__(self, **kwargs):
            pass

        def export_batch(self, event_batch):
            return super().export_batch(event_batch)

        async def healthcheck(self):
            return True

        async def describe(self):
            return {"status": "healthy"}

        async def recover(self):
            return True

    monkeypatch.setattr("bootstrap.PrometheusExporter", PrometheusStub)
    initialized = await initialize_monitor(config_path)
    assert initialized.prometheus_enabled is True
    assert initialized.file_enabled is True

    await registry.shutdown()


@pytest.mark.asyncio
async def test_shutdown_monitor_resets_settings_before_telemetry(monkeypatch):
    settings = get_settings()
    settings.telemetry.inner_telemetry = True
    observed_settings = []

    def observe_reset():
        observed_settings.append(settings.telemetry.inner_telemetry)

    monkeypatch.setattr(telemetry_producer, "reset", observe_reset)

    await shutdown_monitor()

    assert observed_settings == [False]


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

    assert settings.exporters.kafka.enabled is True
    assert settings.exporters.kafka.bootstrap_servers == "localhost:9092"
    assert settings.exporters.kafka.producer.acks == "all"
    assert settings.exporters.kafka.producer.batch_size == 2048
    assert settings.exporters.kafka.producer.max_workers == 12

    await registry.shutdown()


@pytest.mark.asyncio
async def test_kafka_settings_propagate_to_runtime_and_producer_conf(tmp_path):
    config_path = tmp_path / "kafka_runtime_aimonitor.yaml"
    config_path.write_text(
        """
exporters:
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    security_protocol: "SASL_SSL"
    group_id: "aimonitor-test-group"
    max_in_flight_requests_per_connection: 3
    buffer_timeout: 2.5
    sasl:
      mechanism: "PLAIN"
      username: "demo-user"
      password: "demo-pass"
    producer:
      acks: all
      compression: gzip
      linger_ms: 25
      max_workers: 8
      batch_size: 1024
      retries: 7
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.exporters.kafka.enabled is True
    assert settings.exporters.kafka.bootstrap_servers == "localhost:9092"
    assert settings.exporters.kafka.security_protocol == "SASL_SSL"
    assert settings.exporters.kafka.group_id == "aimonitor-test-group"
    assert settings.exporters.kafka.max_in_flight_requests_per_connection == 3
    assert settings.exporters.kafka.buffer_timeout == 2.5
    assert settings.exporters.kafka.producer.acks == "all"
    assert settings.exporters.kafka.producer.compression == "gzip"
    assert settings.exporters.kafka.producer.linger_ms == 25
    assert settings.exporters.kafka.producer.max_workers == 8
    assert settings.exporters.kafka.producer.batch_size == 1024
    assert settings.exporters.kafka.producer.retries == 7

    kafka_conf = settings.get_kafka_config()
    assert kafka_conf["bootstrap.servers"] == "localhost:9092"
    assert kafka_conf["security.protocol"] == "SASL_SSL"
    assert kafka_conf["max.in.flight.requests.per.connection"] == 3
    assert kafka_conf["linger.ms"] == 25
    assert kafka_conf["compression.type"] == "gzip"
    assert kafka_conf["retries"] == 7
    assert kafka_conf["sasl.mechanism"] == "PLAIN"
    assert kafka_conf["sasl.username"] == "demo-user"
    assert kafka_conf["sasl.password"] == "demo-pass"

    await registry.shutdown()


@pytest.mark.asyncio
async def test_json_loader_reads_kafka_settings(tmp_path):
    config_path = tmp_path / "kafka_aimonitor.json"
    config_path.write_text(
        json.dumps(
            {
                "exporters": {
                    "kafka": {
                        "enabled": True,
                        "bootstrap_servers": "localhost:9092",
                        "security_protocol": "SASL_SSL",
                        "group_id": "aimonitor-json-group",
                        "auto_offset_reset": "latest",
                        "retry_policy": 4,
                        "delivery_timeout_ms": 60000,
                        "request_timeout_ms": 15000,
                        "socket_timeout_ms": 12000,
                        "reconnect_backoff_ms": 500,
                        "reconnect_backoff_max_ms": 10000,
                        "max_in_flight_requests_per_connection": 2,
                        "buffer_timeout": 1.5,
                        "sasl": {
                            "mechanism": "PLAIN",
                            "username": "json-user",
                            "password": "json-pass",
                        },
                        "producer": {
                            "acks": "all",
                            "linger_ms": 10,
                            "compression": "snappy",
                            "max_workers": 4,
                            "batch_size": 512,
                        },
                    }
                }
            }
        )
    )

    settings = AIMonitorSettings()
    await settings.load_from_json(config_path)

    assert settings.exporters.kafka.enabled is True
    assert settings.exporters.kafka.bootstrap_servers == "localhost:9092"
    assert settings.exporters.kafka.security_protocol == "SASL_SSL"
    assert settings.exporters.kafka.sasl_mechanism == "PLAIN"
    assert settings.exporters.kafka.sasl_username == "json-user"
    assert settings.exporters.kafka.sasl_password == "json-pass"
    assert settings.exporters.kafka.group_id == "aimonitor-json-group"
    assert settings.exporters.kafka.auto_offset_reset == "latest"
    assert settings.exporters.kafka.retry_policy == 4
    assert settings.exporters.kafka.delivery_timeout_ms == 60000
    assert settings.exporters.kafka.request_timeout_ms == 15000
    assert settings.exporters.kafka.socket_timeout_ms == 12000
    assert settings.exporters.kafka.reconnect_backoff_ms == 500
    assert settings.exporters.kafka.reconnect_backoff_max_ms == 10000
    assert settings.exporters.kafka.max_in_flight_requests_per_connection == 2
    assert settings.exporters.kafka.buffer_timeout == 1.5
    assert settings.exporters.kafka.producer.acks == "all"
    assert settings.exporters.kafka.producer.linger_ms == 10
    assert settings.exporters.kafka.producer.compression == "snappy"
    assert settings.exporters.kafka.producer.max_workers == 4
    assert settings.exporters.kafka.producer.batch_size == 512
    assert settings.exporters.kafka.producer.retries == 4


@pytest.mark.asyncio
async def test_settings_reset_restores_defaults_after_file_load(tmp_path):
    config_path = tmp_path / "loaded.yaml"
    config_path.write_text(
        """
exporters:
  prometheus:
    enabled: true
    url: "http://loaded-host:9000"
telemetry:
  healthcheck_interval: 15
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)
    assert settings.prometheus_enabled is True
    assert settings.healthcheck_interval == 15

    settings.reset()

    assert settings.prometheus_enabled is False
    assert settings.prometheus_url is None
    assert settings.healthcheck_interval == 60


@pytest.mark.asyncio
async def test_initialize_monitor_reads_internal_telemetry_healthcheck_settings(tmp_path):
    config_path = tmp_path / "telemetry_aimonitor.yaml"
    config_path.write_text(
        """
telemetry:
  inner_telemetry: true
  healthcheck_enabled: true
  healthcheck_interval: 15
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.inner_telemetry is True
    assert settings.healthcheck_enabled is True
    assert settings.healthcheck_interval == 15

    await registry.shutdown()


@pytest.mark.asyncio
async def test_nested_config_sections_are_available_for_runtime_and_compatibility(tmp_path):
    config_path = tmp_path / "nested_aimonitor.yaml"
    config_path.write_text(
        """
app:
  env: STG
telemetry:
  inner_telemetry: true
  healthcheck_enabled: true
  healthcheck_interval: 25
exporters:
  kafka:
    enabled: true
    bootstrap_servers: "localhost:9092"
    producer:
      acks: all
      max_workers: 7
      batch_size: 256
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.app.env_code == "STG"
    assert settings.telemetry.inner_telemetry is True
    assert settings.telemetry.healthcheck_enabled is True
    assert settings.telemetry.healthcheck_interval == 25
    assert settings.exporters.kafka.enabled is True
    assert settings.exporters.kafka.bootstrap_servers == "localhost:9092"
    assert settings.exporters.kafka.producer.max_workers == 7
    assert settings.exporters.kafka.producer.batch_size == 256

    await registry.shutdown()


@pytest.mark.asyncio
async def test_environment_variables_take_priority_over_yaml_values(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMONITOR_PROMETHEUS_ENABLED", "true")
    monkeypatch.setenv("AIMONITOR_PROMETHEUS_URL", "http://env-host:9000")

    config_path = tmp_path / "env_precedence.yaml"
    config_path.write_text(
        """
exporters:
  prometheus:
    enabled: true
    url: "http://file-host:9000"
""".strip()
    )

    settings = AIMonitorSettings()
    await settings.load_from_yaml(config_path)

    assert settings.prometheus_enabled is True
    assert str(settings.prometheus_url).startswith("http://env-host:9000")
    assert settings.exporters.prometheus.enabled is True
    assert str(settings.exporters.prometheus.url).startswith("http://env-host:9000")

    await registry.shutdown()
