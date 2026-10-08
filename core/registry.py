from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import (
    BaseSignal,
    HealthCheckSnapshot,
    HealthStatus,
    SDKHealthCheckEvent,
    SDKHealthStatus,
)
from configs.config import get_settings
import httpx
import asyncio
import time
from datetime import UTC, datetime
from utils.logger import logger
from tenacity import retry
from core.event import SDKHealthCheckEvent, SDKHealthStatus
    

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
        if not hasattr(self, "_health_keys"):
            self._health_keys: dict[int, str] = {}

        self._num_workers = num_workers
        self.batch_size = batch_size
        self.flush_delta = flush_delta
        settings = get_settings()
        self._healthcheck_enabled = settings.healthcheck_enabled
        self._healthcheck_interval = settings.healthcheck_interval
        self._health = SDKHealthCheckEvent(
            status=SDKHealthStatus.STARTING,
            summary={
                "total_exporters": 0,
                "healthy_count": 0,
                "recovering_count": 0,
                "failure_count": 0,
                "down_count": 0,
                "stopped_count": 0,
            },
        )

    def _snapshot_key(self, exporter: BaseExporter) -> str:
        exporter_id = id(exporter)
        existing_key = self._health_keys.get(exporter_id)
        if existing_key is not None:
            return existing_key

        base_name = exporter.__class__.__name__
        key = base_name
        suffix = 2
        while key in self._health.exporters:
            key = f"{base_name}#{suffix}"
            suffix += 1

        self._health_keys[exporter_id] = key
        return key

    def _update_sdk_health(self) -> None:
        snapshots = list(self._health.exporters.values())
        counts = {
            "total_exporters": len(snapshots),
            "healthy_count": sum(item.status == HealthStatus.HEALTHY for item in snapshots),
            "recovering_count": sum(item.status == HealthStatus.RECOVERING for item in snapshots),
            "failure_count": sum(item.status == HealthStatus.FAILURE for item in snapshots),
            "down_count": sum(item.status == HealthStatus.DOWN for item in snapshots),
            "stopped_count": sum(item.status == HealthStatus.STOPPED for item in snapshots),
        }
        self._health.summary = counts
        self._health.checked_at = datetime.now(UTC)

        active_statuses = {
            item.status for item in snapshots
            if item.status not in {HealthStatus.STOPPED, HealthStatus.UNUSED}
        }
        if not active_statuses:
            self._health.status = SDKHealthStatus.EMPTY if not snapshots else SDKHealthStatus.DOWN
        elif active_statuses == {HealthStatus.STARTING}:
            self._health.status = SDKHealthStatus.STARTING
        elif active_statuses == {HealthStatus.HEALTHY}:
            self._health.status = SDKHealthStatus.HEALTHY
        elif HealthStatus.HEALTHY in active_statuses:
            self._health.status = SDKHealthStatus.DEGRADED
        else:
            self._health.status = SDKHealthStatus.DOWN

    def _update_exporter_health(
        self,
        exporter: BaseExporter,
        snapshot: HealthCheckSnapshot,
    ) -> None:
        key = self._snapshot_key(exporter)
        previous = self._health.exporters.get(key)
        if previous is not None:
            if snapshot.last_success_at is None:
                snapshot.last_success_at = previous.last_success_at
            if snapshot.last_failure_at is None:
                snapshot.last_failure_at = previous.last_failure_at
            if snapshot.status == HealthStatus.HEALTHY:
                snapshot.consecutive_successes = previous.consecutive_successes + 1
                snapshot.consecutive_failures = 0
            elif snapshot.status in {HealthStatus.DOWN, HealthStatus.FAILURE}:
                snapshot.consecutive_successes = 0
                snapshot.consecutive_failures = previous.consecutive_failures + 1
        self._health.exporters[key] = snapshot
        self._update_sdk_health()

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
                    snapshot = await asyncio.wait_for(
                        exporter._healthcheck(),
                        timeout=self._healthcheck_interval
                    )
                    self._update_exporter_health(exporter, snapshot)
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
        self._update_exporter_health(
            exporter,
            HealthCheckSnapshot(
                exporter_name=exporter.__class__.__name__,
                status=HealthStatus.STARTING,
                message="Exporter registered; healthcheck pending.",
            ),
        )
        self._start_healthcheck_worker()

    @property
    def exporters(self) -> tuple[BaseExporter, ...]:
        """Return a read-only snapshot of the registered exporters."""
        return tuple(self._exporters)

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

    def _record_export_result(self, exporter: BaseExporter, success: bool, message: str = "") -> None:
        key = self._snapshot_key(exporter)
        snapshot = self._health.exporters.get(key)
        if snapshot is None:
            return

        snapshot.status = HealthStatus.HEALTHY if success else HealthStatus.FAILURE
        snapshot.message = message or (
            "Exporter batch delivered successfully."
            if success
            else "Exporter batch delivery failed."
        )
        if not success:
            snapshot.last_failure_at = datetime.now(UTC)
        self._update_sdk_health()

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
        for exporter in self._exporters:
            try:
                await exporter.export_batch(batch)
                self._record_export_result(exporter, success=True)
            except Exception as exc:
                exporter_name = exporter.__class__.__name__
                logger.error(f"Exporter {exporter_name} failed to export event batch, error: {repr(exc)}")
                self._record_export_result(exporter, success=False, message=str(exc))
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
            key = self._snapshot_key(exporter)
            snapshot = self._health.exporters.get(key)
            if snapshot is not None:
                snapshot.status = HealthStatus.STOPPED
                snapshot.message = "Exporter stopped."
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
        self._update_sdk_health()

    async def reset(self):
        """Reset runtime state and discard health snapshots."""
        await self.shutdown()
        self._health = SDKHealthCheckEvent(
            status=SDKHealthStatus.EMPTY,
            summary={
                "total_exporters": 0,
                "healthy_count": 0,
                "recovering_count": 0,
                "failure_count": 0,
                "down_count": 0,
                "stopped_count": 0,
            },
        )
        self._health_keys = {}

    
    async def health_snapshot(self) -> SDKHealthCheckEvent:
        return self._health.model_copy(deep=True)
    

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()
