"""
Exporters are responsible for taking the data from the database and converting it into a format that can be used by other systems. 
This module provides a base class for all exporters, which can be extended to create custom exporters for different formats.
"""
from collections.abc import Sequence
from abc import ABC, abstractmethod
from typing import Callable, Optional, ParamSpec, TypeVar, cast, overload
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
import httpx
from pathlib import Path

from aimonitor.core.event import BaseSignal, SignalType
from aimonitor.configs.config import get_settings

settings = get_settings()


class BaseExporter(ABC):
    """
    Base class for all exporters. This class defines the interface that all exporters must implement.
    """
    SUPPORTED_SIGNALS: set[SignalType] = {SignalType.EVENT, SignalType.METRIC, SignalType.LOG, SignalType.SPAN, SignalType._INNER}  # logs everything

    async def export(self, event: BaseSignal) -> None:
        """
        Export the given event to the desired format.

        :param event: The event to be exported.
        """
        await self.export_batch(event_batch=[event])

    @abstractmethod
    async def export_batch(self, event_batch: Sequence[BaseSignal]) -> None:
        """
        Export the given batch of events to the desired format.

        :param event_batch: The batch of events to be exported 
        """
        pass

    async def connect(self) -> None:
        """Optional lifecycle hook for exporters that require initialization."""
        return None

    async def close(self) -> None:
        """Optional lifecycle hook for exporters that require cleanup."""
        return None

    @abstractmethod    
    async def healthcheck(self) -> bool:
        """Mandatory method to check the health of the exporter. 
        Must be always implemented.
    The healthcheck should emit a boolean value indicating the health of the exporter.
        """
        pass

    @abstractmethod
    async def describe(self) -> dict[str, object]:
        """Return diagnostic details for the exporter.

        The returned data is informational only. Health state is owned by the
        registry snapshot and must be determined by ``healthcheck()``.
        Example:
        {
            "status": "healthy",
            "message": "Exporter is connected to the destination.",
            "timestamp": "2023-01-01T12:00:00Z"
        }
        Exporters may add backend-specific diagnostic fields.
        """
        pass

    @abstractmethod
    async def recover(self) -> bool:
        """Mandatory method to attempt recovery of the exporter. Must be always implemented.
        Should return True if the recovery was successful, False otherwise.
        """
        pass


class HTTPBaseExporter(BaseExporter):
    """
    Base class for http exporters, uses httpx
    """

    def __init__(
        self, 
        url: str, 
        auth: Optional[tuple | httpx.Auth] = None, 
        headers: Optional[dict] = None
    ):
        self.url = url
        self.headers = headers or {}
        self.auth = auth
        self.client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        self.client = httpx.AsyncClient(
            auth=self.auth,
            headers=self.headers,
            base_url=self.url,
            timeout=1.0
        )
    
    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def export(self, event: BaseSignal) -> None:
        """
        Abstract method of exportation
        """
        await self.export_batch(event_batch=[event])

    @abstractmethod
    async def export_batch(self, event_batch: Sequence[BaseSignal]) -> None:
        """
        Export in batches
        """
        pass

class BaseDatabaseExporter(BaseExporter):

    def __init__(self, dsn: str | Path):
        super().__init__()
        self.dsn = dsn

    @abstractmethod
    async def _create_table_if_not_exists(self) -> None:
        pass

    @abstractmethod
    async def _open_connection(self) -> None:
        pass

    async def connect(self) -> None:
        await self._open_connection()
        await self._create_table_if_not_exists()
    
    @abstractmethod
    async def close(self) -> None:
        pass


P = ParamSpec("P")
R = TypeVar("R")


@overload
def with_retry() -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...


@overload
def with_retry(func: Callable[P, R]) -> Callable[P, R]:
    ...


def with_retry(func: Optional[Callable[P, R]] = None) -> Callable[..., object]:
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        retried = retry(
            stop=stop_after_attempt(settings.retries_policy if settings.retries_policy is not None else 1),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            wait=wait_exponential(),
            reraise=True,
        )(fn)
        return cast(Callable[P, R], retried)

    if func is None:
        return decorator
    return decorator(func)