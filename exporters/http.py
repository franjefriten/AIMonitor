from exporters.base import BaseExporter
from core.event import MCPEvent
from utils.logger import logger
import httpx
import asyncio
from exporters.base import with_retry


class HTTPExporter(BaseExporter):
    """
    Exporter for HTTP, used to send events to an HTTP endpoint.
    """
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    @with_retry()
    async def export(self, event: MCPEvent):
        with httpx.AsyncClient() as client:
            try:
                response = await client.post(utl=self.endpoint, json=event.model_dump_json())
            except httpx.RequestError as e:
                logger.error(f"An error occurred while sending the event to {self.endpoint}: {e}")
                raise e
            
    async def export_batch(self, event_batch):
        return await super().export_batch(event_batch)
        
