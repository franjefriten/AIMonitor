# utils/logger.py
import logging.config
import yaml
import os
from pathlib import Path
from configs.config import get_settings

settings = get_settings()

_LOGGING_CONFIG_BY_ENV = {
    "ENV": "./logging.dev.yaml",
    "STG": "/logging.stg.yaml",
    "PRO": "/logging.pro.yaml",
}


def setup_logging(default_path: str = "./logging.dev.yaml", default_level = logging.INFO):
    env_code = settings.app.env_code
    default_path = _LOGGING_CONFIG_BY_ENV.get(env_code, "./logging.dev.yaml")
            
    path = Path(default_path)
    if path.exists():
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

# Inicializar configuración al importar el módulo
setup_logging()

def get_logger(name: str):
    return logging.getLogger(name)

logger = get_logger(__name__)