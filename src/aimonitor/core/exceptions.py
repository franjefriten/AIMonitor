"""
Core exceptions for the AIMonitor application.
"""

# Base exception for the AIMonitor application.
class AIMonitorError(Exception):
    """
    Base exception class for all AIMonitor-related errors. 
    Every exception should inherit from this class.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"AIMonitor error: {message}")

    def __repr__(self):
        return f"AIMonitorError(message={self.message})"

    def __str__(self):
        return f"AIMonitorError: {self.message}"

# Configs
class ConfigurationError(AIMonitorError):
    """
    Exception raised when configuration is invalid or internally inconsistent.
    This exception should be raised whenever there is an issue with the application's configuration, 
    such as missing or invalid configuration values.

    Examples:
        - an enabled exporter has no usable destination;
        - a timeout is negative;
        - mutually incompatible settings are selected.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Configuration error: {message}")

    def __repr__(self):
        return f"ConfigurationError(message={self.message})"

    def __str__(self):
        return f"ConfigurationError: {self.message}"


class ExporterConfigurationError(AIMonitorError):
    """
    Exception raised for errors in the configuration of an exporter within the AIMonitor application.
    It should not be confused with a general `ConfigurationError`; it specifically pertains to exporter-related configuration issues.
    This exception should be raised whenever there is an issue with the exporter's configuration, 
    such as missing or invalid configuration values.
    
    Examples:
        - Kafka bootstrap servers are missing
        - An Unsupported producer settings is passed to the client
        - producer parameters cannot be accepted by the backend
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter configuration error: {message}")

    def __repr__(self):
        return f"ExporterConfigurationError(message={self.message})"

    def __str__(self):
        return f"ExporterConfigurationError: {self.message}"


class OptionalDependencyMissingError(AIMonitorError, ImportError):
    """
    Exception raised when an optional dependency required by the AIMonitor application is missing.
    This exception should be raised whenever an optional package or module is not installed but is needed for certain functionality.
    """
    def __init__(self, dependency_name: str):
        self.dependency_name = dependency_name
        super().__init__(f"Optional dependency missing: {dependency_name}")

    def __repr__(self):
        return f"OptionalDepencyMissingError(dependency_name={self.dependency_name})"

    def __str__(self):
        return f"OptionalDepencyMissingError: {self.dependency_name}"

# Signals
class SignalTypeNotFound(AIMonitorError, ValueError):
    """
    Exception raised when a specified signal type is not found within the AIMonitor application.
    This exception should be raised whenever an invalid or unrecognized signal type is encountered.
    Signal types are located in the aimonitor.core.event module, SignalType class.
    """
    def __init__(self, signal_type: str):
        self.signal_type = signal_type
        super().__init__(f"Signal type not found: {signal_type}")

    def __repr__(self):
        return f"SignalTypeNotFound(signal_type={self.signal_type})"

    def __str__(self):
        return f"SignalTypeNotFound: {self.signal_type}"


class UnsupportedSignalError(AIMonitorError):
    """
    Exception raised when the signal type is valid AIMonitor input but a particular exporter does not support it.
    This is distinct from `SignalTypeNotFound`. For example, an internal signal may be valid within the SDK but intentionally excluded from a public Kafka topic.
    """
    def __init__(self, signal_type: str, exporter_name: str):
        self.signal_type = signal_type
        self.exporter_name = exporter_name
        super().__init__(f"Unsupported signal error: {signal_type} for exporter: {exporter_name}")

    def __repr__(self):
        return f"UnsuportedSignalError(signal_type={self.signal_type}, exporter_name={self.exporter_name})"

    def __str__(self):
        return f"UnsuportedSignalError: {self.signal_type} for exporter: {self.exporter_name}"


# Exporters
class ExporterError(AIMonitorError):
    """
    Base exception for errors related to exporters in the AIMonitor application.
    Not to be confused with `ExporterConfigurationError`, which is meant specifically for configuration-related issues in exporters.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter error: {message}")

    def __repr__(self):
        return f"ExporterError(message={self.message})"

    def __str__(self):
        return f"ExporterError: {self.message}"


class ExporterDeliveryError(ExporterError):
    """
    Exception raised when an exporter cannot confirm delivery of an event or batch.
    This exception means the exporter operation did not complete successfully. 
    It should not be converted into a successful result merely because the message was accepted into a local producer buffer.
    
    Example usage:
    ```python
    try:
        await delivery_future
    except Exception as backend_error:
        raise ExporterDeliveryError(
            f"Kafka delivery failed for event {event.id}"
        ) from backend_error
    ```
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter delivery error: {message}")

    def __repr__(self):
        return f"ExporterDeliveryError(message={self.message})"

    def __str__(self):
        return f"ExporterDeliveryError: {self.message}"


class ExporterNotReadyError(ExporterError):
    """
    Exception raised when an exporter operation is explicitly attempted while the exporter is unavailable for use.
    
    Examples:
       - export is valled after shutdown
       - the producer is in a a terminal closed state
       - the exporter is in a terminal closed state
    
    `healthcheck` method may not need to raise this exception, since a unavailable 
    exporter may return False so the `ExporterRegistry` can record said exporter as down in the health snapshot
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter not ready error: {message}")

    def __repr__(self):
        return f"ExporterNotReadyError(message={self.message})"

    def __str__(self):
        return f"ExporterNotReadyError: {self.message}"


class ExporterHealthcheckError(ExporterError):
    """
    Exception raised when an exporter fails its healthcheck.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter healthcheck error: {message}")

    def __repr__(self):
        return f"ExporterHealthcheckError(message={self.message})"

    def __str__(self):
        return f"ExporterHealthcheckError: {self.message}"
    

class ExporterRecoveryError(ExporterError):
    """
    Exception raised when an exporter encounters an error during recovery. Represents a failed attempt to reconstruct or reconnect an exporter.
    `recover` method contract returns bool, so this exception may be used to indicate an error within the recovery process.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter recovery error: {message}")

    def __repr__(self):
        return f"ExporterRecoveryError(message={self.message})"

    def __str__(self):
        return f"ExporterRecoveryError: {self.message}"


class ExporterClosedError(ExporterError):
    """
    Exception raised when an operation is attempted on an exporter that has been closed.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Exporter closed error: {message}")

    def __repr__(self):
        return f"ExporterClosedError(message={self.message})"

    def __str__(self):
        return f"ExporterClosedError: {self.message}"

## LEGACY ERRORS TO BE DELETED

class BatchExportError(AIMonitorError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Batch export error: {message}")

    def __repr__(self):
        return f"BatchExportError(message={self.message})"

    def __str__(self):
        return f"BatchExportError: {self.message}"

class KafkaProducerNotInitializedError(AIMonitorError):
    def __init__(self, message: str = "Kafka producer is not initialized"):
        self.message = message
        super().__init__(f"Kafka producer not initialized error: {message}")

    def __repr__(self):
        return f"KafkaProducerNotInitializedError(message={self.message})"

    def __str__(self):
        return f"KafkaProducerNotInitializedError: {self.message}"