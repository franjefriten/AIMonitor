"""
Exporter module for console, used mostly for debugging purposes
"""

from exporters.base import BaseExporter
from core.event import MCPEvent
from utils.logger import logger

class ConsoleExporter(BaseExporter):
    def export(self, event: MCPEvent) -> None:
        status_icon = "✅" if event.status == "success" else "❌"
        logger.info(f"{status_icon} [Exec time: {event.delta}] {event.tool_name} - Status: {event.status}, Args: {event.args}, Result: {event.result}")
        