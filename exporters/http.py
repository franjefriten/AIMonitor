from exporters.base import BaseExporter, HTTPBaseExporter
from core.event import BaseSignal, SignalType
from utils.logger import logger
import httpx
import asyncio
from exporters.base import with_retry
from typing import List


class WebhookExporter(HTTPBaseExporter):
    """
    Exporter for HTTP, used to send events to an HTTP endpoint.
    """

    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG, SignalType.METRIC}
    
    def __init__(self, url, headers=None, auth=None):
        super().__init__(url=url, headers=headers, auth=auth)

    async def export(self, event: BaseSignal) -> None:
        await self.export_batch([event])
            
    @with_retry
    async def export_batch(self, event_batch: List[BaseSignal]) -> None:
        if not self.client:
            raise RuntimeError("Exporter not connected. Call connect() before exporting.")
        payload = []
        for event in event_batch:
            if event.event_type not in self.SUPPORTED_SIGNALS:
                logger.warning(
                    "Event type '%s' with id: '%s' is not supported by WebhookExporter. Skipping export for event.",
                    event.event_type,
                    event.id
                )
            else:
                payload.append(event.model_dump())
        
        response = await self.client.post(
            self.url, 
            json=payload,
            timeout=10.0
        )
        response.raise_for_status()
            
    
        
