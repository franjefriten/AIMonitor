from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import BaseSignal
import httpx
import asyncio
import time
from utils.logger import logger
from tenacity import retry

class ExporterRegistry:
    _instance = None

    def __init__(self, batch_size: int = 10, flush_delta: float = 1.0, num_workers: int = 5, register_console: bool = False):
        self._exporters: List[BaseExporter] = []
        self._num_workers = num_workers
        self._workers: List[asyncio.Task] = []
        self._queue: asyncio.Queue | None = None
        self.batch_size = batch_size
        self.flush_delta = flush_delta
        self._loop = None
        self._register_console = register_console

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_queue_exists(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        self._loop = loop
        if loop is None:
            return False

        if self._queue is None:
            self._queue = asyncio.Queue()
            if self._register_console and not self._exporters:
                self.register(ConsoleExporter())

        return True

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)

    async def dispatch(self, events: List[BaseSignal] | BaseSignal):
        if not self._ensure_queue_exists():
            logger.error("Queue does not exist, aborting the dispatch!")
            return
        if not self._workers:
            self.start_workers()

        if isinstance(events, list):
            for e in events:
                logger.info(f"Enqueueing event with id '{e.id}'")
                self._queue.put_nowait(e)
        else:
            self._queue.put_nowait(events)
    
    def sync_dispatch(self, events: List[BaseSignal] | BaseSignal):
        asyncio.run(self.dispatch(events=events))

    def start_workers(self):
        if not self._ensure_queue_exists():
            return
        if not self._workers:
            for _ in range(self._num_workers):
                task = asyncio.create_task(self._process_queue())
                self._workers.append(task)

    async def _process_queue(self):
        last_flush = time.time()
        batch: List[BaseSignal] = []

        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                batch.append(event)
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
                logger.info(f"Flushing batch with {len(batch)} elements with ids: {', '.join(e.id for e in batch)}")
                try:
                    await self._send_batch(batch)
                except Exception:
                    logger.error(f"Error found while sending batch of events! ids: {', '.join(e.id for e in batch)}")
                finally:
                    logger.info("Finished processing event batch")
                    for _ in batch:
                        self._queue.task_done()
                    last_flush = now
                    batch = []

    async def _send_batch(self, batch):
        failed_exporters = []
        for i, exporter in enumerate(self._exporters):
            try:
                await exporter.export_batch(batch)
            except Exception as exc:
                exporter_name = exporter.__class__.__name__
                logger.error(f"Exporter {exporter_name} failed to exporter event batch, popping it from list, error: {repr(exc)}")
                failed_exporters.append(i)
        for exporter_index in failed_exporters:
            self._exporters.pop(exporter_index)
    
    async def shutdown(self):
        if self._queue is None:
            return

        await self._queue.join()

        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        for exporter in self._exporters:
            if hasattr(exporter, 'close'):
                await exporter.close()

        self._workers = []
        self.batch = []
        self._exporters = []
        self._queue = None
    

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()
