from typing import List
from exporters.base import BaseExporter
from core.event import MCPEvent
import httpx
import asyncio
from utils.logger import logger
from tenacity import retry

class ExporterRegistry:
    def __init__(self):
        self._exporters: List[BaseExporter] = []
        self._num_workers: int = 5
        self._workers: List[asyncio.Task] = []
        self._queue = asyncio.Queue()

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    def dispatch(self, event: MCPEvent):
        for exporter in self._exporters:
            self._queue.put_nowait((exporter, event))
    
    def start_workers(self):
        if not self._worker_task:
            for _ in range(self._num_workers):
                task = asyncio.create_task(self._process_queue())
                self._workers.append(task)

    async def _process_queue(self):
        while True:
            exporter, event = await self._queue.get()
            try:
                await exporter.export_with_retries(event)
            except Exception as e:
                self._exporters.remove(exporter)
                logger.error(f"Exporter {exporter.__class__.__name__} has been removed from the registry due to the error. Retries consumed")
            finally:
                logger.info(f"Finished processing event for exporter: {exporter.__class__.__name__} and event: {event.model_json_dump()}")
                self._queue.task_done()
    
    def shutdown(self):
        if self._worker_task is not None:
            self._worker_task.cancel()
            self._worker_task = None


# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()