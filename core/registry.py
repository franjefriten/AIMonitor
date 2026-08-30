from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import BaseSignal
from configs.config import get_settings
import httpx
import asyncio
import time
from utils.logger import logger
from tenacity import retry

class ExporterRegistry:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, batch_size: int = 10, flush_delta: float = 1.0, num_workers: int = 5):
        if not hasattr(self, "_exporters"):
            self._exporters: List[BaseExporter] = []
        if not hasattr(self, "_workers"):
            self._workers: List[asyncio.Task] = []
        if not hasattr(self, "_queue"):
            self._queue: asyncio.Queue | None = None
        if not hasattr(self, "_loop"):
            self._loop = None
        if not hasattr(self, "_healthcheck_worker"):
            self._healthcheck_worker: asyncio.Task | None = None

        self._num_workers = num_workers
        self.batch_size = batch_size
        self.flush_delta = flush_delta
        settings = get_settings()
        self._healthcheck_enabled = settings.healthcheck_enabled
        self._healthcheck_interval = settings.healthcheck_interval

    def _start_healthcheck_worker(self):
        settings = get_settings()
        if not settings.healthcheck_enabled:
            self._healthcheck_enabled = False
            return

        self._healthcheck_enabled = True
        self._healthcheck_interval = settings.healthcheck_interval

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if self._healthcheck_worker is None or self._healthcheck_worker.done():
            self._healthcheck_worker = loop.create_task(self._healthcheck_loop())

    async def _healthcheck_loop(self):
        while self._healthcheck_enabled:
            for exporter in list(self._exporters):
                try:
                    await exporter.healthcheck()
                except Exception as e:
                    logger.error(f"Health check failed for exporter {exporter}: {e}")
            await asyncio.sleep(self._healthcheck_interval)


    def _ensure_queue_exists(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            return False

        # When pytest creates a new loop per test, stale workers/queues from a
        # previous loop become invalid and must be recreated.
        if self._loop is not None and self._loop is not loop:
            self._workers = []
            self._queue = None

        self._loop = loop

        if self._queue is None:
            self._queue = asyncio.Queue()

        # Keep only live workers so dispatch can restart them when needed.
        self._workers = [worker for worker in self._workers if not worker.done()]

        return True

    def register(self, exporter: BaseExporter):
        self._exporters.append(exporter)
        self._start_healthcheck_worker()

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
        batch = events if isinstance(events, list) else [events]
        asyncio.run(self._send_batch(batch))

    def start_workers(self):
        if not self._ensure_queue_exists():
            return
        self._workers = [worker for worker in self._workers if not worker.done()]
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
        for exporter_index in sorted(failed_exporters, reverse=True):
            exporter = self._exporters[exporter_index]
            try:
                if hasattr(exporter, "close"):
                    await exporter.close()
            except Exception:
                logger.warning("Failed to close exporter %s during removal.", exporter.__class__.__name__)
            self._exporters.pop(exporter_index)
            
    
    async def shutdown(self):
        if self._queue is not None:
            await self._queue.join()

        for worker in list(self._workers):
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        if self._healthcheck_worker is not None:
            self._healthcheck_worker.cancel()
            await asyncio.gather(self._healthcheck_worker, return_exceptions=True)
            self._healthcheck_worker = None

        for exporter in list(self._exporters):
            try:
                if hasattr(exporter, 'close'):
                    await exporter.close()
            except Exception:
                logger.warning("Failed to close exporter %s during shutdown.", exporter.__class__.__name__)

        self._workers = []
        self._exporters = []
        self._queue = None
        self._loop = None
        self._healthcheck_enabled = False
    

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()
