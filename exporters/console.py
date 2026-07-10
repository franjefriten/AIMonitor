"""
Exporter module for console, used mostly for debugging purposes
"""

from exporters.base import BaseExporter
from core.event import MCPEvent

class ConsoleExporter(BaseExporter):
    def export(self, event: MCPEvent) -> None:
        status_icon = "✅" if event.status == "success" else "❌"
        if event.error:
            pass