# AIMonitor Roadmap

## Purpose

This roadmap defines the next development objectives after the healthcheck and Kafka work. The current development focus is to improve the reliability and consistency of every exporter already available before adding new integrations or operational features.

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
- Built-in exporters for Console, File, SQLite, Webhook/HTTP, Prometheus, and OpenTelemetry.
- Initial configuration placeholders for MongoDB and PostgreSQL destinations, but no completed MongoDB or PostgreSQL exporters.
- MCP-oriented tool decorators, trace/span events, and OpenTelemetry integration.
- A framework-agnostic decorator path, but no native FastMCP, smolagents, or LangChain adapters.
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
| P1 | Phase 3 | Improve all built-in exporters | Consistent behavior, failure semantics, lifecycle, and focused coverage across the existing exporter set. |
| P1 | Phase 4 | Add framework compatibility adapters | Instrument FastMCP, LangChain, and smolagents through optional, framework-specific adapters that emit one canonical AIMonitor model. |
| P1 | Phase 5 | Add general-purpose persistence exporters | Reliable MongoDB and PostgreSQL exporters for AI events, traces, metrics, and governance records. |
| P1 | Phase 6 | Add AI usage governance | Token, model, cost, policy, and budget data with privacy and aggregation controls. |
| P1 | Phase 7 | Add A2A protocol governance | Instrument agent-to-agent interactions in addition to the existing MCP and framework coverage. |
| P1 | Phase 8 | Improve operational observability | Useful internal metrics and safe diagnostics without creating a second health model. |
| P2 | Phase 9 | Expand performance and reliability coverage | Evidence about queue pressure, concurrency, retries, and long-running processes. |
| P2 | Phase 10 | Prepare a release-quality developer experience | Stable documentation, examples, packaging, and release criteria. |

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

## Phase 3: Built-in Exporter Reliability and Contract

**Priority:** P1  
**Goal:** Improve the reliability of every exporter already shipped with AIMonitor while keeping their backend-specific behavior explicit.

**Scope:** Kafka, Prometheus, OpenTelemetry, Webhook/HTTP, File, SQLite, and Console exporters. This phase does not add MongoDB or PostgreSQL exporters; those remain in Phase 5.

### Work items

- Create an exporter matrix documenting each exporter's configuration, optional dependencies, delivery guarantees, resource ownership, failure behavior, recovery support, and existing tests.
- Document the required behavior of:
  - `export()`;
  - `export()`;
  - `healthcheck()`;
  - `describe()`;
  - `recover()`;
  - `close()`.
- Ensure `healthcheck()` returns a boolean or raises consistently across exporters.
- Ensure `describe()` remains diagnostic-only and never controls readiness.
- Define whether exporter operation failures are represented separately from healthcheck `DOWN` and `FAILURE` states.
- Make close and recovery behavior idempotent for every exporter.
- Implement and test the close lifecycle contract for built-in exporters: successful closure publishes the stopped lifecycle event and updates the registry health snapshot to `STOPPED`; cleanup failures remain observable.
- Document how users design custom exporters, including the `BaseExporter` interface, supported signals, configuration and optional dependencies, error handling, health reporting, recovery, idempotent cleanup, and lifecycle reporting.
- Review all exporters for swallowed exceptions, unbounded retries, resource leaks, and inconsistent logging.
- Add focused unit and integration coverage for each exporter's success path, invalid or unavailable destination, operation failure, and cleanup behavior, using external services only where required.
- Keep failed exporters in the registry when recovery and lifecycle history require them.
- Add shared contract tests that can run against every compatible exporter with fake dependencies, plus exporter-specific tests where the backend semantics differ.
- Include a minimal custom-exporter example and guidance for testing it against the documented contract.
- Fix gaps one exporter at a time, preserving its documented payload and delivery semantics.

### Exit criteria

- Every built-in exporter has a documented contract and targeted tests for its supported behavior.
- Shared exporter contract tests pass for all compatible built-in exporters.
- Readiness always comes from registry snapshots.
- Export failures, healthcheck failures, and recovery failures are distinguishable in logs and snapshots.
- Closing a built-in exporter leaves a `STOPPED` health snapshot and publishes the lifecycle transition.
- The custom-exporter guide explains the extension contract and the lifecycle responsibilities of third-party implementations.
- Shutdown does not leave workers, connections, or tasks running.

## Phase 4: Framework Compatibility Adapters

**Priority:** P1
**Difficulty:** Medium to high
**Dependencies:** Phase 2 configuration consolidation and Phase 3 exporter contract
**Goal:** Instrument common AI application frameworks without coupling the AIMonitor core to their optional dependencies or lifecycle models.

### Why this phase is P1

The current SDK can decorate generic functions, but framework-native integrations
are needed for reliable coverage of framework-managed tools, agents, model calls,
retrievers, middleware, and nested runs. This phase should happen before usage
governance and persistence work so those later phases consume one stable,
framework-neutral event and correlation model instead of implementing separate
translations.

This is not a P0 reliability requirement for the existing MCP SDK. It is a P1
adoption and product-capability phase. The core package must remain usable
without installing any supported framework.

### Integration difficulty

| Integration | Difficulty | Preferred mechanism | Main risks |
| --- | --- | --- | --- |
| FastMCP | Medium | Native middleware, especially `on_call_tool` | Versioned middleware API, typed result preservation, cancellations, multi-round calls, duplicate decorator instrumentation |
| LangChain | Medium to high | Callback handler based on documented run lifecycle | Large callback surface, streaming, nested parent/child runs, token usage variants, duplicate callbacks |
| smolagents | High for native hooks; medium through OpenTelemetry | OpenTelemetry/OpenInference bridge first; native callbacks only when stable | Framework internals may change, agent-step semantics vary, model/tool usage may be incomplete |

### Common compatibility architecture

- Add a framework-neutral run/span context with:
  - `run_id`;
  - `trace_id`;
  - `span_id`;
  - `parent_id`;
  - framework name;
  - operation name;
  - agent, session, and tenant identifiers where available.
- Add a generic run event model for:
  - agent runs;
  - agent steps;
  - tool executions;
  - model invocations;
  - chains;
  - retrieval;
  - errors and cancellations.
- Preserve the existing `MCPEvent` and decorator behavior for compatibility.
- Use `contextvars` to propagate parent-child relationships across async tasks.
- Define an adapter protocol with explicit `instrument()` and `uninstrument()`
  lifecycle methods.
- Route all adapter events through the existing observability API and registry;
  adapters must not implement their own queues, exporters, or health model.
- Preserve framework-provided run IDs and parent IDs when they are available.
- Keep framework dependencies out of `aimonitor.core` and load them only from
  optional integration modules.

### Phase 4.1: Define the framework-neutral contract

- Add a generic run/span abstraction without replacing existing MCP event types.
- Define operation names such as:
  - `mcp.tool`;
  - `agent.run`;
  - `agent.step`;
  - `tool.execute`;
  - `llm.invoke`;
  - `chain.run`;
  - `retriever.query`.
- Add source framework and source run identifiers to event metadata or the
  generic event model.
- Define how results, errors, cancellation, duration, and usage are represented.
- Define payload capture controls:
  - capture inputs;
  - capture outputs;
  - capture prompts;
  - capture tool arguments;
  - capture retrieved documents;
  - capture token usage;
  - maximum payload size.
- Apply the existing redaction policy before events enter the registry.
- Define a duplicate-detection key using framework, source run ID, operation, and
  trace context where reliable.

### Phase 4.2: Implement FastMCP middleware

- Add an optional `aimonitor.integrations.fastmcp` module.
- Implement middleware around tool calls using the documented operation hook.
- Capture tool name, arguments, result, duration, errors, cancellation, and
  request context.
- Preserve FastMCP result types and re-raise original application exceptions.
- Handle multi-round or input-required calls as separate framework requests.
- Document whether users should use middleware, `@monitor_tool`, or neither when
  both are available.
- Add tests for successful calls, validation failures, tool exceptions,
  cancellation, nested calls, and duplicate instrumentation.

### Phase 4.3: Implement LangChain callbacks

- Add an optional `aimonitor.integrations.langchain` module based on the
  documented callback interface.
- Map chain, LLM, tool, retriever, agent, and error callbacks to the common model.
- Preserve LangChain `run_id` and `parent_run_id`.
- Support non-streaming and streaming lifecycle events without emitting
  duplicate completion records.
- Capture provider/model and token usage when LangChain exposes them; represent
  missing usage explicitly rather than estimating silently.
- Ensure callback failures never break the LangChain application path.
- Add tests for nested chains, model success and failure, tool calls, retrievers,
  streaming, parent-child relationships, and usage metadata.

### Phase 4.4: Implement smolagents compatibility

- Start with an optional OpenTelemetry/OpenInference integration because
  smolagents already supports an instrumentation ecosystem.
- Translate agent, managed-agent, model, step, and tool spans into the common
  AIMonitor model where the source data is available.
- Add native smolagents hooks only when the supported versions expose stable,
  documented lifecycle callbacks.
- Do not monkey-patch private smolagents implementation details.
- Add tests for a single agent run, managed agents, tool errors, model errors,
  multi-step traces, and usage metadata.

### Phase 4.5: Package and document optional integrations

- Add independent extras for `fastmcp`, `langchain`, and `smolagents`.
- Keep `import aimonitor` free of optional framework imports.
- Add optional-dependency import checks to CI.
- Document supported framework version ranges and adapter limitations.
- Provide one minimal example per framework.
- Document coexistence with OpenTelemetry, OpenInference, and native framework
  instrumentation to reduce duplicate events.

### Exit criteria

- The core package runs without any framework dependency installed.
- FastMCP tool calls can be captured through middleware without changing their
  response or exception behavior.
- LangChain runs, model calls, tools, and retrievers share stable parent-child
  correlation.
- smolagents is supported through a documented OpenTelemetry path, with native
  hooks only where version stability is demonstrated.
- Inputs, outputs, prompts, and retrieved documents obey explicit capture and
  redaction policies.
- Duplicate instrumentation is detectable and tested.
- All adapters use the existing registry and exporter lifecycle.

## Phase 5: General-Purpose Persistence Exporters

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

## Phase 6: AI Usage Governance

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

## Phase 7: Official A2A SDK Integration and Governance

**Priority:** P1
**Difficulty:** Medium to high
**Dependencies:** Phase 4 framework compatibility, Phase 5 persistence, and Phase 6 usage governance
**Initial scope:** Official `a2a-sdk` implementation only
**Goal:** Extend observability and governance from MCP and framework-local calls to agent-to-agent communication through the official A2A Python SDK.

### Scope decision

The first A2A integration will target only the official `a2a-sdk` implementation
maintained by the A2A project. Alternative implementations such as `fastA2A`
are explicitly out of scope for the first release of this phase.

This limits the initial compatibility matrix and avoids maintaining multiple
implementations with potentially different lifecycle semantics. The internal
event and context contracts should remain sufficiently protocol-oriented that a
second implementation can be added later without changing the registry,
exporters, governance model, or public event semantics.

The project should distinguish:

- **A2A protocol model:** stable AIMonitor concepts for agent communication;
- **`a2a-sdk` adapter:** version-specific translation from the official SDK;
- **A2A governance:** policy, budget, trust, privacy, and delegation controls.

The initial adapter must use documented public SDK APIs. It must not depend on
private classes, monkey-patching, or assumptions about a specific web server
framework.

### Integration difficulty

| Area | Difficulty | Main concerns |
| --- | --- | --- |
| Outbound A2A client instrumentation | Medium | Request lifecycle, task correlation, remote errors, retries, and streaming |
| Inbound A2A server instrumentation | Medium to high | Middleware or handler hooks, task state transitions, cancellations, and response preservation |
| Streaming and partial results | High | Multiple updates per task, ordering, incomplete streams, and duplicate completion events |
| Distributed context propagation | Medium to high | Trace, task, context, and message identifiers across agent boundaries |
| Privacy and payload controls | Medium | Prompts, messages, artifacts, personal data, and cross-agent trust boundaries |
| SDK version compatibility | Medium to high | Protocol evolution and changes to public SDK lifecycle hooks |
| Conformance testing | Medium | In-memory transport, client/server pairs, failures, and version matrix |

### A2A event and context model

- Define an A2A-specific event model rather than forcing agent communication
  into `MCPEvent`.
- Capture, when available:
  - source agent identity and role;
  - target or remote agent identity;
  - `task_id`;
  - `context_id`;
  - `message_id`;
  - agent card or capability reference;
  - protocol version;
  - transport;
  - operation;
  - task status;
  - duration;
  - error and cancellation information;
  - artifact metadata;
  - usage and cost references.
- Define operations such as:
  - `a2a.request`;
  - `a2a.task`;
  - `a2a.message`;
  - `a2a.artifact`;
  - `a2a.status`;
  - `a2a.delegation`.
- Preserve the relationships between a workflow, request, task, message,
  status update, and artifact.
- Keep `MCPEvent`, generic framework run events, and A2A events distinguishable
  while allowing them to share trace and agent metadata.
- Add context propagation for:
  - `trace_id`;
  - `run_id`;
  - `task_id`;
  - `context_id`;
  - `message_id`;
  - tenant or policy identifiers;
  - budget and governance identifiers.
- Preserve identifiers supplied by the official SDK instead of replacing them
  with new local identifiers.
- Use standard distributed tracing context where the protocol and transport
  allow it. Correlate locally without exposing payloads when remote propagation
  is unavailable.

### Phase 7.1: Define the official SDK boundary

- Record the first supported `a2a-sdk` package and protocol versions.
- Decide which transports are in the first conformance target.
- Identify the official public client, server, middleware, callback, and task
  lifecycle APIs.
- Define the supported client and server integration surfaces independently.
- Add a capability matrix for:
  - task lifecycle visibility;
  - streaming;
  - cancellation;
  - artifacts;
  - usage metadata;
  - distributed context propagation.
- Fail clearly when an installed SDK version is outside the tested range.
- Keep the optional dependency isolated from the core installation.

### Phase 7.2: Implement the A2A client adapter

- Add an optional `aimonitor.integrations.a2a_sdk` module.
- Instrument outbound requests without changing client return types.
- Record:
  - request start;
  - target agent;
  - task creation;
  - status updates;
  - messages;
  - artifacts;
  - successful completion;
  - remote errors;
  - cancellation;
  - timeout;
  - retries.
- Correlate all updates with the SDK-provided task and context identifiers.
- Preserve the original SDK exception and response object.
- Record retries as child operations or explicit retry metadata rather than
  creating ambiguous duplicate tasks.

### Phase 7.3: Implement the A2A server adapter

- Instrument inbound requests through documented server or middleware hooks.
- Record source agent, task, context, message, and protocol metadata.
- Observe task state transitions without changing the server's state machine.
- Preserve typed responses, streaming behavior, cancellations, and exceptions.
- Record generated artifacts as metadata by default; capture full content only
  when explicitly enabled.
- Avoid duplicating events when an application also instruments its HTTP layer.
- Keep A2A instrumentation separate from FastMCP middleware even when both run
  on the same host.

### Phase 7.4: Streaming, delegation, and failure semantics

- Model a streamed task as one correlated task with ordered status, message,
  and artifact updates.
- Emit exactly one terminal outcome for completed, failed, cancelled, and
  timed-out tasks.
- Make partial stream loss visible without incorrectly marking the task as
  successfully completed.
- Record delegation chains and preserve parent-child relationships across
  multiple agents.
- Distinguish:
  - local request failure;
  - remote agent failure;
  - protocol validation failure;
  - transport failure;
  - timeout;
  - cancellation;
  - policy rejection.
- Ensure monitoring failures never change the A2A application result.

### Phase 7.5: Privacy, trust, and governance

- Do not capture complete A2A messages or artifacts by default.
- Capture identifiers, statuses, timing, sizes, and safe metadata by default.
- Add explicit controls for:
  - A2A message input;
  - A2A message output;
  - artifact content;
  - tool arguments;
  - usage metadata;
  - maximum payload size.
- Apply configured sensitive-field redaction before events enter the registry.
- Support hashes or references for payloads that cannot cross agent boundaries.
- Add governance controls for:
  - allowed source and target agents;
  - trust boundaries;
  - delegation depth;
  - allowed capabilities;
  - data classification;
  - tenant and budget context;
  - cross-agent payload policy.
- Correlate token and cost usage by agent, task, delegation chain, and workflow
  when Phase 6 data is available.

### Phase 7.6: Testing and compatibility maintenance

- Build a fake in-memory A2A transport before relying on an external service.
- Test client and server adapters together in the same process.
- Test:
  - successful request and task completion;
  - remote errors;
  - local errors;
  - validation failures;
  - retries;
  - cancellation;
  - timeout;
  - streaming;
  - partial stream failure;
  - artifacts;
  - delegation;
  - sensitive payload redaction;
  - trace and task correlation;
  - duplicate instrumentation.
- Run the adapter against the minimum and maximum supported `a2a-sdk` versions.
- Add a scheduled compatibility check for newer SDK versions.
- Keep protocol conformance tests separate from framework-specific adapter tests.

### Optional packaging

- Add an independent package extra for the official SDK, for example:
  `ai-monitor-sdk[a2a]`.
- Keep `import aimonitor` free from A2A imports.
- Do not add `fastA2A` as a transitive or development dependency for the first
  implementation.
- Document that alternative A2A implementations are unsupported initially.
- Add a future compatibility decision point rather than promising support.

### Exit criteria

- The core package works without `a2a-sdk` installed.
- The official SDK client and server paths can be instrumented independently.
- A2A events have stable task, context, message, agent, and trace relationships.
- Streaming produces ordered updates and exactly one terminal outcome.
- Client and server responses, exceptions, cancellation, and return types are
  preserved.
- Governance can observe and enforce agent-boundary policies without requiring
  full message or artifact storage.
- Payload redaction and capture limits are tested.
- The adapter is tested against the supported SDK version range.
- `fastA2A` remains explicitly out of scope unless a later adoption decision
  justifies a second adapter.

## Phase 8: Operational Observability

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

## Phase 9: Performance and Reliability

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

## Phase 10: Release Readiness

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
7. Should exporter lifecycle events and registry snapshot updates be owned by `BaseExporter`, the registry, or a callback/hook when `close()` is invoked directly?
8. What lifecycle reporting responsibilities and supported hooks should the custom-exporter guide require from third-party implementations?
9. Which configuration aliases remain supported during development, and when can they be removed?
10. Which optional integrations are release-blocking and which are best-effort extras?
11. Which model providers and pricing sources are supported for the first governance release?
12. Should governance enforcement be implemented in the SDK, delegated to the host application, or both?
13. Which exact `a2a-sdk` and A2A protocol versions should be the first
    conformance target?
14. Which official `a2a-sdk` transports and public lifecycle hooks should be
    supported first?
15. Which payload fields are allowed to cross agent boundaries by default?
16. Should A2A streaming be represented as one task with updates, or should
    selected updates also be materialized as independent events?
17. When should an alternative implementation such as `fastA2A` justify a
    second adapter and a separate compatibility matrix?

## Recommended Next Sequence

1. Complete any remaining Kafka delivery and lifecycle gaps, including broker failure and recovery behavior.
2. Build the exporter matrix for the existing set: Kafka, Prometheus, OpenTelemetry, Webhook/HTTP, File, SQLite, and Console.
3. Add reusable contract tests and identify the first concrete reliability gap in each exporter.
4. Fix and validate built-in exporters one at a time, including their configuration, failure, and cleanup paths.
5. Establish a clean CI test matrix with explicit external-service fixtures.
6. Complete configuration precedence and validation tests that affect exporter setup.
7. Define the framework-neutral run, context, and payload-capture contracts.
8. Implement the FastMCP and LangChain adapters, then the smolagents
   OpenTelemetry path.
9. Implement the official `a2a-sdk` event, client, server, and context
   integration contracts.
10. Implement MongoDB and PostgreSQL persistence exporters.
11. Define AI usage, cost, budget, and privacy governance.
12. Add A2A boundary governance and compatibility-matrix tests.
13. Add registry runtime metrics and snapshot staleness.
14. Run sustained-load and failure-recovery tests.
15. Update release documentation and package metadata.
