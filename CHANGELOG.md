# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Automatic worker startup in `ExporterRegistry` when dispatching events.
- Support for both synchronous and asynchronous functions in the `monitor_tool` decorator.
- Default `ConsoleExporter` registered in the global registry.
- Retry mechanism for exporters, including HTTP and Redis exporter support.
- Asynchronous event dispatching through queueing in `ExporterRegistry`.
- Basic unit tests for registry and tool monitoring workflows.

### Fixed
- Ensure worker tasks start before queueing export events.
- Correct exporter method invocation and support async export implementations.
- Make `ExporterRegistry.shutdown()` asynchronous and cancel worker tasks cleanly.
- Fix registry shutdown so queued events complete before exit.
- Correct issues in MCPEvent schema validation and improve event logging.
- Fix incorrect imports in exporter modules.

### Changed
- Improved event logging and error handling in tool monitoring.
- Enhanced HTTP and Redis exporters with retry behavior.
- Added basic configuration, security barrier, and logging setup.
