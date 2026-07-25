from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Optional

class AIMonitorSettings(BaseSettings):
    """
    Settings class for the module, handles urls to services such as redis, mongodb and others.
    It also handles the security settings such as secret keys sent in payloads by the user: 
    """
    # Security keys to be redacted
    sensitive_keys: set = {"password", "token", "api_key", "secret", "apikey", "access_token", 
                           "client_secret", "private_key", "credentials"}
    # URL config defaults, to be overrriden by configure helper function or environment variables
    redis_url: Optional[str] = "redis://localhost:6379/0"
    mongodb_url: Optional[str] = "mongodb://localhost:27017"
    postgres_url: Optional[str] = "postgresql://user:password@localhost/dbname"
    sqlite_url: Optional[str] = "sqlite:sqlite.db"
    prometheus_url: Optional[str] = "http://localhost:9000"


    # file size
    max_bytes_per_file: float = 10.0

    # TODO: Add settings for logging levels

    # Search variables in environment that start with AIMONITOR_ and load them into the settings
    model_config = SettingsConfigDict(env_prefix="AIMONITOR_", env_file=".env", env_file_encoding="utf-8")

# singleton
settings = AIMonitorSettings()

def configure(
    sensitive_keys: Optional[set] = None,
    redis_url: Optional[str] = None,
    grafana_url: Optional[str] = None,
    backend_url: Optional[str] = None,
    log_level: Optional[str] = None,
    enable_telemetry: Optional[bool] = None
):
    """
    Helper function to configure the env vars of AI monitor
    
    Keyword arguments:
    sensitive_keys -- keys to be redacted when processed by the monitor
    redis_url -- URL for the Redis service
    grafana_url -- URL for the Grafana service
    backend_url -- URL for the backend service
    log_level -- logging level for the application
    enable_telemetry -- flag to enable/disable telemetry
    Return: return_description
    """
    if sensitive_keys:
        # Añadimos las nuevas claves convirtiéndolas a minúsculas para la comparación
        settings.sensitive_keys.update([k.lower() for k in sensitive_keys])
    
    if redis_url is not None:
        settings.redis_url = redis_url
    if grafana_url is not None:
        settings.grafana_url = grafana_url
    if backend_url is not None:
        settings.backend_url = backend_url
    if log_level is not None:
        settings.log_level = log_level
    if enable_telemetry is not None:
        settings.enable_telemetry = enable_telemetry


