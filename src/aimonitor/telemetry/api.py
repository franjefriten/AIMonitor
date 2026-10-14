import sys
import os
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Optional, Dict, Any
from aimonitor.utils.logger import logger
from aimonitor.configs.config import get_settings
from aimonitor.core.event import HealthCheckSnapshot as HealthCheckEvent


class TelemetryProducer:
    """
    Internal telemetry manager for the SDK.
    - Automatically detects if OpenTelemetry is available in the environment.
    - If not installed, acts in No-Op mode (zero cost, no errors).
    - Protects the client's application against any internal observability failures.
    """
    def __init__(
        self,
        enabled: Optional[bool] = None,
        service_name: str = "aimonitor-sdk",
    ):
        settings = get_settings()
        self.enabled = settings.telemetry.inner_telemetry if enabled is None else enabled
        self.service_name = service_name
        self.tracer = None
        self.meter = None
        self._counters: Dict[str, Any] = {}
        
        if self.enabled:
            self._initialize_otel()

    def configure(self, enabled: Optional[bool] = None, service_name: Optional[str] = None) -> None:
        """
        Configures telemetry at runtime.
        - enabled=None: read value from AIMonitor settings.
        - enabled=False: force no-op mode.
        - enabled=True: initialize OpenTelemetry if available.
        """
        settings = get_settings()
        desired_enabled = settings.telemetry.inner_telemetry if enabled is None else enabled

        if service_name:
            self.service_name = service_name

        self.enabled = bool(desired_enabled)
        self.tracer = None
        self.meter = None
        self._counters = {}

        if self.enabled:
            self._initialize_otel()

    def reset(self) -> None:
        """Reset internal telemetry to the current settings without replacing the manager."""
        self.configure()

    def _initialize_otel(self) -> None:
        """Checks and loads OpenTelemetry dynamically and securely."""
        try:
            if os.getenv("OTEL_SDK_DISABLED", "false").strip().lower() == "true":
                self.enabled = False
                logger.debug("OTEL_SDK_DISABLED=true detected. Internal telemetry disabled (No-Op).")
                return

            from opentelemetry import trace, metrics
            
            # Get the OpenTelemetry providers configured in the client app
            self.tracer = trace.get_tracer(self.service_name)
            self.meter = metrics.get_meter(self.service_name)
            
            logger.debug("OpenTelemetry detected and initialized in the SDK.")

        except ImportError:
            # OpenTelemetry is not installed in the user's environment -> Total skip
            self.enabled = False
            logger.debug("OpenTelemetry not found in the environment. Internal telemetry disabled (No-Op).")
        except Exception as e:
            # Any other unexpected startup failure must not crash the SDK
            self.enabled = False
            logger.warning("Unexpected error initializing OpenTelemetry in the SDK: %s", e)

    def record_event(self, event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """
        Record an internal SDK event as a trace span on a best-effort basis.

        Telemetry failures are isolated from the host application.
        """
        if not self.enabled or not self.tracer:
            return

        try:
            with self.tracer.start_as_current_span(event_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        # Keep attribute payloads safe and compatible with OTel primitive types.
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            span.set_attribute(str(key), value)
                        else:
                            span.set_attribute(str(key), str(value))
        except Exception as internal_error:
            # Absolute safety net: an internal telemetry failure never breaks the user's software
            sys.stderr.write(f"[SDK Telemetry Error] Failed to record event '{event_name}': {internal_error}\n")

    async def record_exporter_healthcheck(
        self,
        event: HealthCheckEvent,
        attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record one internal healthcheck result for a concrete exporter.

        This is internal SDK observability, not a business-export event.
        Health results must be emitted to the internal telemetry channel only.
        """
        if not self.enabled or not self.tracer:
            return

        payload = event.model_dump()
        if attributes:
            payload.update(attributes)

        try:
            with self.tracer.start_as_current_span("sdk.exporter.healthcheck") as span:
                for key, value in payload.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        span.set_attribute(str(key), value)
                    else:
                        span.set_attribute(str(key), str(value))
        except Exception as internal_error:
            sys.stderr.write(
                f"[SDK Telemetry Error] Failed to record exporter healthcheck '{event.exporter_name}': {internal_error}\n"
            )

    def record_metric(self, metric_name: str, value: int = 1, attributes: Optional[Dict[str, Any]] = None) -> None:
        """
        Record an internal counter metric on a best-effort basis.
        """
        if not self.enabled or not self.meter:
            return

        try:
            # Cache counters to avoid re-creating instrument handles on hot paths.
            counter = self._counters.get(metric_name)
            if counter is None:
                counter = self.meter.create_counter(metric_name)
                self._counters[metric_name] = counter
            counter.add(value, attributes or {})
        except Exception as internal_error:
            sys.stderr.write(f"[SDK Telemetry Error] Failed to record metric '{metric_name}': {internal_error}\n")


telemetry_producer = TelemetryProducer()


class TelemetryConsumer:
    """Read-only queries over local telemetry availability and SDK health."""

    def __init__(self, producer: TelemetryProducer):
        self._producer = producer
        self._process_started_at = datetime.now(UTC)
        self._process_started_monotonic = time.monotonic()

    def get_telemetry_status(self) -> Dict[str, Any]:
        """Return the local OpenTelemetry provider availability."""
        return {
            "enabled": self._producer.enabled,
            "service_name": self._producer.service_name,
            "tracer_available": self._producer.tracer is not None,
            "meter_available": self._producer.meter is not None,
        }

    async def get_process_liveness(self) -> Dict[str, Any]:
        """Return local process liveness without probing exporters or dependencies."""
        process_id = os.getpid()
        status = "alive" if process_id > 0 and not sys.is_finalizing() else "stopping"
        return {
            "status": status,
            "component": "aimonitor-sdk",
            "pid": process_id,
            "started_at": self._process_started_at.isoformat(),
            "uptime_seconds": max(0.0, time.monotonic() - self._process_started_monotonic),
        }

    async def get_sdk_readiness(self) -> Dict[str, Any]:
        """Return the registry-owned SDK health snapshot."""
        from aimonitor.core.registry import registry

        snapshot = await registry.health_snapshot()
        return snapshot.model_dump(mode="json")


telemetry_consumer = TelemetryConsumer(telemetry_producer)


def configure_internal_telemetry(enabled: Optional[bool] = None, service_name: Optional[str] = None) -> TelemetryProducer:
    """
    Public helper to configure SDK internal telemetry from user modules.

    Examples:
      - configure_internal_telemetry(enabled=False)
      - configure_internal_telemetry(enabled=True, service_name="my-service")
      - configure_internal_telemetry()  # uses AIMonitor settings
    """
    telemetry_producer.configure(enabled=enabled, service_name=service_name)
    return telemetry_producer


def get_telemetry_status() -> Dict[str, Any]:
    """Query local OpenTelemetry provider availability."""
    return telemetry_consumer.get_telemetry_status()


async def get_sdk_readiness() -> Dict[str, Any]:
    return await telemetry_consumer.get_sdk_readiness()


async def get_process_liveness() -> Dict[str, Any]:
    """Query process liveness without probing exporters or dependencies."""
    return await telemetry_consumer.get_process_liveness()