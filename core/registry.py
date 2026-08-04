from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import MCPEvent
import httpx
import asyncio
import time
from utils.logger import logger
from tenacity import retry

class ExporterRegistry:
    def __init__(self, batch_size: int = 10, flush_delta: float = 1.0, num_workers: int = 5):
        self._exporters: List[BaseExporter] = []
        self._num_workers = num_workers
        self._workers: List[asyncio.Task] = []
        self._queue = asyncio.Queue()
        self.batch_size = batch_size
        self.flush_delta = flush_delta

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    def dispatch(self, events: List[MCPEvent] | MCPEvent):
        if not self._workers:
            self.start_workers()
        
        if isinstance(events, list):
            for e in events:
                self._queue.put_nowait(e)
        else:
            self._queue.put_nowait(events)

    def start_workers(self):
        if not self._workers:
            for _ in range(self._num_workers):
                task = asyncio.create_task(self._process_queue())
                self._workers.append(task)

    async def _process_queue(self):
        last_flush = time.time()
        batch: List[MCPEvent] = []
        batch_items = 0

        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                batch.append(event)
                batch_items += 1
            except asyncio.TimeoutError:
                event = None

            now = time.time()
            if event is None and not batch:
                continue

            should_flush = (
                len(batch) >= self.batch_size
                or (event is None and batch and (now - last_flush) >= self.flush_delta)
                or (event is None and batch and self._queue.empty())
            )

            if should_flush:
                try:
                    await self._send_batch(batch)
                except Exception:
                    logger.error("Error found while sending batch of events")
                finally:
                    logger.info("Finished processing event batch")
                    for _ in range(batch_items):
                        self._queue.task_done()
                    last_flush = now
                    batch = []
                    batch_items = 0

    async def _send_batch(self, batch: List[MCPEvent]):
        failed_exporters = []
        for i, exporter in enumerate(self._exporters):
            try:
                await exporter.export_batch(batch)
            except:
                exporter_name = exporter.__class__.__name__
                logger.error(f"Exporter {exporter_name} failed to exporter event batch, popping it from list")
                failed_exporters.append(i)
        for exporter_index in failed_exporters:
            self._exporters.pop(exporter_index)
    
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