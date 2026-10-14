import logging
import logging.config
from pathlib import Path
from typing import Any

import yaml

AIMONITOR_LOGGER_NAME = "aimonitor"

_LOGGING_CONFIG_BY_ENV = {
    "ENV": "logging.dev.yaml",
    "STG": "logging.stg.yaml",
    "PRO": "logging.pro.yaml",
}


def _configure_fallback(default_level: int) -> None:
    aimonitor_logger = logging.getLogger(AIMONITOR_LOGGER_NAME)
    aimonitor_logger.setLevel(default_level)
    aimonitor_logger.propagate = False

    if not aimonitor_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(default_level)
        aimonitor_logger.addHandler(handler)


def setup_logging(
    config_path: str | Path | None = None,
    env_code: str = "ENV",
    default_level: int = logging.INFO,
) -> None:
    """Configure AIMonitor's logger without changing the application's root logger."""
    path = Path(config_path) if config_path is not None else Path(
        _LOGGING_CONFIG_BY_ENV.get(env_code, _LOGGING_CONFIG_BY_ENV["ENV"])
    )

    if not path.exists():
        _configure_fallback(default_level)
        return

    with path.open("rt", encoding="utf-8") as file:
        config: dict[str, Any] = yaml.safe_load(file) or {}

    root_config = config.pop("root", None) or {}
    loggers = config.setdefault("loggers", {})
    aimonitor_config = loggers.setdefault(AIMONITOR_LOGGER_NAME, {})
    aimonitor_config.setdefault("level", root_config.get("level", default_level))
    aimonitor_config.setdefault("handlers", root_config.get("handlers", []))
    aimonitor_config["propagate"] = False

    logging.config.dictConfig(config)


def get_logger(name: str | None = None) -> logging.Logger:
    logger_name = AIMONITOR_LOGGER_NAME if not name else f"{AIMONITOR_LOGGER_NAME}.{name}"
    return logging.getLogger(logger_name)


logger = get_logger()
