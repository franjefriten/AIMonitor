import sys
import os
from typing import Optional, Dict, Any
from utils.logger import logger
from configs.config import get_settings

class InternalTelemetryManager:
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
        self.enabled = settings.inner_telemetry if enabled is None else enabled
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
        desired_enabled = settings.inner_telemetry if enabled is None else enabled

        if service_name:
            self.service_name = service_name

        self.enabled = bool(desired_enabled)
        self.tracer = None
        self.meter = None
        self._counters = {}

        if self.enabled:
            self._initialize_otel()

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

    def track_event(self, event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """
        Safely records an event or trace.
        If telemetry is disabled or fails, the SDK execution continues normally.
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

    def track_metric_counter(self, metric_name: str, value: int = 1, attributes: Optional[Dict[str, Any]] = None) -> None:
        """
        Example for recording internal metrics (counters) optionally.
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


internal_telemetry_manager = InternalTelemetryManager()


def configure_internal_telemetry(enabled: Optional[bool] = None, service_name: Optional[str] = None) -> InternalTelemetryManager:
    """
    Public helper to configure SDK internal telemetry from user modules.

    Examples:
      - configure_internal_telemetry(enabled=False)
      - configure_internal_telemetry(enabled=True, service_name="my-service")
      - configure_internal_telemetry()  # uses AIMonitor settings
    """
    internal_telemetry_manager.configure(enabled=enabled, service_name=service_name)
    return internal_telemetry_manager