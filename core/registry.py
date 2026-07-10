from typing import List
from exporters.base import BaseExporter
from core.event import MCPEvent

class ExporterRegistry:
    def __init__(self):
        self._exporters: List[BaseExporter] = []

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    def dispatch(self, event: MCPEvent):
        for exporter in self._exporters:
            exporter.export(event)

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()