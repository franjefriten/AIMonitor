from exporters.base import BaseExporter, HTTPBaseExporter
from core.event import MCPEvent
from utils.logger import logger
import httpx
import asyncio
from exporters.base import with_retry
from typing import List


class WebhookExporter(HTTPBaseExporter):
    """
    Exporter for HTTP, used to send events to an HTTP endpoint.
    """
    def __init__(self, url, headers=None, auth=None):
        super().__init__(url=url, headers=headers, auth=auth)

    async def export(self, event: MCPEvent) -> None:
        await self.export_batch([event])
            
    @with_retry
    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        if not self.client:
            raise RuntimeError("Exporter not connected. Call connect() before exporting.")
            
        payload = [e.model_dump() for e in event_batch]
        
        response = await self.client.post(
            self.url, 
            json=payload,
            timeout=10.0
        )
        response.raise_for_status()
            
    
        
