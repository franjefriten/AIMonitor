# utils/logger.py
import logging.config
import yaml
import os
from pathlib import Path
from configs.config import get_settings

settings = get_settings()

def setup_logging(default_path: str = "./logging.dev.yaml", default_level = logging.INFO):
    env_code = settings.env_code
    match env_code:
        case "ENV":
            default_path = "./logging.dev.yaml"
        case "STG":
            default_path = "/logging.stg.yaml"
        case "PRO":
            default_path = "/logging.pro.yaml"
        case _:
            default_path = "./logging.dev.yaml"
            
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