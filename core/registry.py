from typing import List
from exporters.base import BaseExporter
from exporters.console import ConsoleExporter
from core.event import (
    BaseSignal,
    HealthCheckSnapshot,
    HealthStatus,
    SDKHealthCheckSnapshot,
    SDKHealthStatus,
)
from configs.config import get_settings
import httpx
import asyncio
import time
from datetime import UTC, datetime
from utils.logger import logger
from tenacity import retry
from telemetry.api import internal_telemetry_manager

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
        self._healthcheck_timeout = settings.healthcheck_timeout
        self._healthcheck_retry_policy = settings.healthcheck_retry_policy
        self._healthcheck_recovery_timeout = settings.healthcheck_recovery_timeout
        self._health = SDKHealthCheckSnapshot(
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

    ## INTERNAL HEALTH MANAGEMENT METHODS

    def _snapshot_key(self, exporter: BaseExporter) -> str:
        """Creates the internal key for the exporter"""
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
        """Updates the overall SDK health based on the individual exporter health snapshots."""
        previous_status = self._health.status
        snapshots = list(self._health.exporters.values())
        counts = {
            "total_exporters": len(snapshots),
            "healthy_count": sum(item.status == HealthStatus.HEALTHY for item in snapshots),
            "recovering_count": sum(item.status == HealthStatus.RECOVERING for item in snapshots),
            "failure_count": sum(item.status == HealthStatus.FAILURE for item in snapshots),
            "down_count": sum(item.status in {HealthStatus.DOWN, HealthStatus.FAILURE} for item in snapshots), # We must include failures as down
            "stopped_count": sum(item.status == HealthStatus.STOPPED for item in snapshots),
        }
        self._health.summary = counts
        self._health.checked_at = datetime.now(UTC)

        active_statuses = {
            item.status
            for item in snapshots
            if item.status not in {HealthStatus.STOPPED, HealthStatus.UNUSED}
        }
        if not snapshots:
            sdk_status = SDKHealthStatus.EMPTY
        elif not active_statuses:
            sdk_status = SDKHealthStatus.DOWN
        elif active_statuses == {HealthStatus.STARTING}:
            sdk_status = SDKHealthStatus.STARTING
        elif active_statuses == {HealthStatus.HEALTHY}:
            sdk_status = SDKHealthStatus.HEALTHY
        elif {
            HealthStatus.HEALTHY,
            HealthStatus.RECOVERING,
            HealthStatus.STARTING,
        } & active_statuses:
            sdk_status = SDKHealthStatus.DEGRADED
        elif active_statuses:
            sdk_status = SDKHealthStatus.DEGRADED
        else:
            sdk_status = SDKHealthStatus.DOWN

        self._health.status = sdk_status

        if previous_status != self._health.status:
            self._log_sdk_health_transition(previous_status, self._health.status)
            self._publish_sdk_health_transition(previous_status, self._health.status)

    def _log_sdk_health_transition(
        self,
        previous: SDKHealthStatus,
        current: SDKHealthStatus,
    ) -> None:
        logger.info(
            "SDK health transitioned from %s to %s",
            previous.value.upper(),
            current.value.upper(),
        )

    def _publish_sdk_health_transition(
        self,
        previous: SDKHealthStatus,
        current: SDKHealthStatus,
    ) -> None:
        internal_telemetry_manager.track_event(
            "sdk.health.transition",
            {
                "previous_status": previous.value,
                "status": current.value,
            },
        )

    def _update_exporter_health(
        self,
        exporter: BaseExporter,
        snapshot: HealthCheckSnapshot,
    ) -> None:
        key = self._snapshot_key(exporter)
        previous = self._health.exporters.get(key) # Previous snapshot for this exporter, to be updated
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

    def _log_health_transition(
        self,
        exporter: BaseExporter,
        previous: HealthCheckSnapshot | None,
        current: HealthCheckSnapshot,
    ) -> bool:
        if previous is None or previous.status == current.status:
            return False

        logger.info(
            "Exporter %s transitioned from %s to %s",
            exporter.__class__.__name__,
            previous.status.value.upper(),
            current.status.value.upper(),
        )
        return True

    async def _publish_health_transition(self, snapshot: HealthCheckSnapshot) -> None:
        await internal_telemetry_manager.track_healthcheck(snapshot)

    async def _run_healthcheck(self, exporter: BaseExporter) -> HealthCheckSnapshot:
        started_at = datetime.now(UTC)

        try:
            health = await exporter.healthcheck()
            if health:
                status = HealthStatus.HEALTHY
                last_success_at=started_at
                last_failure_at=None
            else:
                status = HealthStatus.DOWN
                last_failure_at=started_at
                last_success_at=None
            health_snapshot = HealthCheckSnapshot(
                exporter_name=exporter.__class__.__name__,
                status=status,
                message="Health check completed.",
                last_success_at=last_success_at,
                last_failure_at=last_failure_at,
                last_check_started_at=started_at,
                last_check_finished_at=datetime.now(UTC)
            )
        except Exception:
            status = HealthStatus.FAILURE
            health_snapshot = HealthCheckSnapshot(
                exporter_name=exporter.__class__.__name__,
                status=status,
                message="Health check failed.",
                last_success_at=None,
                last_failure_at=started_at,
                last_check_started_at=started_at,
                last_check_finished_at=datetime.now(UTC)
            )
        # Capture the previous snapshot before replacing it so transitions compare old and new state.
        snapshot_key = self._snapshot_key(exporter)
        previous = self._health.exporters.get(snapshot_key)
        self._update_exporter_health(exporter, health_snapshot)
        # Only publish real status changes; repeated checks with the same status are not transitions.
        if self._log_health_transition(exporter, previous, health_snapshot):
            await self._publish_health_transition(health_snapshot)
        return health_snapshot
        
        
    async def _attempt_exporter_recovery(self, exporter: BaseExporter) -> bool:
        started_at = datetime.now(UTC)
        pre_health_recovery_snapshot = HealthCheckSnapshot(
            exporter_name=exporter.__class__.__name__,
            status=HealthStatus.RECOVERING,
            message="Recovery attempt completed.",
            last_success_at=None,
            last_failure_at=None,
            last_check_started_at=started_at,
            last_check_finished_at=datetime.now(UTC)
        )
        previous = self._health.exporters.get(self._snapshot_key(exporter))
        self._update_exporter_health(exporter, pre_health_recovery_snapshot)
        if self._log_health_transition(exporter, previous, pre_health_recovery_snapshot):
            await self._publish_health_transition(pre_health_recovery_snapshot)
        post_health_recovery_snapshot = None
        healthcheck_completed = False
        try:
            if self._healthcheck_retry_policy:
                recovery = False
                recovery_retries = 0
                while not recovery and recovery_retries < self._healthcheck_retry_policy:
                    recovery = await asyncio.wait_for(
                        exporter.recover(),
                        timeout=self._healthcheck_recovery_timeout if self._healthcheck_recovery_timeout else self._healthcheck_timeout
                    )
                    if recovery:
                        status = HealthStatus.HEALTHY
                        break
                    else:
                        status = HealthStatus.DOWN
                        if self._healthcheck_retry_policy and recovery_retries + 1 >= self._healthcheck_retry_policy:
                            logger.warning(f"Recovery attempt for exporter {exporter} failed after {recovery_retries + 1} retries.")
                            break
                    await asyncio.sleep(recovery_retries * 0.5 + 0.1)  # implement basic backoff
                    recovery_retries += 1
            else:
                recovery = await asyncio.wait_for(
                    exporter.recover(), 
                    timeout=self._healthcheck_recovery_timeout if self._healthcheck_recovery_timeout else self._healthcheck_timeout
                )
                if recovery:
                    status = HealthStatus.HEALTHY
                else:
                    status = HealthStatus.DOWN      
            post_health_recovery_snapshot = HealthCheckSnapshot(
                exporter_name=exporter.__class__.__name__,
                status=status,
                message="Recovery attempt completed.",
                last_success_at=None,
                last_failure_at=started_at if status in {HealthStatus.FAILURE, HealthStatus.DOWN} else None,
                last_check_started_at=started_at,
                last_check_finished_at=datetime.now(UTC)
            )
            # Now, we have to attempt a healthcheck to verify if the exporter has recovered.
            health_snapshot = await self._run_healthcheck(exporter)
            healthcheck_completed = True
            if post_health_recovery_snapshot.status != HealthStatus.HEALTHY:
                post_health_recovery_snapshot.status = HealthStatus.FAILURE
                post_health_recovery_snapshot.message = "Recovery attempt failed. Recovery function failed"
            if health_snapshot.status == HealthStatus.HEALTHY and post_health_recovery_snapshot.status == HealthStatus.HEALTHY:
                status = HealthStatus.HEALTHY
                post_health_recovery_snapshot.message = "Recovery attempt succeeded."
            elif health_snapshot.status != HealthStatus.HEALTHY or post_health_recovery_snapshot.status != HealthStatus.HEALTHY:
                status = HealthStatus.FAILURE
                post_health_recovery_snapshot.message = "Recovery attempt failed. Health check failed after recovery was successful."
        except Exception as e:
            logger.error(f"Recovery attempt failed for exporter {exporter}: {e}")
            status = HealthStatus.FAILURE
            post_health_recovery_snapshot = HealthCheckSnapshot(
                exporter_name=exporter.__class__.__name__,
                status=status,
                message="Recovery attempt failed.",
                last_success_at=None,
                last_failure_at=started_at,
                last_check_started_at=started_at,
                last_check_finished_at=datetime.now(UTC)
            )
        finally:
            if post_health_recovery_snapshot is not None:
                if not healthcheck_completed:
                    self._update_exporter_health(exporter, post_health_recovery_snapshot)
                await internal_telemetry_manager.track_healthcheck(post_health_recovery_snapshot)

        return status == HealthStatus.HEALTHY

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
                    health_snapshot = await asyncio.wait_for(
                        self._run_healthcheck(exporter),
                        timeout=self._healthcheck_timeout
                    )
                    if health_snapshot.status in {HealthStatus.FAILURE, HealthStatus.DOWN}:
                        logger.error(f"Exporter {exporter.__class__.__name__} is in a bad state: {health_snapshot.status}. Attempting recovery")
                        await self._attempt_exporter_recovery(exporter)
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
        self._health = SDKHealthCheckSnapshot(
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

    
    async def health_snapshot(self) -> SDKHealthCheckSnapshot:
        return self._health.model_copy(deep=True)
    

# Global singleton instance of the ExporterRegistry
registry = ExporterRegistry()
