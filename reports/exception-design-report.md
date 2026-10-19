# AIMonitor Exception Design Report

## Purpose

This report defines a small, stable exception model for AIMonitor. The goal is
to give callers predictable library-level exceptions without hiding useful
backend-specific failures from logs or debugging tools.

The design is focused on the current exporter and registry contracts,
especially signal validation, exporter delivery, configuration, healthchecks,
and recovery.

## Current State

The repository currently contains a `SignalTypeNotFound` exception in
`src/aimonitor/core/exceptions.py`. The Kafka exporter raises it when a signal
cannot be mapped to a Kafka topic or is not included in the exporter's
supported signals.

This is a useful first step, but the exception is currently standalone. Other
exporter failures generally propagate backend exceptions directly or are
represented by boolean return values. That makes it difficult for applications
to distinguish:

- invalid AIMonitor input;
- invalid exporter configuration;
- an event that was not delivered;
- an exporter that is unavailable;
- a failed recovery attempt.

The exception model should improve that distinction without requiring every
backend error to become a new public AIMonitor class.

## Design Principles

### 1. Exceptions represent AIMonitor contracts

Custom exceptions should describe a failure at an AIMonitor boundary, not
mirror every error type exposed by Kafka, HTTP, SQLite, or another backend.

### 2. Preserve the original cause

When a backend exception is wrapped, it must remain available through exception
chaining:

```python
raise ExporterDeliveryError(message) from backend_error
```

This gives callers a stable AIMonitor type while preserving the original
diagnostic information.

### 3. Do not use exceptions as hidden control flow

The existing health model distinguishes between:

- a healthcheck returning `False`;
- a healthcheck raising or timing out;
- an export operation failing;
- recovery failing.

The exception model must preserve these distinctions rather than converting
every failure into either `False` or a generic exception.

### 4. Keep the public hierarchy small

The initial public API should contain only exceptions that callers can
reasonably handle. Backend-specific details should remain in the chained cause
and logs.

## Proposed Exception Hierarchy

```text
AIMonitorError
├── ConfigurationError
│   └── ExporterConfigurationError
├── SignalTypeNotFound
├── UnsupportedSignalError
└── ExporterError
    ├── ExporterDeliveryError
    ├── ExporterNotReadyError
    └── ExporterRecoveryError
```

An optional dependency error may also be introduced:

```text
OptionalDependencyError
```

It can inherit from both `AIMonitorError` and `ImportError` so existing
`ImportError` handling remains compatible.

## Exception Definitions

### `AIMonitorError`

The root exception for expected AIMonitor failures.

Applications that want to handle AIMonitor failures uniformly can catch this
type without catching unrelated application exceptions.

### `ConfigurationError`

Used when configuration is invalid or internally inconsistent.

Examples:

- an enabled exporter has no usable destination;
- a timeout is negative;
- mutually incompatible settings are selected.

### `ExporterConfigurationError`

A more specific configuration error raised while configuring or constructing an
exporter.

Examples:

- Kafka bootstrap servers are missing;
- an unsupported producer setting is passed to the client;
- a required optional dependency is unavailable;
- producer parameters cannot be accepted by the backend.

### `SignalTypeNotFound`

Used when an input signal contains an unknown or invalid signal type.

This exception should inherit from `ValueError` as well as
`AIMonitorError`, because the problem is invalid caller input.

The exception should retain the supplied value as an attribute:

```python
exception.signal_type
```

### `UnsupportedSignalError`

Used when the signal type is valid AIMonitor input but a particular exporter
does not support it.

This is distinct from `SignalTypeNotFound`. For example, an internal signal
may be valid within the SDK but intentionally excluded from a public Kafka
topic.

The exception should retain:

```python
exception.signal_type
exception.exporter_name
```

If the project prefers to avoid two signal-related exceptions initially,
`SignalTypeNotFound` can remain the only public type, but its message should
clearly distinguish “unknown” from “known but unsupported”.

### `ExporterError`

The base class for exporter lifecycle and operation failures.

It should not be used as a generic replacement for all exceptions. Prefer one
of its specific subclasses when the failure category is known.

### `ExporterDeliveryError`

Raised when an exporter cannot confirm delivery of an event or batch.

For Kafka this should wrap a failed delivery future:

```python
try:
    await delivery_future
except Exception as backend_error:
    raise ExporterDeliveryError(
        f"Kafka delivery failed for event {event.id}"
    ) from backend_error
```

This exception means the exporter operation did not complete successfully. It
should not be converted into a successful result merely because the message
was accepted into a local producer buffer.

### `ExporterNotReadyError`

Raised when an exporter operation is explicitly attempted while the exporter
is unavailable for use.

Examples:

- export is called after shutdown;
- the producer was never initialized;
- the exporter is in a terminal closed state.

The `healthcheck()` method does not necessarily need to raise this exception.
For the current registry contract, an unavailable exporter may return `False`
so the registry can record the exporter as down.

### `ExporterRecoveryError`

Represents a failed attempt to reconstruct or reconnect an exporter.

The current `recover()` contract returns `bool`, so this exception can first be
used as an internal wrapped/logged cause while `recover()` continues to return
`False`. Changing `recover()` to raise should be considered a separate,
repository-wide contract change.

### `OptionalDependencyError`

Used when an exporter cannot operate because its optional backend dependency is
not installed.

This is useful for callers that want to provide installation guidance without
matching a backend-specific import message.

It should remain compatible with normal import handling:

```python
class OptionalDependencyError(AIMonitorError, ImportError):
    ...
```

## Error Mapping by Operation

| Operation | Failure | Recommended result |
| --- | --- | --- |
| Configuration loading | Invalid general setting | `ConfigurationError` |
| Exporter construction | Invalid backend setting | `ExporterConfigurationError` |
| Exporter construction | Missing optional package | `OptionalDependencyError` |
| Signal validation | Unknown signal type | `SignalTypeNotFound` |
| Signal routing | Valid but unsupported signal | `UnsupportedSignalError` |
| Event serialization | Event cannot be encoded | `ExporterDeliveryError` or a later dedicated serialization error |
| Kafka delivery future | Broker rejects or times out | `ExporterDeliveryError` |
| Healthcheck | Probe completes and reports unavailable | Return `False` |
| Healthcheck | Probe raises or times out | Preserve exception for registry failure state |
| Recovery | Rebuild/reconnect fails | Return `False` under current contract, with chained/logged cause |
| Shutdown | Close fails | Log and continue registry shutdown, unless direct caller requests propagation |

## Registry Semantics

The exception hierarchy should align with the existing registry behavior in
`src/aimonitor/core/registry.py`:

- `export_batch()` raises an exporter operation exception:
  record the exporter operation as `FAILURE`.
- `healthcheck()` returns `False`:
  record the exporter as `DOWN`.
- `healthcheck()` raises or times out:
  record the exporter as `FAILURE`.
- `recover()` returns `False`:
  keep the exporter unhealthy and record recovery failure.
- `recover()` returns `True`:
  record recovery as completed, but do not mark the exporter healthy until a
  subsequent healthcheck succeeds.

This preserves the distinction between “recovery completed” and “the
destination has been verified healthy again”.

## Kafka-Specific Guidance

The Kafka exporter should use the exception model as follows:

1. Validate the signal before producing.
2. Raise `SignalTypeNotFound` for an unknown signal type.
3. Raise `UnsupportedSignalError` for valid signals that Kafka intentionally
   does not publish.
4. Await the coroutine returned by `AIOProducer.produce()`.
5. Await the delivery future returned by that coroutine.
6. Wrap delivery failures in `ExporterDeliveryError`, preserving the original
   Kafka exception as `__cause__`.
7. Do not publish a healthcheck event to a reserved Kafka topic.
8. Use metadata or an equivalent broker connectivity probe for healthchecks.
9. Use internal telemetry for healthcheck observations, through the existing
   `inner_telemetry` path.

A successful delivery future means Kafka acknowledged the record according to
the producer acknowledgement configuration. It does not mean that a consumer
processed the record.

## Logging and Information Safety

Exceptions and logs should not expose credentials. In particular:

- do not include the full producer configuration in exception messages;
- redact SASL passwords, tokens, and connection credentials;
- include event identifiers, signal types, exporter names, and backend error
  codes where safe;
- use exception chaining instead of interpolating complete backend objects into
  messages.

Example:

```text
Kafka delivery failed for event 7f... (topic=aimonitor-events)
```

Avoid logging the complete Kafka configuration or serialized event payload by
default.

## Recommended Adoption Plan

### Step 1: Establish the root types

Add `AIMonitorError`, `ConfigurationError`, and `ExporterError` while keeping
the existing `SignalTypeNotFound` behavior compatible.

### Step 2: Separate unknown and unsupported signals

Add `UnsupportedSignalError` only where the distinction is useful, beginning
with Kafka and internal signals.

### Step 3: Wrap delivery failures

Update exporters to raise `ExporterDeliveryError` only after preserving the
backend exception as the cause. Add focused tests for successful delivery,
delivery failure, and input-batch immutability.

### Step 4: Align healthcheck and recovery behavior

Keep healthcheck return values and recovery return values compatible with the
registry. Use the new exceptions for diagnostics and direct exporter callers
without changing the registry contract prematurely.

### Step 5: Apply the model to other exporters

Introduce shared contract tests covering configuration errors, delivery
errors, healthchecks, recovery, and shutdown. Do not create backend-specific
exception classes unless a caller-facing distinction is required.

## Decisions and Non-Goals

### Decisions

- Use a single AIMonitor root exception.
- Keep custom exceptions focused on stable library contracts.
- Preserve backend exceptions through exception chaining.
- Keep the current boolean healthcheck and recovery contracts initially.
- Treat internal health telemetry separately from application event export.

### Non-goals

- Replacing every backend exception.
- Designing a complete retry taxonomy in this phase.
- Changing the registry health state model.
- Promising end-to-end consumer processing when only broker delivery is known.

## Conclusion

AIMonitor needs a small exception hierarchy, not a large catalogue of backend
errors. The most valuable distinctions are:

1. invalid configuration;
2. invalid or unsupported signals;
3. exporter delivery failure;
4. exporter lifecycle failure;
5. optional dependency availability.

This model gives applications stable handling points while retaining the
original backend failure for diagnosis. It also supports the current registry
health semantics and keeps Kafka healthchecks separate from application event
topics and internal telemetry.
