"""
Exporters are responsible for taking the data from the database and converting it into a format that can be used by other systems. 
This module provides a base class for all exporters, which can be extended to create custom exporters for different formats.
"""
from abc import ABC, abstractmethod
from core.event import MCPEvent
from typing import Callable, List, Optional
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import httpx

class BaseExporter(ABC):
    """
    Base class for all exporters. This class defines the interface that all exporters must implement.
    """

    @abstractmethod
    async def export(self, event: MCPEvent) -> None:
        """
        Export the given event to the desired format.

        :param event: The event to be exported.
        """
        pass

    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        """
        Export the given batch of events to the desired format.

        :param event_batch: The batch of events to be exported 
        """
        for event in event_batch:
            await self.export(event)


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

    @abstractmethod
    async def export(self, event: MCPEvent):
        """
        Abstract method of exportation
        """
        pass
    
    async def export_batch(self, event_batch: List[MCPEvent]):
        """
        Export in batches
        """
        for event in event_batch:
            await self.export(event)


def with_retry(func: Callable):
    return retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception((ConnectionError, TimeoutError)),
        wait=wait_exponential(),
        reraise=True
    )(func)