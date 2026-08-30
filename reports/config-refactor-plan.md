# Config refactor plan

## Objective
Improve the module configuration model so it is easier to validate, document, extend, and maintain without coupling configuration parsing to runtime exporter wiring.

## Current issue
The current settings model in `configs/config.py` is a flat configuration object with many fields and alias variants. This makes the config surface difficult to reason about as the module grows and makes it harder to preserve a clear separation between:
- pure configuration state
- runtime bootstrap logic
- exporter lifecycle and health checks
- optional dependency initialization

## Target design
Split the config into logical sections instead of keeping everything at the top level.

### Recommended structure
- `AppSettings`
  - environment
  - logger level
  - general module behavior
- `TelemetrySettings`
  - `enabled`
  - `healthcheck_enabled`
  - `healthcheck_interval`
- `KafkaProducerSettings`
  - `acks`
  - `batch_size`
  - `max_workers`
  - other producer tuning values
- `ExporterSettings`
  - Redis / SQLite / Prometheus / File / Kafka / OTel details
- `AIMonitorSettings`
  - top-level aggregator that keeps the public API stable

## Key principles
1. Configuration should describe state, not instantiate exporters.
2. Bootstrap should decide which exporters to create from config.
3. Optional dependencies should be lazy-loaded and fail safely.
4. Aliases should remain minimal and canonical names should be clear.
5. Validation should be strict but safe for optional integrations.

## Refactor steps
1. Create nested config models for app, telemetry, and export-related sections.
2. Keep `AIMonitorSettings` as the external facade but compose the nested models internally.
3. Preserve compatibility with current YAML/env keys while reducing alias sprawl.
4. Move runtime exporter construction to `bootstrap.py`.
5. Ensure `ExporterRegistry` and telemetry logic read from config without mutating it.
6. Add/keep regression tests for YAML parsing, env parsing, and healthcheck settings.

## Why this is valuable
This reduces config drift, makes the API easier to extend for Kafka and other exporters, and keeps runtime behavior predictable. It also makes the project easier to maintain as new integrations are added.

## Expected outcome
A more maintainable config layer with:
- cleaner validation
- explicit runtime separation
- easier extension for future exporters
- less risk of hidden state mutation during startup
