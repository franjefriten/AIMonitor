from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, AnyUrl, FilePath, HttpUrl
from typing import Any, Optional, List, Literal
from pathlib import Path
import yaml
import aiofiles
import json
from functools import lru_cache


_VALID_URLS = ["mongodb://", "redis://", "postgres://", "http://", "https://"]

class AIMonitorSettings(BaseSettings):
    """
    Settings class for the module, handles urls to services such as redis, mongodb and others.
    It also handles the security settings such as secret keys sent in payloads by the user: 
    """
    
    model_config = SettingsConfigDict(env_prefix="AIMONITOR_", env_file=('.env', '.env.prod'))
    
    # Security keys to be redacted
    sensitive_keys: set = Field(
        default_factory={
            "password", 
            "token", 
            "api_key", 
            "secret", 
            "apikey", 
            "access_token", 
            "client_secret", 
            "private_key", 
            "credentials"
        },
        description="sensitive keys to censor in data",

    )
    # URL config defaults, to be overrriden by configure helper function or environment variables
    redis_url: Optional[AnyUrl] = Field(default="redis://localhost:6379/0", description="redis url to use", validation_alias="AIMONITOR_REDIS_URL")
    mongodb_url: Optional[AnyUrl] = Field(default="mongodb://localhost:27017", description="mongodb url to use", validation_alias="AIMONITOR_MONGODB_URL")
    postgres_url: Optional[AnyUrl] = Field(default="postgresql://user:password@localhost/dbname", description="postgres url to use", validation_alias="AIMONITOR_POSTGRES_URL")
    prometheus_url: Optional[HttpUrl] = Field(default="http://localhost:9000", description="prometheus url to use", validation_alias="AIMONITOR_PROMETHEUS_URL")
    sqlite_uri: Optional[FilePath] = Field(default="./sqlite_aimonitor.sqlite", description="sqlite path to use")
    max_mb_per_file: Optional[float] = Field(default=10.0, description="max file size in megabytes")
    level_log: Literal["error", "warning", "info"]


    async def load_from_yaml(self, yaml_file_path: str | Path) -> None:
        if isinstance(yaml_file_path, str):
            yaml_file_path = Path(yaml_file_path)
        if not yaml_file_path.exists():
            raise FileNotFoundError("YAML config file was not found")
        
        async with aiofiles.open(file=yaml_file_path) as file:
            data = yaml.safe_load(await file.read())
        
        if data:
            current_data = self.model_dump()
            current_data.update(data)
            # Avoids skiping pydantic evaluation 
            updated_instance = self.__class__(**current_data)
            for field, value in updated_instance:
                setattr(self, field, value)
    
    
    async def load_from_json(self, json_file_path: str | Path) -> None:
        if isinstance(json_file_path, str):
            json_file_path = Path(json_file_path)
        if not json_file_path.exists():
            raise FileNotFoundError("JSON config file was not found")
        
        async with aiofiles.open(file=json_file_path) as file:
            data = json.load(await file.read())
        
        if data:
            current_data = self.model_dump()
            current_data.update(data)
            # Avoids skiping pydantic evaluation 
            updated_instance = self.__class__(**current_data)
            for field, value in updated_instance:
                setattr(self, field, value)

    
    @field_validator("redis_url", "mongobd_url", "postgres_url", mode="before")
    @classmethod
    def validate_urls(cls, v: Optional[str]) -> Optional[str]:
        if not any([v.startswith(prefix) for prefix in _VALID_URLS]):
            raise ValueError(f"Invalid URL for service: {v}")

        

# singleton
@lru_cache
def get_settings():
    return AIMonitorSettings()


