# utils/logger.py
import logging.config
import yaml
import os
from pathlib import Path

def setup_logging(default_path='logging_config.yaml', default_level=logging.INFO):
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