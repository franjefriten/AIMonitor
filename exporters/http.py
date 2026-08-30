from exporters.base import BaseExporter, HTTPBaseExporter
from core.event import BaseSignal, SignalType, HealthCheckEvent, HealthStatus
from utils.logger import logger
import httpx
import asyncio
from exporters.base import with_retry
from typing import List


class WebhookExporter(HTTPBaseExporter):
    """
    Exporter for HTTP, used to send events to an HTTP endpoint.
    """

    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG, SignalType.METRIC, SignalType.SPAN}
    
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
    
    async def healthcheck(self) -> bool:
        success = True
        error_message = ""
        try:
            response = await self.client.get(self.url, timeout=10.0)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Health check failed for WebhookExporter: {e}")
            success = False
            error_message = str(e)

        from telemetry.api import internal_telemetry_manager
        internal_telemetry_manager.track_healthcheck(
            "WebhookExporter",
            success,
            "Health check passed for WebhookExporter." if success else f"Health check failed for WebhookExporter: {error_message}",
            {"url": self.url}
        )

        if success:
            logger.info("Health check passed for WebhookExporter.")
        else:
            logger.error("Health check failed for WebhookExporter.")
        return success

    async def status(self) -> dict:
        """
        Returns the status of the WebhookExporter, including the URL and connection status.
        """
        if not self.client:
            return {"status": HealthStatus.UNHEALTHY, "message": "WebhookExporter is not connected."}
        
        return {
            "status": HealthStatus.HEALTHY,
            "url": self.url,
            "headers": self.headers,
            "auth": str(self.auth) if self.auth else None
        }