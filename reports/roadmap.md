# AIMonitor Roadmap

## Purpose

This roadmap defines the next development objectives after merging the healthcheck and Kafka work. It prioritizes reliability and contract clarity before adding more exporters or operational features.

The guiding principles are:

- Keep the `ExporterRegistry` as the owner of exporter lifecycle and health state.
- Keep `healthcheck()`, `describe()`, export operations, and recovery as separate responsibilities.
- Prefer explicit contracts and focused tests over implicit compatibility behavior.
- Keep optional integrations isolated so the core SDK remains lightweight and safe to import.

## Current Baseline

The project currently provides:

- Cached exporter and SDK health snapshots.
- Explicit health states, including `STARTING`, `HEALTHY`, `DOWN`, `FAILURE`, `RECOVERING`, `STOPPED`, and `UNUSED`.
- Healthcheck retries, timeouts, transition tracking, recovery attempts, and shutdown handling.
- Separate liveness and readiness APIs.
- A `TelemetryProducer` / `TelemetryConsumer` split.
- A Kafka exporter with configurable producer settings.
- Initial configuration placeholders for MongoDB and PostgreSQL destinations, but no completed MongoDB or PostgreSQL exporters.
- MCP-oriented tool decorators, trace/span events, and OpenTelemetry integration.
- Nested configuration sections alongside the existing public configuration surface.
- Unit coverage for healthcheck lifecycle, configuration, telemetry, exporters, and bootstrap behavior.

The main remaining risk is not the absence of features. It is the consistency of behavior across exporters, configuration paths, integration environments, and operational failure modes.

## Priority Overview

Priorities are defined as follows:

- **P0:** Required to make the merged baseline reliable and usable.
- **P1:** Core product capabilities needed before expanding adoption.
- **P2:** Hardening, scale, and release-quality improvements after the core contracts are stable.

| Priority | Phase | Objective | Outcome |
| --- | --- | --- | --- |
| P0 | Phase 0 | Stabilize the merged baseline | A reproducible test suite and clear integration-test contract. |
| P0 | Phase 1 | Harden Kafka production behavior | Correct producer configuration, delivery semantics, lifecycle, and recovery. |
| P1 | Phase 2 | Complete the configuration refactor | One canonical nested configuration model with predictable precedence and validation. |
| P1 | Phase 3 | Formalize the exporter contract | Consistent behavior for export, healthcheck, description, recovery, and shutdown. |
| P1 | Phase 4 | Add general-purpose persistence exporters | Reliable MongoDB and PostgreSQL exporters for AI events, traces, metrics, and governance records. |
| P1 | Phase 5 | Add AI usage governance | Token, model, cost, policy, and budget data with privacy and aggregation controls. |
| P1 | Phase 6 | Add A2A protocol governance | Instrument agent-to-agent interactions in addition to the existing MCP tool coverage. |
| P1 | Phase 7 | Improve operational observability | Useful internal metrics and safe diagnostics without creating a second health model. |
| P2 | Phase 8 | Expand performance and reliability coverage | Evidence about queue pressure, concurrency, retries, and long-running processes. |
| P2 | Phase 9 | Prepare a release-quality developer experience | Stable documentation, examples, packaging, and release criteria. |

## Phase 0: Stabilize the Baseline

**Priority:** P0  
**Goal:** Make the merged state reproducible and distinguish product failures from environment-dependent integration failures.

### Work items

- Run the complete unit and integration test matrix in a clean virtual environment.
- Define which tests require external services such as Kafka or Prometheus.
- Mark service-dependent tests explicitly and document the required broker or service setup.
- Resolve test collection conflicts and keep unique test module names.
- Add a CI matrix for:
  - core unit tests without optional integrations;
  - Kafka integration tests with a real broker;
  - Prometheus integration tests with the supported signal types;
  - optional dependency import checks.
- Record supported Python versions and dependency versions in the project documentation.

### Exit criteria

- Unit tests pass without external services.
- Integration tests either pass in CI or are explicitly gated behind documented service fixtures.
- A clean checkout can reproduce the documented commands.
- Failures identify a product defect instead of an unavailable local dependency.

## Phase 1: Kafka Production Hardening

**Priority:** P0  
**Goal:** Turn the merged Kafka exporter into a predictable production integration.

### Work items

- Align `KafkaExporter` constructor arguments with the installed `AIOProducer` API.
- Stop passing unsupported producer arguments directly to the client.
- Define the mapping between nested Kafka configuration and the actual client configuration.
- Decide which settings are client-supported, exporter-owned, or unsupported and validate them accordingly.
- Make delivery failure semantics explicit:
  - what `produce()` success means;
  - when callbacks report delivery errors;
  - when a batch is considered complete;
  - how `BufferError` and flush failures affect exporter health.
- Review event serialization so payloads are encoded once and preserve the expected JSON shape.
- Make `close()` idempotent and safe during partial initialization.
- Make `recover()` rebuild or reconnect the actual `AIOProducer` using the original configuration.
- Add healthcheck tests for successful delivery, broker failure, timeout, and recovery.
- Add a real Kafka integration test covering export, healthcheck, shutdown, and restart.

### Exit criteria

- Kafka initialization works with the supported `confluent-kafka` version.
- Unsupported arguments are rejected during validation or ignored intentionally with documentation.
- Delivery errors are observable and cannot silently leave events in an inconsistent state.
- Kafka recovery is tested against a stopped and restarted broker.

## Phase 2: Configuration Consolidation

**Priority:** P1  
**Goal:** Finish the move from a flat, alias-heavy configuration surface to a canonical nested model without hidden runtime mutation.

### Work items

- Treat nested sections as the canonical internal representation:
  - `app`;
  - `tracking`;
  - `telemetry`;
  - `exporters`.
- Keep legacy flat fields only where they are still part of the active development contract, and define their precedence explicitly.
- Reduce alias sprawl and document accepted YAML and environment variable names.
- Validate cross-field requirements, such as an enabled exporter requiring a usable destination.
- Keep secrets represented by `SecretStr` or equivalent protected types throughout configuration loading.
- Ensure bootstrap constructs exporters from configuration without mutating settings.
- Separate configuration reset from registry and exporter lifecycle reset.
- Add tests for YAML, environment variables, nested sections, precedence, invalid values, and reset behavior.

### Exit criteria

- Every runtime setting has one canonical location.
- YAML and environment precedence is documented and tested.
- Bootstrap behavior is deterministic and does not modify the settings object.
- Invalid optional integration settings fail early with actionable messages.

## Phase 3: Formal Exporter Contract

**Priority:** P1  
**Goal:** Make every exporter obey the same lifecycle and failure model.

### Work items

- Document the required behavior of:
  - `export()`;
  - `export_batch()`;
  - `healthcheck()`;
  - `describe()`;
  - `recover()`;
  - `close()`.
- Ensure `healthcheck()` returns a boolean or raises consistently across exporters.
- Ensure `describe()` remains diagnostic-only and never controls readiness.
- Define whether exporter operation failures are represented separately from healthcheck `DOWN` and `FAILURE` states.
- Make close and recovery behavior idempotent for every exporter.
- Review all exporters for swallowed exceptions, unbounded retries, resource leaks, and inconsistent logging.
- Keep failed exporters in the registry when recovery and lifecycle history require them.
- Add contract tests that can run against every exporter with fake dependencies.

### Exit criteria

- A shared exporter contract test suite passes for all built-in exporters.
- Readiness always comes from registry snapshots.
- Export failures, healthcheck failures, and recovery failures are distinguishable in logs and snapshots.
- Shutdown does not leave workers, connections, or tasks running.

## Phase 4: General-Purpose Persistence Exporters

**Priority:** P1  
**Goal:** Support durable storage systems that are useful for analysis, audit, replay, and governance, not only monitoring backends.

### Work items

- Define a storage-oriented exporter contract for MongoDB and PostgreSQL.
- Decide which signals are stored directly and which are materialized into query-friendly records:
  - tool and agent events;
  - spans and traces;
  - metrics;
  - health snapshots;
  - AI usage and governance records.
- Implement a MongoDB exporter with explicit collection naming, indexes, document size limits, and connection lifecycle handling.
- Implement a PostgreSQL exporter with explicit table/schema ownership, indexes, migrations, and transaction boundaries.
- Keep event identity and timestamps stable across retries so persistence retries are idempotent.
- Define serialization rules for arbitrary tool arguments, results, errors, and metadata.
- Redact configured sensitive fields before persistence and avoid storing credentials by default.
- Add healthchecks, recovery, shutdown, and integration fixtures for both databases.
- Document retention, schema evolution, and migration expectations.

### Exit criteria

- MongoDB and PostgreSQL exporters implement the common exporter contract.
- Retries do not create uncontrolled duplicates for records with the same event identity.
- Schemas and indexes support the documented query and retention use cases.
- Database credentials and sensitive payload fields are protected by default.
- Integration tests run against supported database versions.

## Phase 5: AI Usage Governance

**Priority:** P1  
**Goal:** Make model usage, token consumption, cost, and policy decisions first-class observability data.

### Work items

- Define a provider-neutral usage model covering:
  - provider and model name;
  - request and response token counts;
  - cached, reasoning, input, and output tokens when available;
  - latency and completion status;
  - request, trace, tool, and agent identifiers;
  - pricing metadata and estimated cost.
- Add explicit model and provider metadata to the relevant event/span context without requiring sensitive prompt or response capture.
- Support usage reporting when providers expose usage data and make missing usage explicit instead of guessing silently.
- Add configurable cost models with versioned pricing metadata and a clear distinction between estimated and provider-reported cost.
- Add budgets and thresholds by application, tenant, user, agent, model, provider, and time window.
- Emit governance events for budget warnings, budget exhaustion, policy violations, and missing usage data.
- Define enforcement modes:
  - observe only;
  - warn;
  - reject or stop before a request is sent.
- Add privacy controls for prompts, completions, tool arguments, and results, including allowlists and redaction policies.
- Make governance data exportable through the same persistence and Kafka paths without coupling policy evaluation to a backend.
- Add tests for token aggregation, cost calculation, budget windows, missing metadata, retries, and concurrent updates.

### Exit criteria

- Token and cost records are consistent across supported model providers.
- Estimated costs are clearly marked and reproducible from versioned pricing data.
- Budgets can be observed and enforced deterministically.
- Governance controls do not require storing raw prompts or completions.
- Usage and policy data can be correlated with tool, trace, and agent activity.

## Phase 6: A2A Protocol Governance

**Priority:** P1  
**Goal:** Extend governance and observability from MCP tool calls to agent-to-agent communication.

### Work items

- Define an A2A-neutral event model for:
  - agent identity and role;
  - source and target agent;
  - task or conversation identifier;
  - message and artifact metadata;
  - request, response, delegation, and error lifecycle;
  - protocol version and transport metadata.
- Separate protocol instrumentation from MCP decorators so A2A integrations do not depend on tool-specific assumptions.
- Add a context propagation model that carries trace, tenant, policy, and budget identifiers across agent boundaries.
- Define how A2A calls map to existing events and spans without flattening multi-agent relationships.
- Add instrumentation hooks for outbound requests, inbound requests, delegation, cancellation, timeout, and retries.
- Track token and cost usage per agent, task, delegation chain, and overall workflow.
- Add policy controls for allowed agents, delegation depth, trust boundaries, data classification, and tool permissions.
- Support privacy-safe correlation when payloads cannot be exported across agent boundaries.
- Add conformance tests using a fake A2A transport before integrating a concrete protocol implementation.

### Exit criteria

- A2A interactions have stable identifiers and trace relationships.
- MCP and A2A telemetry can be correlated without sharing an ambiguous event type.
- Delegation, retries, timeouts, and policy violations are observable.
- Governance decisions can be applied at agent boundaries.
- The protocol layer remains optional and does not add a mandatory runtime dependency to the core SDK.

## Phase 7: Operational Observability

**Priority:** P1  
**Goal:** Make runtime behavior diagnosable without coupling the SDK to a telemetry backend.

### Work items

- Add registry-owned runtime metrics such as:
  - queue size and capacity;
  - active workers;
  - batches processed;
  - events processed;
  - export failures;
  - retry counts;
  - last flush duration;
  - healthcheck duration;
  - recovery attempts.
- Add snapshot staleness information so consumers can distinguish an unhealthy exporter from an old result.
- Emit structured transition events for exporter and SDK health changes.
- Keep `TelemetryProducer` best-effort and non-blocking for application operations.
- Keep `TelemetryConsumer` local and read-only; do not add backend queries to the core API.
- Redact credentials and sensitive connection details from diagnostics and logs.
- Define log levels and message formats for repeated healthcheck and recovery failures.

### Exit criteria

- Operators can explain why an exporter is unhealthy from snapshots and logs.
- Queue saturation and slow batches are visible without enabling an external backend.
- Telemetry failures never break export or lifecycle operations.
- Diagnostic output contains no secrets.

## Phase 8: Performance and Reliability

**Priority:** P2  
**Goal:** Validate the SDK under sustained load and dependency degradation.

### Work items

- Measure throughput and latency for single and batched events.
- Test queue pressure, worker limits, flush intervals, and backpressure behavior.
- Verify that healthcheck timeouts do not block unrelated exporters.
- Test concurrent recovery attempts and ensure only one recovery runs per exporter.
- Test repeated broker or backend outages followed by recovery.
- Add cancellation tests for shutdown while export, healthcheck, or recovery is in progress.
- Evaluate optional process metrics such as CPU and RSS only if queue and exporter metrics show a real need.
- Establish baseline performance targets for supported exporters.

### Exit criteria

- No unbounded task or queue growth under the documented workload.
- Shutdown completes within a documented bound.
- Recovery and healthcheck loops remain bounded during prolonged outages.
- Performance regressions can be detected in CI or scheduled benchmarks.

## Phase 9: Release Readiness

**Priority:** P2  
**Goal:** Prepare a coherent public release once the runtime contracts are stable.

### Work items

- Update README and all `/docs` pages to match the current API and configuration model.
- Add complete examples for liveness, readiness, health snapshots, Kafka, and optional telemetry.
- Document supported dependency extras and external service requirements.
- Review public imports and remove accidental internal APIs.
- Define semantic versioning rules for exporter and configuration contract changes.
- Add a changelog entry describing health states, recovery, Kafka support, and breaking API changes.
- Verify package metadata, optional dependencies, and source distribution contents.
- Create a release checklist covering tests, documentation, security review, and rollback guidance.

### Exit criteria

- Documentation examples execute against the current public API.
- Optional integrations can be installed independently.
- Breaking changes are visible in the changelog and migration notes.
- Release artifacts can be built and validated from a clean checkout.

## Decisions to Make Before Further Expansion

These decisions should be recorded in tests and documentation before adding more exporters:

1. Should SDK readiness be strict when any exporter is `DOWN`, or `DEGRADED` while another exporter remains healthy?
2. Should `RECOVERING` count as ready, unhealthy, or degraded for host applications?
3. Should stale snapshots produce a separate status or only an explicit `stale` field?
4. Should export-operation failures have their own status instead of sharing `FAILURE` with healthcheck execution failures?
5. Should the registry retain failed exporters indefinitely, or should removal require an explicit administrative action?
6. Should recovery reconnect existing instances only, or should exporters support factory-based recreation?
7. Which configuration aliases remain supported during development, and when can they be removed?
8. Which optional integrations are release-blocking and which are best-effort extras?
9. Which model providers and pricing sources are supported for the first governance release?
10. Should governance enforcement be implemented in the SDK, delegated to the host application, or both?
11. Which A2A protocol version and transport should be the first conformance target?
12. Which payload fields are allowed to cross agent boundaries by default?

## Recommended Next Sequence

1. Fix and test Kafka producer compatibility and delivery semantics.
2. Establish a clean CI test matrix with explicit external-service fixtures.
3. Complete configuration precedence and validation tests.
4. Add shared exporter contract tests.
5. Implement MongoDB and PostgreSQL persistence exporters.
6. Define AI usage, cost, budget, and privacy governance.
7. Define the A2A event and context propagation contracts.
8. Add registry runtime metrics and snapshot staleness.
9. Run sustained-load and failure-recovery tests.
10. Update release documentation and package metadata.
