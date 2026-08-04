try:
    import opentelemetry as optl
    import opentelemetry.sdk as optl_sdk
except ImportError as e:
    raise ImportError(
        "opentelemetry is required for OpenTelemetryExporter. Install it with pip install .[opentelemetry]"
    ) from e


import sys
import logging
from typing import Optional, Dict, Any
from utils.logger import logger
from configs.config import get_settings

settings = get_settings()

class InternalTelemetryManager:
    """
    Internal telemetry manager for the SDK.
    - Automatically detects if OpenTelemetry is available in the environment.
    - If not installed, acts in No-Op mode (zero cost, no errors).
    - Protects the client's application against any internal observability failures.
    """
    def __init__(self, enabled: bool = settings.inner_telemetry, service_name: str = "tu-sdk-observabilidad"):

        if getattr(self, "_initialized", False):
            return  # Avoid re-initialization

        self.enabled = enabled
        self.service_name = service_name
        self.tracer = None
        self.meter = None
        
        if self.enabled:
            self._initialize_otel()
        self._initialized = True
    
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(InternalTelemetryManager, cls).__new__(cls)
            cls.instance._initialized = False
        return cls.instance

    def _initialize_otel(self) -> None:
        """Checks and loads OpenTelemetry dynamically and securely."""
        try:
            from opentelemetry import trace, metrics
            
            # Get the OpenTelemetry providers configured in the client app
            self.tracer = trace.get_tracer(self.service_name)
            self.meter = metrics.get_meter(self.service_name)
            
            logger.debug("OpenTelemetry detected and successfully initialized in the SDK.")

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
                        # OTel expects primitive types (str, int, float, bool)
                        span.set_attribute(str(key), value)
        except Exception as internal_error:
            # Absolute safety net: an internal telemetry failure never breaks the user's software
            sys.stderr.write(f"[SDK Telemetry Error] Failed to record event '{event_name}': {internal_error}\n")

    def track_metric_counter(self, metric_name: str, value: int = 1, attributes: Optional[Dict[str, str]] = None) -> None:
        """
        Example for recording internal metrics (counters) optionally.
        """
        if not self.enabled or not self.meter:
            return

        try:
            # Creates or reuses a basic OTel counter
            counter = self.meter.create_counter(metric_name)
            counter.add(value, attributes or {})
        except Exception as internal_error:
            sys.stderr.write(f"[SDK Telemetry Error] Failed to record metric '{metric_name}': {internal_error}\n")


internal_telemetry_manager = InternalTelemetryManager()