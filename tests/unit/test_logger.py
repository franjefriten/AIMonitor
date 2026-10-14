import logging

from aimonitor.utils.logger import AIMONITOR_LOGGER_NAME, setup_logging


def test_setup_logging_configures_only_aimonitor_logger(tmp_path):
    config_path = tmp_path / "logging.yaml"
    config_path.write_text(
        """
version: 1
disable_existing_loggers: false
formatters:
  standard:
    format: "%(message)s"
handlers:
  console:
    class: logging.StreamHandler
    level: DEBUG
    formatter: standard
    stream: ext://sys.stdout
root:
  level: CRITICAL
  handlers: [console]
""".strip(),
        encoding="utf-8",
    )

    root_logger = logging.getLogger()
    root_handlers = list(root_logger.handlers)

    setup_logging(config_path=config_path)

    aimonitor_logger = logging.getLogger(AIMONITOR_LOGGER_NAME)
    assert aimonitor_logger.handlers
    assert aimonitor_logger.propagate is False
    assert list(root_logger.handlers) == root_handlers
