from typing import List
from exporters.base import BaseExporter
from core.event import MCPEvent
import httpx
import asyncio
from utils.logger import logger
class ExporterRegistry:
    def __init__(self):
        self._exporters: List[BaseExporter] = []
        self._worker_task: asyncio.Task = None
        self._queue = asyncio.Queue()

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    def dispatch(self, event: MCPEvent):
        for exporter in self._exporters:
            self._queue.put_nowait((exporter, event))
    
    def start_worker(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._process_queue)

    async def _process_queue(self):
        while True:
            exporter, event = await self._queue.get()
            try:
                await exporter.export(event)
            except Exception as e:
                logger.error(f"Error occurred while exporting data: {e}")
            finally:
                self._queue.task_done()

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()