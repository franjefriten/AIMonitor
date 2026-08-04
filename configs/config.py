from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional
from urllib import parse

import aiofiles
import json
import yaml
from pydantic import AnyUrl, Field, FilePath, HttpUrl, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

import logging
from logging import getLogger, config

_VALID_URLS = ["mongodb://", "redis://", "postgres://", "postgresql://", "http://", "https://"]

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
        env_file=(".env.prod", ".env.stg", ".end.dev", ".env.local", ".end"),
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
        validation_alias=AliasChoices("sensitive_keys", "sensitive-keys", "sensitiveKeys")
    )
    redis_url: Optional[AnyUrl] = Field(
        default="redis://localhost:6379/0",
        description="Redis URL to use",
        validation_alias=AliasChoices("redis_url", "redis-url", "redisUrl")
    )
    mongodb_url: Optional[AnyUrl] = Field(
        default="mongodb://localhost:27017",
        description="MongoDB URL to use",
        validation_alias=AliasChoices("mongodb_url", "mongodb-url", "mongodbUrl")
    )
    postgres_url: Optional[AnyUrl] = Field(
        default="postgresql://user:password@localhost/dbname",
        description="Postgres URL to use",
        validation_alias=AliasChoices("postgres_url", "postgres-url", "postgresUrl")
    )
    prometheus_url: Optional[HttpUrl] = Field(
        default="http://localhost:9000",
        description="Prometheus URL to use",
        validation_alias=AliasChoices("prometheus_url", "prometheus-url", "prometheusUrl")
    )
    sqlite_uri: Optional[Path] = Field(
        default=Path("./sqlite_aimonitor.sqlite"),
        description="SQLite path to use",
        validation_alias=AliasChoices("sqlite_uri", "sqlite-uri", "sqliteUri")
    )
    max_mb_per_file: Optional[float] = Field(
        default=10.0, 
        description="Max file size in megabytes",
        gt=0,
        validation_alias=AliasChoices("max_mb_per_file", "max-mb-per-file", "maxMbPerFile", "max_mb", "max-mb", "maxMb")
    )
    retries_policy: Optional[int] = Field(
        default=3, 
        description="Number of retries for exporters", 
        ge=0,
        validation_alias=AliasChoices("retries_policy", "retries-policy", "retriesPolicy", "retries")
    )
    env_code: Optional[_VALID_ENV_CODE] = Field(
        default=_VALID_ENV_CODE.ENV, 
        description="Environment code used for configs such as logs",
        validation_alias=AliasChoices("env", "envCode", "env-code", "env_code", "environment")    
    )
    file_exporter_logs: Optional[Path] = Field(
        default=Path("./logs"), 
        description="Folder to which file exporter logs will be dumped into",
        validation_alias=AliasChoices("file", "file_path", "file-path", "filePath", "file_exporter_logs", "fileExporterLogs", "file-exporter-logs")
    )

    # tracking validations
    enabled: bool = Field(
        default=True,
        description="Whether general tracking of the module is off or on",
        validation_alias=AliasChoices("enabled", "enable")
    )
    track_metrics: bool = Field(
        default=True,
        description="Whether to track metrics",
        validation_alias=AliasChoices("metrics", "track_metrics", "trackMetrics", "track-metrics")
    )
    track_events: bool = Field(
        default=True,
        description="Whether to track events",
        validation_alias=AliasChoices("events", "track_events", "trackEvents", "track-events")
    )
    track_logs: bool = Field(
        default=True,
        description="Whether to track logs",
        validation_alias=AliasChoices("logs", "track_logs", "trackLogs", "track-logs")
    )

    # inner telemetry
    inner_telemetry: bool = Field(
        default=False,
        description="Option to track telemetry of the module itself, useful for debugging and development",
        validation_alias=AliasChoices("inner_telemetry", "innerTelemetry", "inner-telemetry", "telemetry", "track_telemetry", "trackTelemetry", "track-telemetry", "enable-telemetry", "enableTelemetry", "enable_telemetry")
    )

    # OpenTelemetry exporter for monitored MCP events (separate from SDK internal telemetry)
    otel_mcp_exporter_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry exporter for MCP events captured by AIMonitor",
        validation_alias=AliasChoices(
            "otel_mcp_exporter_enabled",
            "otel-mcp-exporter-enabled",
            "otelMcpExporterEnabled",
            "otel_exporter",
            "open_telemetry_exporter",
            "openTelemetryExporter",
            "mcp_otel_exporter",
            "mcp-otel-exporter",
        ),
    )
    otel_mcp_service_name: str = Field(
        default="aimonitor-mcp",
        description="OpenTelemetry service name used by the MCP events exporter",
        validation_alias=AliasChoices(
            "otel_mcp_service_name",
            "otel-mcp-service-name",
            "otelMcpServiceName",
            "otel_service_name",
            "service_name",
            "serviceName",
        ),
    )
    otel_mcp_span_prefix: str = Field(
        default="mcp.tool",
        description="Span name prefix for monitored MCP tool events",
        validation_alias=AliasChoices(
            "otel_mcp_span_prefix",
            "otel-mcp-span-prefix",
            "otelMcpSpanPrefix",
            "otel_span_prefix",
            "span_prefix",
            "spanPrefix",
        ),
    )


    async def load_from_yaml(self, yaml_file_path: str | Path) -> None:
        yaml_file_path = Path(yaml_file_path)
        if not yaml_file_path.exists():
            config_logger.error("YAML config file was not found")
            raise FileNotFoundError("YAML config file was not found")

        async with aiofiles.open(yaml_file_path, mode="r", encoding="utf-8") as file:
            data = yaml.safe_load(await file.read()) or {}

        if data:
            current_data = self.model_dump()
            current_data.update(data)
            # allow pydantic validation for aliases
            updated_instance = self.__class__.model_validate(**current_data)
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
            current_data = self.model_dump()
            current_data.update(data)
            updated_instance = self.__class__.model_validate(**current_data)
            for field, value in updated_instance.model_dump().items():
                setattr(self, field, value)

        config_logger.info("JSON config file was loaded into AIMonitor settings")

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
        if isinstance(v, bool) and v is True:
            try:
                import opentelemetry
            except ImportError as e:
                raise ImportError(
                    (
                        f"telemetry is set to True in config.yaml or config.json or in .env vars,"
                        f"but opentelemetry is not installed, cannot use inner telemetry."
                        f"Please install it by running pip install .[opentelemetry] or uv sync --extra opentelemetry"
                    )
                ) from e        
            else:
                return True
        elif isinstance(v, bool) and v is False:
            return False
        if isinstance(v, str):
            normalized = v.lower()
            if normalized in {"true", "1", "yes", "on"}:
                try:
                    import opentelemetry
                except ImportError as e:
                    raise ImportError(
                        (
                            f"telemetry is set to True in config.yaml or config.json or in .env vars,"
                            f"but opentelemetry is not installed, cannot use inner telemetry."
                            f"Please install it by running pip install .[opentelemetry] or uv sync --extra opentelemetry"
                        )
                    ) from e
                else:
                    return True
            elif normalized in {"false", "0", "no", "off"}:
                return False
            raise ValueError("inner_telemetry must be a boolean value or one of: true, false, 1, 0, yes, no, on, off")

        raise ValueError("inner_telemetry must be a boolean or boolean-like string")




@lru_cache
def get_settings() -> AIMonitorSettings:
    return AIMonitorSettings()


