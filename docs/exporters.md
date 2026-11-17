# Built-in exporters

AIMonitor exporters receive signals from the shared `ExporterRegistry`. The registry fans each batch out to its registered exporters; each exporter decides which signal types it supports and how to deliver them. An exporter that does not support a signal should skip it rather than reinterpret its payload.

The built-in exporters have different purposes and delivery models:

| Exporter | Intended use | Signals and output | Important behavior |
| --- | --- | --- | --- |
| `ConsoleExporter` | Local development and debugging | Events, logs, metrics, spans, and internal signals as readable Python-model representations | Writes synchronously to a text stream; not durable storage. |
| `FileExporter` | Local capture and inspection | Events, logs, metrics, and spans as JSON Lines | Creates dated files and rotates them by size. |
| `SQLiteExporter` | Local persistence and querying | Events, logs, metrics, and spans in separate SQLite tables | Uses an async SQLite connection and commits each exported batch. Call `connect()` before exporting. |
| `WebhookExporter` | Forwarding signals to an application or collector | Events, logs, metrics, and spans as a JSON batch over HTTP | Requires an endpoint and `connect()`; HTTP status failures are raised to the registry. |
| `PrometheusExporter` | Scrape-based numeric monitoring | `MetricEvent` only, exposed from an HTTP `/metrics` endpoint | It does not store raw events or logs. Counters increment, gauges set the current value, and histograms observe samples. |
| `OpenTelemetryExporter` | Exporting tool executions as traces | `MCPEvent` values as OpenTelemetry spans | Separate from AIMonitor's internal SDK telemetry; requires the optional OpenTelemetry dependencies and an installed SDK/export pipeline to deliver spans externally. |
| `KafkaExporter` | Asynchronous event streaming to Kafka | Configured signal types as serialized event messages | Requires a running broker and an explicit topic mapping for the signal types being published. |

## Choosing an exporter

- Use **Console** to see what the SDK emits while developing.
- Use **File** for simple append-only local capture and **SQLite** when local queries or structured persistence are useful.
- Use **Webhook** to hand full signal payloads to a service that owns downstream processing.
- Use **Prometheus** for numerical, scrape-based metrics. Emit `MetricEvent` signals for the measurements that should appear in Prometheus. For example, `monitor_tool` emits an `MCPEvent` describing a tool execution and separate `MetricEvent` values for execution count and duration. Prometheus consumes the metrics, not the detailed event, so it does not duplicate or expose arguments, results, errors, logs, or trace identifiers.
- Use **OpenTelemetry** when tool executions should be represented as spans and sent through an OpenTelemetry pipeline.
- Use **Kafka** when signals need to be streamed to consumers asynchronously.

These exporters are not interchangeable. In particular, Prometheus is an aggregation/metrics endpoint, while File, SQLite, Webhook, and Kafka can preserve full signal payloads.

## Lifecycle

Exporters that own resources must be connected before exporting and closed when no longer needed. When registered, the `ExporterRegistry` owns health tracking and its shutdown process closes registered exporters. Export methods should surface delivery failures so the registry can record them; `describe()` is diagnostic and does not replace `healthcheck()`.

## Configuration and examples

Exporter settings and YAML examples are documented in [configuration.md](./configuration.md). Basic construction examples are in [usage.md](./usage.md); architectural boundaries, including the separation of internal telemetry from user-facing export, are in [architecture.md](./architecture.md).
