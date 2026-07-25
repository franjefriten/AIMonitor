from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import MCPEvent
import httpx
import asyncio
from utils.logger import logger
from tenacity import retry

class ExporterRegistry:
    _instance = None

    def __init__(self):
        self._exporters: List[BaseExporter] = []
        self._num_workers: int = 5
        self._workers: List[asyncio.Task] = []
        self._queue = asyncio.Queue()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    def dispatch(self, event: MCPEvent):
        if not self._workers:
            self.start_workers()

        for exporter in self._exporters:
            self._queue.put_nowait((exporter, event))
    
    def start_workers(self):
        if not self._workers:
            for _ in range(self._num_workers):
                task = asyncio.create_task(self._process_queue())
                self._workers.append(task)

    async def _process_queue(self):
        while True:
            exporter, event = await self._queue.get()
            try:
                await exporter.export(event)
            except Exception as e:
                self._exporters.remove(exporter)
                logger.error(f"Exporter {exporter.__class__.__name__} has been removed from the registry due to the error. Retries consumed")
            finally:
                logger.info(f"Finished processing event for exporter: {exporter.__class__.__name__} and event: {event.model_dump_json()}")
                self._queue.task_done()
    
    async def shutdown(self):
        # wait until all tasks are finished
        await self._queue.join()

        if len(self._workers):
            for worker in self._workers:
                worker.cancel()
            # make sure all workers have been cancelled, in case of errors of exceptions in cancel
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers = []
    

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()
# add default console register
registry.register(ConsoleExporter())