# Healthcheck, State, and Recovery Design

## 1. Objective

AIMonitor healthchecks should provide four capabilities:

1. Determine whether the process is alive.
2. Determine whether registered exporters are ready to work.
3. Preserve the last result of each healthcheck, including timestamps and errors.
4. Attempt recovery from transient exporter failures without hiding persistent failures.

The design is incremental and should support learning about state, lifecycle, concurrency, and fault tolerance.

## 2. Current state

The public API separates three concepts:

- `get_process_liveness()` is cheap and must not contact external dependencies.
- `get_sdk_readiness()` reports registered exporters and their dependencies.
- `get_telemetry_status()` checks local OpenTelemetry provider availability.

`get_sdk_readiness()` reads the cached snapshot in `ExporterRegistry`. It does not perform extra probes during a request, and the snapshot is the source of truth.

The registry worker is also responsible for registration, export workers, queues, shutdown, and recovery. Therefore, the registry is the natural owner of exporter lifecycle and health state.

## 3. Health state ownership

Do not create another singleton for health state. The state belongs to `ExporterRegistry`, which owns:

- Registered exporters.
- The healthcheck worker.
- `register()` and `shutdown()`.
- Recovery attempts.
- The relationship between an exporter instance and its health result.

The registry should keep private state keyed by exporter instance identity:

```python
self._health: dict[int, ExporterHealth] = {}
```

Instance identity is important because two exporters of the same class may use different destinations.

The public API must not expose the mutable dictionary. `health_snapshot()` should return a serializable copy:

```python
snapshot = registry.health_snapshot()
```

## 4. Recommended state model

Use a structured `dataclass` rather than an untyped dictionary:

```python
@dataclass
class ExporterHealth:
    status: str = "starting"
    last_check_started_at: datetime | None = None
    last_check_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    message: str = ""
```

### States

| State | Meaning |
| --- | --- |
| `starting` | The exporter is registered, but no healthcheck has completed. |
| `healthy` | The latest healthcheck completed successfully. |
| `recovering` | A failure occurred and reconnection or reconstruction is in progress. |
| `down` | The exporter should be active, but a healthcheck reports a persistent failure. |
| `stopped` | The exporter was deliberately stopped during shutdown or administration. |
| `unused` | The exporter is disabled, has no configured destination, or does not participate in active execution. |

`starting`, `stopped`, `down`, and `unused` describe different situations and must not be used interchangeably.

## 5. Timestamps and snapshots

Track at least:

- `checked_at`: when the current snapshot is created.
- `last_check_started_at`: when the latest healthcheck started.
- `last_check_finished_at`: when the latest healthcheck finished.
- `last_success_at`: the latest successful check.
- `last_failure_at`: the latest failed check.

Use timezone-aware UTC timestamps:

```python
from datetime import UTC, datetime

now = datetime.now(UTC)
```

Example snapshot:

```json
{
  "status": "degraded",
  "checked_at": "2026-10-08T19:30:00.120000+00:00",
  "summary": {
    "total_exporters": 2,
    "healthy_count": 1,
    "recovering_count": 1,
    "down_count": 0
  },
  "exporters": [
    {
      "name": "PrometheusExporter",
      "status": "healthy",
      "last_check_finished_at": "2026-10-08T19:29:59.900000+00:00",
      "last_success_at": "2026-10-08T19:29:59.900000+00:00",
      "last_failure_at": null,
      "consecutive_failures": 0,
      "message": "Exporter is operational."
    }
  ]
}
```

`describe()` may return exporter-specific diagnostics, but it is not the source of health history or registry state. The health worker records one result after every check.

### Healthcheck result contract

The registry distinguishes an unhealthy exporter from a healthcheck execution failure:

- `HEALTHY`: the healthcheck completed and returned `True`.
- `DOWN`: the healthcheck completed and returned `False`.
- `FAILURE`: the healthcheck raised or timed out.
- `RECOVERING`: recovery is being attempted after an unhealthy result.

Both `DOWN` and `FAILURE` contribute to unhealthy counts. Their separate values preserve the diagnosis for operators and telemetry consumers.

## 6. Separate responsibilities

- `healthcheck()` performs an active probe and may contact a dependency.
- `describe()` returns diagnostic information.
- `health_snapshot()` returns historical state maintained by the registry.

`get_sdk_readiness()` must read the cached snapshot rather than launch a new probe or invoke `describe()`. This keeps readiness predictable and cheap.

Readiness can therefore be slightly stale. Expose `last_check_finished_at`, and optionally `stale: true` when the result exceeds a maximum age.

## 7. Timeout and interval

The interval determines how often a healthcheck runs. The timeout determines how long one check may take. They do not need to share a value:

```text
healthcheck_interval = 60 seconds
healthcheck_timeout = 5 seconds
```

The initial implementation should retain a sequential loop and add a separate timeout. A sequential loop is easier to test and avoids a burst of tasks, although a slow exporter can delay later exporters.

## 8. Automatic recovery

Recovery is useful, but it must not be confused with export retries.

### Operation retries

Export retries target one operation:

```text
send batch -> send fails -> retry send
```

Their purpose is to tolerate a temporary network or dependency failure.

### Exporter recovery

Recovery owns the lifecycle of an exporter instance:

```text
healthcheck fails
  -> record failure
  -> mark recovering
  -> close or reconnect
  -> healthcheck again
  -> healthy or down
```

Do not reuse the `export()` retry decorator for recovery. They are separate policies with different limits, logs, and consequences.

The base contract may include:

```python
async def recover(self) -> bool:
    await self.close()
    await self.connect()
    return True
```

Not every exporter has a connection that can be reconstructed. A default implementation may return `False`, or recovery may explicitly check for a supported `recover()` implementation.

### Minimum recovery policy

```python
recovery_enabled = True
recovery_max_attempts = 3
recovery_backoff_seconds = 5.0
```

Recommended flow:

1. The first failure updates state and counters.
2. The exporter enters `recovering` if recovery is enabled.
3. `recover()` runs with bounded backoff.
4. A healthcheck follows recovery.
5. A successful healthcheck restores `healthy`.
6. Exhausted attempts produce `down`.
7. The exporter is retained in the registry.

Do not recover indefinitely. Permanent reconnection loops create noise, consume resources, and pressure already unavailable services.

If the registry must rebuild a complete exporter, it needs a factory or creator function because it does not always know constructor arguments. The first step should be `close()` plus `connect()`; reconstruction can be added later.

## 9. Export failures

The registry should not remove an exporter immediately after `_send_batch()` fails. Immediate removal:

- Makes it disappear from readiness.
- Loses its health history.
- Prevents automatic recovery through the registry.

Prefer retaining the exporter, marking it `down` or `recovering`, and optionally skipping exports temporarily. A removal policy requires a separate configured-exporter registry and a factory for arbitrary instances.

## 10. Reset and lifecycle

Do not place exporter state inside `AIMonitorSettings.reset()`. Configuration and runtime state are separate responsibilities.

Recommended separation:

```python
async def shutdown(self) -> None:
    """Stop workers and close exporters."""

async def reset(self) -> None:
    """Reset runtime state for tests or reconfiguration."""
    await self.shutdown()
    self._health.clear()
```

`shutdown()` represents a real stop and may leave exporters `stopped` in the final snapshot.

`reset()` is used for tests or complete reconfiguration and removes history.

The telemetry manager has its own reset, but it must not own health state. Telemetry observes and emits data; the registry controls lifecycle.

## 11. Resource metrics

Queue and worker metrics are useful but should not block the first implementation:

```json
{
  "queue_size": 12,
  "queue_capacity": 1000,
  "active_workers": 5,
  "batches_processed": 240,
  "events_processed": 12000,
  "export_failures": 3,
  "last_flush_duration_ms": 18.4
}
```

Process CPU and RSS may be collected with `psutil`, but exporter- or thread-level CPU attribution should not be implemented initially.

Start by measuring queue depth, workers, batch duration, and failures.

## 12. Required tests

Add focused tests for:

- Initial `starting` state.
- Successful healthcheck.
- `False` healthcheck result.
- Raised healthcheck and timeout.
- Recovery success and recovery exhaustion.
- Reset behavior.
- Stale snapshot handling.
- Shutdown transition to `stopped`.

## 13. Recommended implementation order

1. Add the private `ExporterHealth` model.
2. Record healthcheck start and finish timestamps.
3. Add `health_snapshot()` and use it from the public readiness API.
4. Separate `DOWN`, `FAILURE`, and `RECOVERING`.
5. Add healthcheck timeout.
6. Add bounded recovery.
7. Retain failed exporters in the registry.
8. Add resource metrics only after the lifecycle contract is stable.

## 14. Decisions to make explicit

For every exporter, document:

- Whether it supports healthchecks.
- Whether it supports recovery.
- Which result is `down` versus `failure`.
- What happens during close.
- Whether delivery is acknowledged synchronously or asynchronously.

Record these decisions in tests and operational documentation.

## 15. Merge readiness

The implementation should not be merged until the complete test suite can be collected and executed successfully.

The initial test suite had a module collection conflict because two test modules shared the same basename. Renaming the Kafka integration module resolved collection. Integration tests still require a Kafka broker when enabled.

Before calling the design stable:

- Resolve product defects in Kafka delivery configuration.
- Align Prometheus integration tests with supported signal types.
- Verify shutdown and restart behavior.
- Confirm that unit tests pass without external services.
- Document how external integration fixtures are enabled.

## 16. Telemetry producer and consumer contract

The telemetry API has two explicit responsibilities:

- `TelemetryProducer` emits SDK observations.
- `TelemetryConsumer` reads registry health and local OpenTelemetry status.

The producer never owns health state. The registry owns snapshots, transitions, counters, and recovery.

Canonical public functions:

```python
get_process_liveness
get_sdk_readiness
get_telemetry_status
```

The legacy `get_liveness()`, `get_readiness()`, `track_*`, and exporter-`describe()`-based status helpers should not remain public.
