"""
Exporters are responsible for taking the data from the database and converting it into a format that can be used by other systems. 
This module provides a base class for all exporters, which can be extended to create custom exporters for different formats.
"""
from abc import ABC, abstractmethod
from core.event import BaseSignal, SignalType
from typing import Callable, List, Optional
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import httpx
from pathlib import Path
from configs.config import get_settings


settings = get_settings()


class BaseExporter(ABC):
    """
    Base class for all exporters. This class defines the interface that all exporters must implement.
    """
    SUPPORTED_SIGNALS: set[SignalType] = {SignalType.EVENT, SignalType.METRIC, SignalType.LOG, SignalType.SPAN}

    @abstractmethod
    async def export(self, event: BaseSignal) -> None:
        """
        Export the given event to the desired format.

        :param event: The event to be exported.
        """
        await self.export_batch(event_batch=[event])

    async def export_batch(self, event_batch: List[BaseSignal]) -> None:
        """
        Export the given batch of events to the desired format.

        :param event_batch: The batch of events to be exported 
        """
        for event in event_batch:
            await self.export(event)

    async def connect(self) -> None:
        """Optional lifecycle hook for exporters that require initialization."""
        return None

    async def close(self) -> None:
        """Optional lifecycle hook for exporters that require cleanup."""
        return None


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

    async def connect(self):
        self.client = httpx.AsyncClient(
            auth=self.auth,
            headers=self.headers,
            base_url=self.url,
            timeout=1.0
        )
    
    async def close(self):
        if self.client:
            self.client.aclose()
            self.client = None

    async def export(self, event: BaseSignal) -> None:
        """
        Abstract method of exportation
        """
        await self.export_batch(event_batch=[event])

    @abstractmethod
    async def export_batch(self, event_batch: List[BaseSignal]):
        """
        Export in batches
        """
        pass

class BaseDatabaseExporter(BaseExporter):

    def __init__(self, dsn: str | Path):
        super().__init__()
        self.dsn = dsn

    @abstractmethod
    async def _create_table_if_not_exists():
        pass

    @abstractmethod
    async def _open_connection():
        pass

    async def connect(self):
        await self._open_connection()
        await self._create_table_if_not_exists()
    
    @abstractmethod
    async def close():
        pass


def with_retry(func: Callable):
    return retry(
        stop=stop_after_attempt(settings.retries_policy),
        retry=retry_if_exception((ConnectionError, TimeoutError)),
        wait=wait_exponential(),
        reraise=True
    )(func)