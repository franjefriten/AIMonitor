"""
Exporter module for console, used mostly for debugging purposes
"""

from exporters.base import BaseExporter
from core.event import BaseSignal, SignalType
from utils.logger import logger
from typing import List
import io
import sys
from datetime import datetime, UTC


class ConsoleExporter(BaseExporter):
    """
    Basic exporter that prints events to the console. This exporter is primarily intended for debugging and development purposes, allowing developers to see the events being processed in real-time.
    """
    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG, SignalType.METRIC}  # logs everything    
    
    def __init__(self, stream: io.TextIOBase = sys.stdout):
        super().__init__()
        self.stream = stream

    async def export(self, event: BaseSignal) -> None:
        if event.event_type not in self.SUPPORTED_SIGNALS:
            logger.warning(
                "Event type '%s' with id: '%s' is not supported by ConsoleExporter. Skipping export for event.",
                event.event_type,
                event.id
                )       
            return
        output = f"[TRACE][{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S.%f')}]"
        output += f"\n{event.model_dump()}"
        self.stream.write(output + "\n")

        if hasattr(self.stream, "flush"):
            self.stream.flush()
    
    async def export_batch(self, event_batch: List[BaseSignal]) -> None:
        timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S.%f')
        output_lines = f"[TRACE][{timestamp}]"

        for event in event_batch:
            if event.event_type not in self.SUPPORTED_SIGNALS:
                logger.warning(
                    "Event type '%s' with id: '%s' is not supported by ConsoleExporter. Skipping export for event.",
                    event.event_type,
                    event.id
                )
            else:
                output_lines += f"\n{event.model_dump()}"

        self.stream.write("\n".join(output_lines) + "\n")

        if hasattr(self.stream, "flush"):
            self.stream.flush()

        
