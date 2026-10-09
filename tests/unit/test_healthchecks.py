from exporters.base import BaseExporter, with_retry
from core.event import (
    MCPEvent,
    BaseSignal,
    SignalType,
    HealthCheckSnapshot,
    SDKHealthCheckSnapshot,
    SDKHealthStatus,
    HealthStatus,
)
from core.registry import registry
from telemetry.api import get_liveness, get_readiness, internal_telemetry_manager

import pytest
from core.registry import ExporterRegistry
import asyncio


@pytest.mark.asyncio
async def test_healthcheck_api_returns_liveness_and_empty_readiness():
    assert await get_liveness() == {"status": "alive"}

    readiness = await get_readiness()

    assert readiness["status"] == "empty"
    assert readiness["summary"]["total_exporters"] == 0


@pytest.mark.asyncio
async def test_health_check_event_emission():
    captured = []

    class SpyExporter(BaseExporter):
        async def export(self, event):
            captured.append(event)

        async def export_batch(self, event_batch):
            captured.extend(event_batch)
        
        async def healthcheck(self):
            captured.extend([HealthCheckSnapshot(message="Health check passed for SpyExporter.", status=HealthStatus.HEALTHY)])
            return True
        
        async def recover(self):
            return True

        async def status(self):
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Exporter is healthy and connected to the destination.",
                "timestamp": "2023-01-01T12:00:00Z"
            }

    # Test the exporter healthcheck directly so the registry worker does not
    # produce a second event in parallel.
    exporter = SpyExporter()

    # Perform the health check
    await exporter.healthcheck()

    # Check that a HealthCheckEvent was emitted
    assert len(captured) == 1
    event = captured[0]
    assert isinstance(event, HealthCheckSnapshot)
    assert event.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_base_healthcheck_wraps_custom_healthcheck_and_emits_telemetry(monkeypatch):
    captured = []

    class CustomExporter(BaseExporter):
        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return True

        async def status(self):
            return {"status": "healthy"}

        async def recover(self):
            return True 

    monkeypatch.setattr(
        internal_telemetry_manager,
        "track_healthcheck",
        lambda **payload: captured.append(payload),
    )

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    healthy = await exporter.healthcheck()
    await asyncio.sleep(0.2)

    assert healthy == True
    summary_snapshot = registry._health.model_dump().get("summary")
    assert summary_snapshot["total_exporters"] == 1
    assert summary_snapshot["healthy_count"] == 1
    assert summary_snapshot["down_count"] == 0

    key = registry._snapshot_key(exporter)
    snapshot = registry._health.model_dump().get("exporters")
    assert snapshot[key].get("status") == HealthStatus.HEALTHY
    assert snapshot[key].get("last_success_at") is not None
    assert snapshot[key].get("last_failure_at") is None
    assert snapshot[key].get("consecutive_failures") == 0
    assert snapshot[key].get("consecutive_successes") == 1

@pytest.mark.asyncio
async def test_healthcheck_false_populates_snapshot(monkeypatch):
    captured = []

    class CustomExporter(BaseExporter):
        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return False

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            return True

    monkeypatch.setattr(
        internal_telemetry_manager,
        "track_healthcheck",
        lambda **payload: captured.append(payload),
    )

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    healthy = await exporter.healthcheck()
    await asyncio.sleep(0.2)

    assert isinstance(healthy, bool)
    assert healthy == False
    summary_snapshot = registry._health.model_dump().get("summary")
    assert summary_snapshot["total_exporters"] == 1
    assert summary_snapshot["healthy_count"] == 0
    assert summary_snapshot["down_count"] == 1

    key = registry._snapshot_key(exporter)
    snapshot = registry._health.model_dump().get("exporters")
    assert snapshot[key].get("status") == HealthStatus.DOWN
    assert snapshot[key].get("last_success_at") is None
    assert snapshot[key].get("last_failure_at") is not None
    assert snapshot[key].get("consecutive_failures") == 1
    assert snapshot[key].get("consecutive_successes") == 0

@pytest.mark.asyncio
async def test_healthcheck_failure_populates_snapshot(monkeypatch):
    captured = []

    class CustomExporter(BaseExporter):
        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            raise Exception("Healthcheck failed")

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            return True

    monkeypatch.setattr(
        internal_telemetry_manager,
        "track_healthcheck",
        lambda **payload: captured.append(payload),
    )

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    try:
        healthy = await exporter.healthcheck()
    except Exception:
        healthy = False
    await asyncio.sleep(0.2)

    assert isinstance(healthy, bool)
    assert healthy == False
    summary_snapshot = registry._health.model_dump().get("summary")
    assert summary_snapshot["total_exporters"] == 1
    assert summary_snapshot["healthy_count"] == 0
    assert summary_snapshot["down_count"] == 1

    key = registry._snapshot_key(exporter)
    snapshot = registry._health.model_dump().get("exporters")
    assert snapshot[key].get("status") == HealthStatus.FAILURE
    assert snapshot[key].get("last_success_at") is None
    assert snapshot[key].get("last_failure_at") is not None
    assert snapshot[key].get("consecutive_failures") == 1
    assert snapshot[key].get("consecutive_successes") == 0

@pytest.mark.asyncio
async def test_consecutive_success_and_fail_healthchecks(monkeypatch):
    captured = []

    class CustomExporter(BaseExporter):
        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self, check: bool):
            if check:
                return True
            else:
                return False

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            return True

    monkeypatch.setattr(
        internal_telemetry_manager,
        "track_healthcheck",
        lambda **payload: captured.append(payload),
    )

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    await exporter.healthcheck(True)  # Simulate a successful healthcheck
    await asyncio.sleep(0.2)

    await exporter.healthcheck(False)  # Simulate a failed healthcheck
    await asyncio.sleep(0.2)

    key = registry._snapshot_key(exporter)
    snapshot = registry._health.model_dump().get("exporters")
    assert snapshot[key].get("consecutive_successes") == 0  # After a failed healthcheck, consecutive successes should reset to 0
    assert snapshot[key].get("consecutive_failures") == 1


# Check transition of health status

@pytest.mark.asyncio
async def test_health_status_transition(monkeypatch):
    captured = []

    class CustomExporter(BaseExporter):
        def __init__(self):
            self.healthy = True

        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return self.healthy

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            return True

    async def capture_healthcheck(snapshot):
        captured.append(snapshot.model_dump())

    monkeypatch.setattr(internal_telemetry_manager, "track_healthcheck", capture_healthcheck)

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry._update_exporter_health(
        exporter,
        HealthCheckSnapshot(
            exporter_name="CustomExporter",
            status=HealthStatus.STARTING,
        ),
    )
    await registry._run_healthcheck(exporter)

    exporter.healthy = False
    await registry._run_healthcheck(exporter)
    await registry._run_healthcheck(exporter)

    # The first two checks transition STARTING -> HEALTHY -> DOWN.
    # Repeating DOWN must not publish another transition.
    assert [event["status"] for event in captured] == [
        HealthStatus.HEALTHY.value,
        HealthStatus.DOWN.value,
    ]
    assert len(captured) == 2



def test_sdk_health_transition_is_logged_and_published(monkeypatch):
    registry = ExporterRegistry()
    registry._health = SDKHealthCheckSnapshot(status=SDKHealthStatus.STARTING)
    registry._health.exporters["Exporter"] = HealthCheckSnapshot(
        exporter_name="Exporter",
        status=HealthStatus.HEALTHY,
    )
    logged = []
    published = []

    monkeypatch.setattr(
        registry,
        "_log_sdk_health_transition",
        lambda previous, current: logged.append((previous, current)),
    )
    monkeypatch.setattr(
        registry,
        "_publish_sdk_health_transition",
        lambda previous, current: published.append((previous, current)),
    )

    registry._update_sdk_health()
    registry._update_sdk_health()

    assert registry._health.status == SDKHealthStatus.HEALTHY
    assert logged == [(SDKHealthStatus.STARTING, SDKHealthStatus.HEALTHY)]
    assert published == [(SDKHealthStatus.STARTING, SDKHealthStatus.HEALTHY)]


def test_sdk_health_is_degraded_when_all_active_exporters_are_down():
    registry = ExporterRegistry()
    registry._health = SDKHealthCheckSnapshot(status=SDKHealthStatus.STARTING)
    registry._health.exporters["Exporter"] = HealthCheckSnapshot(
        exporter_name="Exporter",
        status=HealthStatus.DOWN,
    )

    registry._update_sdk_health()

    assert registry._health.status == SDKHealthStatus.DEGRADED


# Chech recoveries

@pytest.mark.asyncio
async def test_health_recovery(monkeypatch):
    captured = []
    sdk_transitions = []

    class CustomExporter(BaseExporter):
        def __init__(self):
            self.healthy = False

        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return self.healthy

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            self.healthy = True
            return True

    async def capture_healthcheck(snapshot):
        captured.append(snapshot.model_dump())

    monkeypatch.setattr(internal_telemetry_manager, "track_healthcheck", capture_healthcheck)

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    monkeypatch.setattr(
        registry,
        "_publish_sdk_health_transition",
        lambda previous, current: sdk_transitions.append((previous, current)),
    )
    captured.clear()

    # The registry emits exporter health snapshots through track_healthcheck
    # and SDK transitions through _publish_sdk_health_transition separately.
    await asyncio.sleep(0.5)  # Allow the healthcheck worker to process the exporter

    assert [event["status"] for event in captured] == [
        HealthStatus.DOWN.value,
        HealthStatus.RECOVERING.value,
        HealthStatus.HEALTHY.value,
        HealthStatus.HEALTHY.value,
    ]
    assert len(captured) == 4
    assert sdk_transitions == [
        (SDKHealthStatus.STARTING, SDKHealthStatus.DEGRADED),
        (SDKHealthStatus.DEGRADED, SDKHealthStatus.HEALTHY),
    ]


@pytest.mark.asyncio
async def test_health_recovery_failed(monkeypatch):
    captured = []
    sdk_transitions = []

    class CustomExporter(BaseExporter):
        def __init__(self):
            self.healthy = False

        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return self.healthy

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            self.healthy = False
            return False

    async def capture_healthcheck(snapshot):
        captured.append(snapshot.model_dump())

    monkeypatch.setattr(internal_telemetry_manager, "track_healthcheck", capture_healthcheck)

    registry = ExporterRegistry()
    exporter = CustomExporter()
    registry.register(exporter)
    monkeypatch.setattr(
        registry,
        "_publish_sdk_health_transition",
        lambda previous, current: sdk_transitions.append((previous, current)),
    )
    captured.clear()

    # The regitry should on its own, throught the healthcheck worker,
    # attempt healcheck, emit a DOWN status, emit a RECOVERING status, 
    # attempt recover, emit a DEGRADED status on the sdk _and_ DOWN on the exporter, total of 4.
    await asyncio.sleep(1)  # Allow the healthcheck worker to process the exporter

    assert [event["status"] for event in captured] == [
        HealthStatus.DOWN.value,
        HealthStatus.RECOVERING.value,
        HealthStatus.DOWN.value,
        HealthStatus.FAILURE.value,
    ]
    assert len(captured) == 4
    assert sdk_transitions == [(SDKHealthStatus.STARTING, SDKHealthStatus.DEGRADED)]


@pytest.mark.asyncio
async def test_health_recovery_retries_until_success(monkeypatch):
    class RetryingExporter(BaseExporter):
        def __init__(self):
            self.recover_calls = 0
            self.healthy = False

        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return self.healthy

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            self.recover_calls += 1
            if self.recover_calls == 3:
                self.healthy = True
                return True
            return False

    async def no_sleep(_delay):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    registry = ExporterRegistry()
    registry._healthcheck_retry_policy = 3
    registry._healthcheck_recovery_timeout = 0.1
    registry._healthcheck_timeout = 0.1
    exporter = RetryingExporter()
    registry._update_exporter_health(
        exporter,
        HealthCheckSnapshot(
            exporter_name="RetryingExporter",
            status=HealthStatus.DOWN,
        ),
    )

    recovered = await registry._attempt_exporter_recovery(exporter)

    assert recovered is True
    assert exporter.recover_calls == 3
    assert registry._health.exporters[registry._snapshot_key(exporter)].status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_health_recovery_timeout_marks_exporter_as_failure():
    class HangingExporter(BaseExporter):
        def __init__(self):
            self.recover_calls = 0

        async def export_batch(self, event_batch):
            pass

        async def healthcheck(self):
            return False

        async def status(self):
            return {"status": "unhealthy"}

        async def recover(self):
            self.recover_calls += 1
            await asyncio.sleep(0.05)
            return True

    registry = ExporterRegistry()
    registry._healthcheck_retry_policy = 1
    registry._healthcheck_recovery_timeout = 0.001
    registry._healthcheck_timeout = 0.001
    exporter = HangingExporter()
    registry._update_exporter_health(
        exporter,
        HealthCheckSnapshot(
            exporter_name="HangingExporter",
            status=HealthStatus.DOWN,
        ),
    )

    recovered = await registry._attempt_exporter_recovery(exporter)

    assert recovered is False
    assert exporter.recover_calls == 1
    assert registry._health.exporters[registry._snapshot_key(exporter)].status == HealthStatus.FAILURE
