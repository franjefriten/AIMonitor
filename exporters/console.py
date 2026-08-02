"""
Exporter module for console, used mostly for debugging purposes
"""

from exporters.base import BaseExporter
from core.event import MCPEvent, SignalType
from utils.logger import logger
from typing import List

class ConsoleExporter(BaseExporter):
    
    def __init__(self):
        super().__init__()

    def export(self, event: MCPEvent) -> None:
        logger.info(f"Exporting event to console: {event}")
    
    def export_batch(self, event_batch: List[MCPEvent]) -> None:
        for event in event_batch:
            self.export(event)

        
