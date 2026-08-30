from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional
from urllib import parse
import socket

import aiofiles
import json
import yaml
from pydantic import AnyUrl, Field, FilePath, HttpUrl, field_validator, AliasChoices, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

import logging
from logging import getLogger, config

_VALID_URLS = ["mongodb://", "redis://", "postgres://", "postgresql://", "http://", "https://"]

_REDIS_URL_ALIASES = frozenset({"redis_url", "redis-url", "redisUrl"})
_MONGODB_URL_ALIASES = frozenset({"mongodb_url", "mongodb-url", "mongodbUrl"})
_POSTGRES_URL_ALIASES = frozenset({"postgres_url", "postgres-url", "postgresUrl"})
_PROMETHEUS_URL_ALIASES = frozenset({"prometheus_url", "prometheus-url", "prometheusUrl"})
_SQLITE_URI_ALIASES = frozenset({"sqlite_uri", "sqlite-uri", "sqliteUri"})
_MAX_MB_PER_FILE_ALIASES = frozenset({"max_mb_per_file", "max-mb-per-file", "maxMbPerFile", "max_mb", "max-mb", "maxMb"})
_ENV_CODE_ALIASES = frozenset({"env", "envCode", "env-code", "env_code", "environment"})
_LOGGER_LEVEL_ALIASES = frozenset({"log", "logger", "log-level", "log_level", "logLevel"})
_RETRIES_POLICY_ALIASES = frozenset({"retries_policy", "retries-policy", "retriesPolicy", "retries"})
_TRACK_METRICS_ALIASES = frozenset({"metrics", "track_metrics", "trackMetrics", "track-metrics"})
_TRACK_EVENTS_ALIASES = frozenset({"events", "track_events", "trackEvents", "track-events"})
_TRACK_LOGS_ALIASES = frozenset({"logs", "track_logs", "trackLogs", "track-logs"})
_SENSITIVE_KEYS_ALIASES = frozenset({"sensitive_keys", "sensitive-keys", "sensitiveKeys"})
_FILE_EXPORTER_LOGS_ALIASES = frozenset({"file", "uri", "url", "path", "file_path", "file-path", "filePath"})
_INNER_TELEMETRY_ALIASES = frozenset({
    "inner_telemetry",
    "innerTelemetry",
    "inner-telemetry",
    "telemetry",
    "track_telemetry",
    "trackTelemetry",
    "track-telemetry",
    "enable-telemetry",
    "enableTelemetry",
    "enable_telemetry"
})
_HEALTHCHECK_ENABLED_ALIASES = frozenset({
    "healthcheck_enabled",
    "healthcheck-enabled",
    "healthcheckEnabled",
    "exporter_healthcheck_enabled",
    "exporterHealthcheckEnabled",
    "enable_healthcheck",
    "enableHealthcheck",
})
_HEALTHCHECK_INTERVAL_ALIASES = frozenset({
    "healthcheck_interval",
    "healthcheck-interval",
    "healthcheckInterval",
    "exporter_healthcheck_interval",
    "exporterHealthcheckInterval",
    "telemetry_healthcheck_interval",
    "telemetryHealthcheckInterval",
})
_OTEL_MCP_EXPORTER_ENABLED_ALIASES = frozenset({
    "otel_mcp_exporter_enabled",
    "otel-mcp-exporter-enabled",
    "otelMcpExporterEnabled",
    "otel_exporter",
    "open_telemetry_exporter",
    "openTelemetryExporter",
    "mcp_otel_exporter",
    "mcp-otel-exporter"
})
_OTEL_MCP_SERVICE_NAME_ALIASES = frozenset({
    "otel_mcp_service_name",
    "otel-mcp-service-name",
    "otelMcpServiceName",
    "otel_service_name",
    "service_name",
    "serviceName"
})
_OTEL_MCP_SPAN_PREFIX_ALIASES = frozenset({
    "otel_mcp_span_prefix",
    "otel-mcp-span-prefix",
    "otelMcpSpanPrefix",
    "otel_span_prefix",
    "span_prefix",
    "spanPrefix"
})

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_config_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s - %(filename)s:%(lineno)d: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "filename": "mcp_monitor.log",
            "mode": "a",
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
}
config.dictConfig(config=LOGGING_CONFIG)
config_logger = getLogger("AIMonitor.Config") # avoid circular import

class _VALID_ENV_CODE(str, Enum):
    ENV = "ENV"
    STG = "STG"
    PRO = "PRO"


class AIMonitorSettings(BaseSettings):
    """
    Settings class for the module, handles URLs to services such as Redis, MongoDB and others.
    It also handles the security settings for sensitive data that should be redacted in payloads.
    """

    model_config = SettingsConfigDict(
        env_prefix="AIMONITOR_",
        env_file=(".env.prod", ".env.stg", ".env.dev", ".env.local", ".env"),
        populate_by_name=True,
        extra="ignore",
    )

    sensitive_keys: set[str] = Field(
        default_factory=lambda: {
            "password",
            "token",
            "api_key",
            "secret",
            "apikey",
            "access_token",
            "client_secret",
            "private_key",
            "credentials",
        },
        description="Sensitive keys to censor in data",
        validation_alias=AliasChoices(*_SENSITIVE_KEYS_ALIASES)
    )
    # redis
    redis_enabled: bool = Field(
        default=False,
        description="Whether Redis exporter is enabled",
    )
    redis_url: Optional[AnyUrl] = Field(
        default=None,
        description="Redis URL to use",
        validation_alias=AliasChoices(*_REDIS_URL_ALIASES)
    )
    # mongo
    mongodb_enabled: bool = Field(
        default=False,
        description="Whether MongoDB exporter is enabled",
    )
    mongodb_url: Optional[AnyUrl] = Field(
        default=None,
        description="MongoDB URL to use",
        validation_alias=AliasChoices(*_MONGODB_URL_ALIASES)
    )
    # postgres
    postgres_enabled: bool = Field(
        default=False,
        description="Whether Postgres exporter is enabled",
    )
    postgres_url: Optional[AnyUrl] = Field(
        default=None,
        description="Postgres URL to use",
        validation_alias=AliasChoices(*_POSTGRES_URL_ALIASES)
    )
    # prometheus
    prometheus_enabled: bool = Field(
        default=False,
        description="Whether Prometheus exporter is enabled",
    )
    prometheus_url: Optional[HttpUrl] = Field(
        default=None,
        description="Prometheus URL to use",
        validation_alias=AliasChoices(*_PROMETHEUS_URL_ALIASES)
    )
    # kafka
    kafka_enabled: bool = Field(
        default=False,
        description="Whether Kafka exporter is enabled",
    )
    kafka_bootstrap_servers: Optional[str] = Field(default=None, description="Kafka bootstrap servers")
    kafka_security_protocol: Optional[str] = Field(default=None, description="Security protocol (PLAINTEXT, SASL_SSL, etc.)")
    kafka_sasl_mechanism: Optional[str] = Field(default=None, description="SASL mechanism (e.g. PLAIN, SCRAM-SHA-256)")
    kafka_sasl_username: Optional[SecretStr] = Field(default=None, description="Cluster API Key / Username")
    kafka_sasl_password: Optional[SecretStr] = Field(default=None, description="Cluster API Secret / Password")
    kafka_group_id: str = Field(default="aimonitor-group", description="Consumer group id")
    kafka_auto_offset_reset: Optional[str] = Field(default=None, description="Auto offset reset")
    kafka_retry_policy: Optional[int] = Field(default=None, description="Number of retries for Kafka producer")
    kafka_delivery_timeout_ms: Optional[int] = Field(default=None, description="Delivery timeout in milliseconds for Kafka producer")
    kafka_request_timeout_ms: Optional[int] = Field(default=None, description="Request timeout in milliseconds for Kafka producer")
    kafka_socket_timeout_ms: Optional[int] = Field(default=None, description="Socket timeout in milliseconds for Kafka producer")
    kafka_reconnect_backoff_ms: Optional[int] = Field(default=None, description="Reconnect backoff in milliseconds for Kafka producer")
    kafka_reconnect_backoff_max_ms: Optional[int] = Field(default=None, description="Max reconnect backoff in milliseconds for Kafka producer")
    kafka_compression_type: Optional[str] = Field(default=None, description="Compression type for Kafka producer (none, gzip, snappy, lz4, zstd)")
    kafka_producer_acks: Optional[str] = Field(default=None, description="Acknowledgment level for Kafka producer (none, leader, all)")
    kafka_producer_linger_ms: Optional[int] = Field(default=None, description="Linger time in milliseconds for Kafka producer to allow batching of messages")
    kafka_max_in_flight_requests_per_connection: Optional[int] = Field(default=None, description="Maximum number of in-flight requests per connection for Kafka producer to maintain order")
    kafka_max_workers: Optional[int] = Field(default=None, description="Maximum number of concurrent workers for Kafka producer")
    kafka_batch_size: Optional[int] = Field(default=None, description="Batch size for Kafka producer")
    kafka_buffer_timeout: Optional[float] = Field(default=None, description="Buffer timeout in seconds for Kafka producer to flush messages")

    # sqlite
    sqlite_enabled: bool = Field(
        default=False,
        description="Whether SQLite exporter is enabled",
    )
    sqlite_uri: Optional[Path] = Field(
        default=None,
        description="SQLite path to use",
        validation_alias=AliasChoices(*_SQLITE_URI_ALIASES)
    )
    max_mb_per_file: Optional[float] = Field(
        default=10.0, 
        description="Max file size in megabytes",
        gt=0,
        validation_alias=AliasChoices(*_MAX_MB_PER_FILE_ALIASES)
    )

    retries_policy: Optional[int] = Field(
        default=3, 
        description="Number of retries for exporters", 
        ge=0,
        validation_alias=AliasChoices(*_RETRIES_POLICY_ALIASES)
    )
    env_code: Optional[_VALID_ENV_CODE] = Field(
        default=_VALID_ENV_CODE.ENV, 
        description="Environment code used for configs such as logs",
        validation_alias=AliasChoices(*_ENV_CODE_ALIASES)    
    )
    logger_level: str = Field(
        default="INFO",
        description="Logger level used for the module inner console logs",
        validation_alias=AliasChoices(*_LOGGER_LEVEL_ALIASES)
    )
    # file
    file_enabled: bool = Field(
        default=False,
        description="Whether File exporter is enabled",
    )
    file_exporter_logs: Optional[Path] = Field(
        default=Path("./logs"), 
        description="Folder to which file exporter logs will be dumped into",
        validation_alias=AliasChoices(*_FILE_EXPORTER_LOGS_ALIASES)
    )

    # tracking validations
    enabled: bool = Field(
        default=True,
        description="Whether general tracking of the module is off or on",
    )
    track_metrics: bool = Field(
        default=True,
        description="Whether to track metrics",
        validation_alias=AliasChoices(*_TRACK_METRICS_ALIASES)
    )
    track_events: bool = Field(
        default=True,
        description="Whether to track events",
        validation_alias=AliasChoices(*_TRACK_EVENTS_ALIASES)
    )
    track_logs: bool = Field(
        default=True,
        description="Whether to track logs",
        validation_alias=AliasChoices(*_TRACK_LOGS_ALIASES)
    )

    # inner telemetry
    inner_telemetry: bool = Field(
        default=False,
        description="Option to track telemetry of the module itself, useful for debugging and development",
        validation_alias=AliasChoices(*_INNER_TELEMETRY_ALIASES)
    )
    healthcheck_enabled: bool = Field(
        default=True,
        description="Whether the registry background exporter healthcheck loop is enabled",
        validation_alias=AliasChoices(*_HEALTHCHECK_ENABLED_ALIASES),
    )
    healthcheck_interval: int = Field(
        default=60,
        description="Seconds between exporter health checks when the registry background loop is enabled",
        ge=1,
        validation_alias=AliasChoices(*_HEALTHCHECK_INTERVAL_ALIASES),
    )

    # OpenTelemetry exporter for monitored MCP events (separate from SDK internal telemetry)
    otel_enabled: bool = Field(
        default=False,
        description="Whether OpenTelemetry exporter is enabled for MCP events",
    )
    otel_mcp_exporter_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry exporter for MCP events captured by AIMonitor",
        validation_alias=AliasChoices(*_OTEL_MCP_EXPORTER_ENABLED_ALIASES),
    )
    otel_mcp_service_name: str = Field(
        default="aimonitor-mcp",
        description="OpenTelemetry service name used by the MCP events exporter",
        validation_alias=AliasChoices(*_OTEL_MCP_SERVICE_NAME_ALIASES),
    )
    otel_mcp_span_prefix: str = Field(
        default="mcp.tool",
        description="Span name prefix for monitored MCP tool events",
        validation_alias=AliasChoices(*_OTEL_MCP_SPAN_PREFIX_ALIASES),
    )


    async def load_from_yaml(self, yaml_file_path: str | Path) -> None:
        yaml_file_path = Path(yaml_file_path)
        if not yaml_file_path.exists():
            config_logger.error("YAML config file was not found")
            raise FileNotFoundError("YAML config file was not found")

        async with aiofiles.open(yaml_file_path, mode="r", encoding="utf-8") as file:
            data = yaml.safe_load(await file.read()) or {}

        if data:
            # app
            flattened_data = {}
            app_data: dict = data.get("app", {})
            env_code = next(iter(app_data.get(env_label) for env_label in _ENV_CODE_ALIASES if env_label in app_data), None)
            logger_level = next(iter(app_data.get(logs_label) for logs_label in _LOGGER_LEVEL_ALIASES if logs_label in app_data), None)
            if env_code:
                flattened_data["env_code"] = env_code
            if logger_level:
                flattened_data["logger_level"] = logger_level
            
            # tracking
            tracking_data: dict = data.get("tracking", {})
            enabled = tracking_data.get("enabled", None)
            track_metrics = next(iter(tracking_data.get(metrics_label) for metrics_label in _TRACK_METRICS_ALIASES if metrics_label in tracking_data), None)
            track_events = next(iter(tracking_data.get(events_label) for events_label in _TRACK_EVENTS_ALIASES if events_label in tracking_data), None)
            track_logs = next(iter(tracking_data.get(logs_label) for logs_label in _TRACK_LOGS_ALIASES if logs_label in tracking_data), None)
            if enabled is not None:
                flattened_data["enabled"] = enabled
            if track_metrics is not None:
                flattened_data["track_metrics"] = track_metrics
            if track_events is not None:
                flattened_data["track_events"] = track_events
            if track_logs is not None:
                flattened_data["track_logs"] = track_logs

            # inner telemetry
            telemetry_data: dict = data.get("telemetry", {})
            inner_telemetry = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _INNER_TELEMETRY_ALIASES if telemetry_label in telemetry_data), None)
            if inner_telemetry is not None:
                flattened_data["inner_telemetry"] = inner_telemetry
            healthcheck_enabled = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _HEALTHCHECK_ENABLED_ALIASES if telemetry_label in telemetry_data), None)
            if healthcheck_enabled is not None:
                flattened_data["healthcheck_enabled"] = healthcheck_enabled
            healthcheck_interval = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _HEALTHCHECK_INTERVAL_ALIASES if telemetry_label in telemetry_data), None)
            if healthcheck_interval is not None:
                flattened_data["healthcheck_interval"] = healthcheck_interval
            
            # security
            security_data: dict = data.get("security", {})
            sensitive_keys = next(iter(security_data.get(keys_label) for keys_label in _SENSITIVE_KEYS_ALIASES if keys_label in security_data), None)
            if sensitive_keys is not None:
                flattened_data["sensitive_keys"] = sensitive_keys

            # exporters
            exporters_data: dict = data.get("exporters", {})
            # redis
            redis: dict = exporters_data.get("redis", {})
            redis_enabled = redis.get("enabled", False)
            if redis_enabled:
                flattened_data["redis_enabled"] = redis_enabled
                redis_url = redis.get("url")
                if redis_url is not None:
                    flattened_data["redis_url"] = redis_url
            else:
                flattened_data["redis_enabled"] = False
            # mongodb
            mongodb: dict = exporters_data.get("mongodb", {})
            mongodb_enabled: bool = mongodb.get("enabled", False)
            if mongodb_enabled:
                flattened_data["mongodb_enabled"] = True
                mongodb_url = mongodb.get("url")
                if mongodb_url is not None:
                    flattened_data["mongodb_url"] = mongodb_url
            else:
                flattened_data["mongodb_enabled"] = False
            # postgres
            postgres: dict = exporters_data.get("postgres", {})
            postgres_enabled: bool = postgres.get("enabled", False)
            postgres_url = postgres.get("url")
            if postgres_enabled:
                flattened_data["postgres_enabled"] = True
                if postgres_url is not None:
                    flattened_data["postgres_url"] = postgres_url
            else:
                flattened_data["postgres_enabled"] = False
            # prometheus
            prometheus: dict = exporters_data.get("prometheus", {})
            prometheus_enabled: bool = prometheus.get("enabled", False)
            if prometheus_enabled:
                flattened_data["prometheus_enabled"] = True
                prometheus_url = prometheus.get("url")
                if prometheus_url is not None:
                    flattened_data["prometheus_url"] = prometheus_url
            else:
                flattened_data["prometheus_enabled"] = False
            # kafka
            kafka: dict = exporters_data.get("kafka", {})
            if kafka.get("enabled"):
                flattened_data["kafka_enabled"] = True
                kafka_bootstrap_servers = kafka.get("bootstrap_servers")
                if kafka_bootstrap_servers is not None:
                    flattened_data["kafka_bootstrap_servers"] = kafka_bootstrap_servers
                kafka_security_protocol = kafka.get("security_protocol")
                if kafka_security_protocol is not None:
                    flattened_data["kafka_security_protocol"] = kafka_security_protocol
                kafka_auto_offset_reset = kafka.get("auto_offset_reset")
                if kafka_auto_offset_reset is not None:
                    flattened_data["kafka_auto_offset_reset"] = kafka_auto_offset_reset
                kafka_retry_policy = kafka.get("retry_policy")
                if kafka_retry_policy is not None:
                    flattened_data["kafka_retry_policy"] = kafka_retry_policy
                kafka_delivery_timeout_ms = kafka.get("delivery_timeout_ms")
                if kafka_delivery_timeout_ms is not None:
                    flattened_data["kafka_delivery_timeout_ms"] = kafka_delivery_timeout_ms
                kafka_request_timeout_ms = kafka.get("request_timeout_ms")
                if kafka_request_timeout_ms is not None:
                    flattened_data["kafka_request_timeout_ms"] = kafka_request_timeout_ms
                kafka_socket_timeout_ms = kafka.get("socket_timeout_ms")
                if kafka_socket_timeout_ms is not None:
                    flattened_data["kafka_socket_timeout_ms"] = kafka_socket_timeout_ms
                kafka_reconnect_backoff_ms = kafka.get("reconnect_backoff_ms")
                if kafka_reconnect_backoff_ms is not None:
                    flattened_data["kafka_reconnect_backoff_ms"] = kafka_reconnect_backoff_ms
                kafka_reconnect_backoff_max_ms = kafka.get("reconnect_backoff_max_ms")
                if kafka_reconnect_backoff_max_ms is not None:
                    flattened_data["kafka_reconnect_backoff_max_ms"] = kafka_reconnect_backoff_max_ms
                kafka_sasl = kafka.get("sasl")
                if kafka_sasl is not None:
                    kafka_sasl_mechanism = kafka_sasl.get("mechanism")
                    if kafka_sasl_mechanism is not None:
                        flattened_data["kafka_sasl_mechanism"] = kafka_sasl_mechanism
                    kafka_sasl_username = kafka_sasl.get("username")
                    if kafka_sasl_username is not None:
                        flattened_data["kafka_sasl_username"] = kafka_sasl_username
                    kafka_sasl_password = kafka_sasl.get("password")
                    if kafka_sasl_password is not None:
                        flattened_data["kafka_sasl_password"] = SecretStr(kafka_sasl_password)
                kakfa_producer = kafka.get("producer")
                if kakfa_producer is not None:
                    kafka_producer_acks = kakfa_producer.get("acks")
                    if kafka_producer_acks is not None:
                        flattened_data["kafka_producer_acks"] = kafka_producer_acks
                    kafka_retries = kakfa_producer.get("retries")
                    if kafka_retries is not None and isinstance(kafka_retries, int):
                        flattened_data["kafka_retry_policy"] = kafka_retries
                    kafka_compression_type = kakfa_producer.get("compression")
                    if kafka_compression_type is not None:
                        flattened_data["kafka_compression_type"] = kafka_compression_type
                    kafka_linger_ms = kakfa_producer.get("linger_ms")
                    if kafka_linger_ms is not None and isinstance(kafka_linger_ms, int):
                        flattened_data["kafka_linger_ms"] = kafka_linger_ms
                    kafka_max_workers = kakfa_producer.get("max_workers")
                    if kafka_max_workers is not None and isinstance(kafka_max_workers, int):
                        flattened_data["kafka_max_workers"] = kafka_max_workers
                    kafka_batch_size = kakfa_producer.get("batch_size")
                    if kafka_batch_size is not None and isinstance(kafka_batch_size, int):
                        flattened_data["kafka_batch_size"] = kafka_batch_size
                kafka_max_in_flight_requests_per_connection = kafka.get("max_in_flight_requests_per_connection")
                if kafka_max_in_flight_requests_per_connection is not None and isinstance(kafka_max_in_flight_requests_per_connection, int):
                    flattened_data["kafka_max_in_flight_requests_per_connection"] = kafka_max_in_flight_requests_per_connection
                kafka_max_workers = kafka.get("max_workers")
                if kafka_max_workers is not None and isinstance(kafka_max_workers, int):
                    flattened_data["kafka_max_workers"] = kafka_max_workers
                kafka_batch_size = kafka.get("batch_size")
                if kafka_batch_size is not None and isinstance(kafka_batch_size, int):
                    flattened_data["kafka_batch_size"] = kafka_batch_size
                kafka_buffer_timeout = kafka.get("buffer_timeout")
                if kafka_buffer_timeout is not None and isinstance(kafka_buffer_timeout, (int, float)):
                    flattened_data["kafka_buffer_timeout"] = kafka_buffer_timeout
            else:
                flattened_data["kafka_enabled"] = False
            # open telemetry
            otel: dict = exporters_data.get("otel", {})
            otel_enabled: bool = otel.get("enabled", False)
            if otel_enabled:
                flattened_data["otel_mcp_exporter_enabled"] = True
                otel_service_name = otel.get("service_name")
                if otel_service_name is not None:
                    flattened_data["otel_mcp_service_name"] = otel_service_name
                otel_span_prefix = otel.get("span_prefix")
                if otel_span_prefix is not None:
                    flattened_data["otel_mcp_span_prefix"] = otel_span_prefix
            # file
            file: dict = exporters_data.get("file", {})
            file_enabled: bool = file.get("enabled", False)
            if file_enabled:
                flattened_data["file_enabled"] = True
                file_path = next(iter(file.get(label) for label in _FILE_EXPORTER_LOGS_ALIASES if label in file), None)
                if file_path is not None:
                    flattened_data["file_exporter_logs"] = Path(file_path)
                max_mb_per_file = next(iter(file.get(label) for label in _MAX_MB_PER_FILE_ALIASES if label in file), None)
                if max_mb_per_file is not None:
                    flattened_data["max_mb_per_file"] = max_mb_per_file
            # sqlite
            sqlite: dict = exporters_data.get("sqlite", {})
            sqlite_enabled: bool = sqlite.get("enabled", False)
            if sqlite_enabled:
                flattened_data["sqlite_enabled"] = True
                sqlite_path = next(iter(sqlite.get(label) for label in _SQLITE_URI_ALIASES if label in sqlite), None)
                if sqlite_path is not None:
                    flattened_data["sqlite_uri"] = Path(sqlite_path)

            current_data = self.model_dump()
            current_data.update(flattened_data)
            updated_instance = self.__class__.model_validate(current_data)
            for field, value in updated_instance.model_dump().items():
                setattr(self, field, value)

        config_logger.info("YAML config file was loaded into AIMonitor settings")

    async def load_from_json(self, json_file_path: str | Path) -> None:
        json_file_path = Path(json_file_path)
        if not json_file_path.exists():
            config_logger.error("JSON config file was not found")
            raise FileNotFoundError("JSON config file was not found")

        async with aiofiles.open(json_file_path, mode="r", encoding="utf-8") as file:
            data = json.loads(await file.read())

        if data:
            # app
            flattened_data = {}
            app_data: dict = data.get("app", {})
            env_code = next(iter(app_data.get(env_label) for env_label in _ENV_CODE_ALIASES if env_label in app_data), None)
            logger_level = next(iter(app_data.get(logs_label) for logs_label in _LOGGER_LEVEL_ALIASES if logs_label in app_data), None)
            if env_code:
                flattened_data["env_code"] = env_code
            if logger_level:
                flattened_data["logger_level"] = logger_level
            
            # tracking
            tracking_data: dict = data.get("tracking", {})
            enabled = tracking_data.get("enabled", None)
            track_metrics = next(iter(tracking_data.get(metrics_label) for metrics_label in _TRACK_METRICS_ALIASES if metrics_label in tracking_data), None)
            track_events = next(iter(tracking_data.get(events_label) for events_label in _TRACK_EVENTS_ALIASES if events_label in tracking_data), None)
            track_logs = next(iter(tracking_data.get(logs_label) for logs_label in _TRACK_LOGS_ALIASES if logs_label in tracking_data), None)
            if enabled is not None:
                flattened_data["enabled"] = enabled
            if track_metrics is not None:
                flattened_data["track_metrics"] = track_metrics
            if track_events is not None:
                flattened_data["track_events"] = track_events
            if track_logs is not None:
                flattened_data["track_logs"] = track_logs

            # inner telemetry
            telemetry_data: dict = data.get("telemetry", {})
            inner_telemetry = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _INNER_TELEMETRY_ALIASES if telemetry_label in telemetry_data), None)
            if inner_telemetry is not None:
                flattened_data["inner_telemetry"] = inner_telemetry
            healthcheck_enabled = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _HEALTHCHECK_ENABLED_ALIASES if telemetry_label in telemetry_data), None)
            if healthcheck_enabled is not None:
                flattened_data["healthcheck_enabled"] = healthcheck_enabled
            healthcheck_interval = next(iter(telemetry_data.get(telemetry_label) for telemetry_label in _HEALTHCHECK_INTERVAL_ALIASES if telemetry_label in telemetry_data), None)
            if healthcheck_interval is not None:
                flattened_data["healthcheck_interval"] = healthcheck_interval
            
            # security
            security_data: dict = data.get("security", {})
            sensitive_keys = next(iter(security_data.get(keys_label) for keys_label in _SENSITIVE_KEYS_ALIASES if keys_label in security_data), None)
            if sensitive_keys is not None:
                flattened_data["sensitive_keys"] = sensitive_keys

            # exporters
            exporters_data: dict = data.get("exporters", {})
            # redis
            redis: dict = exporters_data.get("redis", {})
            redis_enabled = redis.get("enabled", False)
            if redis_enabled:
                flattened_data["redis_enabled"] = redis_enabled
                redis_url = redis.get("url")
                if redis_url is not None:
                    flattened_data["redis_url"] = redis_url
            else:
                flattened_data["redis_enabled"] = False
            # mongodb
            mongodb: dict = exporters_data.get("mongodb", {})
            mongodb_enabled: bool = mongodb.get("enabled", False)
            if mongodb_enabled:
                flattened_data["mongodb_enabled"] = True
                mongodb_url = mongodb.get("url")
                if mongodb_url is not None:
                    flattened_data["mongodb_url"] = mongodb_url
            else:
                flattened_data["mongodb_enabled"] = False
            # postgres
            postgres: dict = exporters_data.get("postgres", {})
            postgres_enabled: bool = postgres.get("enabled", False)
            postgres_url = postgres.get("url")
            if postgres_enabled:
                flattened_data["postgres_enabled"] = True
                if postgres_url is not None:
                    flattened_data["postgres_url"] = postgres_url
            else:
                flattened_data["postgres_enabled"] = False
            # prometheus
            prometheus: dict = exporters_data.get("prometheus", {})
            prometheus_enabled: bool = prometheus.get("enabled", False)
            if prometheus_enabled:
                flattened_data["prometheus_enabled"] = True
                prometheus_url = prometheus.get("url")
                if prometheus_url is not None:
                    flattened_data["prometheus_url"] = prometheus_url
            else:
                flattened_data["prometheus_enabled"] = False
            # kafka
            kafka: dict = exporters_data.get("kafka", {})
            if kafka.get("enabled"):
                flattened_data["kafka_enabled"] = True
                kafka_bootstrap_servers = kafka.get("bootstrap_servers")
                if kafka_bootstrap_servers is not None:
                    flattened_data["kafka_bootstrap_servers"] = kafka_bootstrap_servers
                kafka_security_protocol = kafka.get("security_protocol")
                if kafka_security_protocol is not None:
                    flattened_data["kafka_security_protocol"] = kafka_security_protocol
                kafka_auto_offset_reset = kafka.get("auto_offset_reset")
                if kafka_auto_offset_reset is not None:
                    flattened_data["kafka_auto_offset_reset"] = kafka_auto_offset_reset
                kafka_retry_policy = kafka.get("retry_policy")
                if kafka_retry_policy is not None:
                    flattened_data["kafka_retry_policy"] = kafka_retry_policy
                kafka_delivery_timeout_ms = kafka.get("delivery_timeout_ms")
                if kafka_delivery_timeout_ms is not None:
                    flattened_data["kafka_delivery_timeout_ms"] = kafka_delivery_timeout_ms
                kafka_request_timeout_ms = kafka.get("request_timeout_ms")
                if kafka_request_timeout_ms is not None:
                    flattened_data["kafka_request_timeout_ms"] = kafka_request_timeout_ms
                kafka_socket_timeout_ms = kafka.get("socket_timeout_ms")
                if kafka_socket_timeout_ms is not None:
                    flattened_data["kafka_socket_timeout_ms"] = kafka_socket_timeout_ms
                kafka_reconnect_backoff_ms = kafka.get("reconnect_backoff_ms")
                if kafka_reconnect_backoff_ms is not None:
                    flattened_data["kafka_reconnect_backoff_ms"] = kafka_reconnect_backoff_ms
                kafka_reconnect_backoff_max_ms = kafka.get("reconnect_backoff_max_ms")
                if kafka_reconnect_backoff_max_ms is not None:
                    flattened_data["kafka_reconnect_backoff_max_ms"] = kafka_reconnect_backoff_max_ms
                kafka_sasl = kafka.get("sasl")
                if kafka_sasl is not None:
                    kafka_sasl_mechanism = kafka_sasl.get("mechanism")
                    if kafka_sasl_mechanism is not None:
                        flattened_data["kafka_sasl_mechanism"] = kafka_sasl_mechanism
                    kafka_sasl_username = kafka_sasl.get("username")
                    if kafka_sasl_username is not None:
                        flattened_data["kafka_sasl_username"] = kafka_sasl_username
                    kafka_sasl_password = kafka_sasl.get("password")
                    if kafka_sasl_password is not None:
                        flattened_data["kafka_sasl_password"] = SecretStr(kafka_sasl_password)
                kakfa_producer = kafka.get("producer")
                if kakfa_producer is not None:
                    kafka_producer_acks = kakfa_producer.get("acks")
                    if kafka_producer_acks is not None:
                        flattened_data["kafka_producer_acks"] = kafka_producer_acks
                    kafka_retries = kakfa_producer.get("retries")
                    if kafka_retries is not None and isinstance(kafka_retries, int):
                        flattened_data["kafka_retry_policy"] = kafka_retries
                    kafka_compression_type = kakfa_producer.get("compression")
                    if kafka_compression_type is not None:
                        flattened_data["kafka_compression_type"] = kafka_compression_type
                    kafka_linger_ms = kakfa_producer.get("linger_ms")
                    if kafka_linger_ms is not None and isinstance(kafka_linger_ms, int):
                        flattened_data["kafka_linger_ms"] = kafka_linger_ms
                    kafka_max_workers = kakfa_producer.get("max_workers")
                    if kafka_max_workers is not None and isinstance(kafka_max_workers, int):
                        flattened_data["kafka_max_workers"] = kafka_max_workers
                    kafka_batch_size = kakfa_producer.get("batch_size")
                    if kafka_batch_size is not None and isinstance(kafka_batch_size, int):
                        flattened_data["kafka_batch_size"] = kafka_batch_size
                kafka_max_in_flight_requests_per_connection = kafka.get("max_in_flight_requests_per_connection")
                if kafka_max_in_flight_requests_per_connection is not None and isinstance(kafka_max_in_flight_requests_per_connection, int):
                    flattened_data["kafka_max_in_flight_requests_per_connection"] = kafka_max_in_flight_requests_per_connection
                kafka_max_workers = kafka.get("max_workers")
                if kafka_max_workers is not None and isinstance(kafka_max_workers, int):
                    flattened_data["kafka_max_workers"] = kafka_max_workers
                kafka_batch_size = kafka.get("batch_size")
                if kafka_batch_size is not None and isinstance(kafka_batch_size, int):
                    flattened_data["kafka_batch_size"] = kafka_batch_size
                kafka_buffer_timeout = kafka.get("buffer_timeout")
                if kafka_buffer_timeout is not None and isinstance(kafka_buffer_timeout, (int, float)):
                    flattened_data["kafka_buffer_timeout"] = kafka_buffer_timeout
            else:
                flattened_data["kafka_enabled"] = False
            # open telemetry
            otel: dict = exporters_data.get("otel", {})
            otel_enabled: bool = otel.get("enabled", False)
            if otel_enabled:
                flattened_data["otel_mcp_exporter_enabled"] = True
                otel_service_name = otel.get("service_name")
                if otel_service_name is not None:
                    flattened_data["otel_mcp_service_name"] = otel_service_name
                otel_span_prefix = otel.get("span_prefix")
                if otel_span_prefix is not None:
                    flattened_data["otel_mcp_span_prefix"] = otel_span_prefix
            # file
            file: dict = exporters_data.get("file", {})
            file_enabled: bool = file.get("enabled", False)
            if file_enabled:
                flattened_data["file_enabled"] = True
                file_path = next(iter(file.get(label) for label in _FILE_EXPORTER_LOGS_ALIASES if label in file), None)
                if file_path is not None:
                    flattened_data["file_exporter_logs"] = Path(file_path)
                max_mb_per_file = next(iter(file.get(label) for label in _MAX_MB_PER_FILE_ALIASES if label in file), None)
                if max_mb_per_file is not None:
                    flattened_data["max_mb_per_file"] = max_mb_per_file
            # sqlite
            sqlite: dict = exporters_data.get("sqlite", {})
            sqlite_enabled: bool = sqlite.get("enabled", False)
            if sqlite_enabled:
                flattened_data["sqlite_enabled"] = True
                sqlite_path = next(iter(sqlite.get(label) for label in _SQLITE_URI_ALIASES if label in sqlite), None)
                if sqlite_path is not None:
                    flattened_data["sqlite_uri"] = Path(sqlite_path)

            current_data = self.model_dump()
            current_data.update(flattened_data)
            updated_instance = self.__class__.model_validate(current_data)
            for field, value in updated_instance.model_dump().items():
                setattr(self, field, value)

        config_logger.info("JSON config file was loaded into AIMonitor settings")
    
    def get_kafka_config(self) -> dict:
        """Return the exact producer configuration expected by confluent-kafka."""
        conf = {
            "bootstrap.servers": self.kafka_bootstrap_servers,
            "security.protocol": self.kafka_security_protocol,
            "client.id": socket.gethostname(),
            "auto.offset.reset": self.kafka_auto_offset_reset,
            "acks": self.kafka_producer_acks if self.kafka_producer_acks is not None else "all",
            "enable.idempotence": True,
            "retries": self.kafka_retry_policy if self.kafka_retry_policy is not None else 3,
            "max.in.flight.requests.per.connection": self.kafka_max_in_flight_requests_per_connection if self.kafka_max_in_flight_requests_per_connection is not None else 5,
            "linger.ms": self.kafka_producer_linger_ms if self.kafka_producer_linger_ms is not None else 5,
            "compression.type": self.kafka_compression_type if self.kafka_compression_type is not None else "none",
            "delivery.timeout.ms": self.kafka_delivery_timeout_ms if self.kafka_delivery_timeout_ms is not None else 120000,
            "request.timeout.ms": self.kafka_request_timeout_ms if self.kafka_request_timeout_ms is not None else 30000,
            "socket.timeout.ms": self.kafka_socket_timeout_ms if self.kafka_socket_timeout_ms is not None else 30000,
            "reconnect.backoff.ms": self.kafka_reconnect_backoff_ms if self.kafka_reconnect_backoff_ms is not None else 1000,
            "reconnect.backoff.max.ms": self.kafka_reconnect_backoff_max_ms if self.kafka_reconnect_backoff_max_ms is not None else 30000,
        }

        if self.kafka_sasl_mechanism:
            conf["sasl.mechanism"] = self.kafka_sasl_mechanism
        if self.kafka_sasl_username:
            conf["sasl.username"] = self.kafka_sasl_username.get_secret_value() if hasattr(self.kafka_sasl_username, "get_secret_value") else self.kafka_sasl_username
        if self.kafka_sasl_password:
            conf["sasl.password"] = self.kafka_sasl_password.get_secret_value() if hasattr(self.kafka_sasl_password, "get_secret_value") else self.kafka_sasl_password

        return conf

    @field_validator("redis_url", "mongodb_url", "postgres_url", mode="before")
    @classmethod
    def validate_urls(cls, v: Optional[Any]) -> Optional[Any]:
        if v is None or v == "":
            return None
        if isinstance(v, AnyUrl):
            return v
        if not isinstance(v, str):
            raise ValueError(f"URL value must be a string, got {type(v)}")
        parsed = parse.urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL for service: {v}")
        if not any(v.startswith(prefix) for prefix in _VALID_URLS):
            raise ValueError(f"Invalid URL for service: {v}")
        return v

    @field_validator("max_mb_per_file")
    @classmethod
    def validate_size(cls, v: Optional[float]) -> Optional[float]:
        if not isinstance(v, (float, int)):
            raise ValueError(f"Max file size should be float or integer, not {type(v)}")
        if v <= 0:
            raise ValueError("Max file size should be positive")
        return float(v)

    @field_validator("retries_policy")
    @classmethod
    def validate_retries_policy(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return 0
        if not isinstance(v, (int, float)):
            raise ValueError(f"Retries must be int or float, not {type(v)}")
        if v < 0:
            raise ValueError("Retries policy must be greater or equal than 0")
        return int(v)

    @field_validator("env_code", mode="before")
    @classmethod
    def validate_env_code(cls, v: Optional[object]) -> Optional[_VALID_ENV_CODE]:
        if v is None:
            return _VALID_ENV_CODE.ENV
        if isinstance(v, _VALID_ENV_CODE):
            return v
        if isinstance(v, str):
            normalized = v.upper()
            for member in _VALID_ENV_CODE:
                if member.value == normalized:
                    return member
            raise ValueError(f"env code {v} is not allowed, use {[member.value for member in _VALID_ENV_CODE]}")
        raise ValueError(f"env code {v} is not allowed")

    @field_validator("sensitive_keys", mode="before")
    @classmethod
    def validate_sensitive_keys(cls, v: Optional[Any]) -> Optional[set[str]]:
        if v is None:
            return set()
        if isinstance(v, str):
            return {item.strip().lower() for item in v.split(",") if item.strip()}
        if isinstance(v, (list, tuple, set)):
            return {str(item).strip().lower() for item in v if str(item).strip()}
        raise ValueError("sensitive_keys must be a string, list, tuple, or set")
    
    @field_validator("inner_telemetry", mode="before")
    @classmethod
    def validate_inner_telemetry(cls, v: Optional[bool]) -> Optional[bool]:
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
            raise ValueError("inner_telemetry must be a boolean value or one of: true, false, 1, 0, yes, no, on, off")
        raise ValueError("inner_telemetry must be a boolean or boolean-like string")

    @field_validator("healthcheck_enabled", mode="before")
    @classmethod
    def validate_healthcheck_enabled(cls, v: Optional[bool]) -> Optional[bool]:
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueError("healthcheck_enabled must be a boolean value or one of: true, false, 1, 0, yes, no, on, off")




@lru_cache
def get_settings() -> AIMonitorSettings:
    return AIMonitorSettings()


settings = get_settings()


