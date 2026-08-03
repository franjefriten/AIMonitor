from exporters.base import BaseExporter, HTTPBaseExporter
from core.event import BaseSignal, SignalType
from utils.logger import logger
import httpx
import asyncio
from datetime import datetime
from datetime import UTC
from exporters.base import with_retry
from typing import List, Literal, Optional
import sys, os
from typing import Protocol
import aiofiles
from pathlib import Path
from configs.config import get_settings

settings = get_settings()

# Tu Protocolo está perfecto
class AsyncWritable(Protocol):
    async def write(self, data: str) -> int: ...
    async def writelines(self, lines: List[str]) -> None: ...
    async def close(self) -> None: ...
    async def flush(self) -> None: ...
    @property
    def closed(self) -> bool: ...

class FileExporter(BaseExporter):

    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG, SignalType.METRIC}

    def __init__(
            self, base_uri: str | Path = settings.file_exporter_logs, 
            mode: Literal['a', 'w', 'x'] = 'a',
            max_bytes: float = (1024 * settings.max_mb_per_file * 1024)
        ):
        super().__init__()
        self.base_uri = Path(base_uri)
        self.mode = mode
        self.client: Optional[AsyncWritable] = None
        self.max_bytes = max_bytes
        #self.current_size = 0

        # make sure it exists
        self.base_uri.mkdir(parents=True, exist_ok=True) 

        # rotation vars
        self.rotation = 1
        self.date: datetime = datetime.now(UTC).date()
        self.file_uri: str = self._generate_uri()

    def _is_date_today(self) -> bool:
        return self.date == datetime.now(UTC).date()

    def _generate_uri(self):
        return self.base_uri / f"{self.date.strftime(r'%Y-%m-%d')}_logfile{'_' + str(self.rotation) if self.rotation > 1 else ''}.jsonl"

    async def _check_and_rotate(self, incoming_file_size):
        # Check if we are need to update date
        if not self._is_date_today():
            await self.close()
            self.date = datetime.now(UTC).date() # Update date
            self.rotation = 1 # Reset rotation to 1
            file_uri = Path(self._generate_uri()) # Regenerate file uri
            self.file_uri = file_uri
            await self.connect()
        
        if self.file_uri.stat().st_size + incoming_file_size >= self.max_bytes:
            await self.close()
            self.rotation += 1
            self.file_uri = self._generate_uri()
            await self.connect()

    async def connect(self) -> None:
        self.client = await aiofiles.open(self.file_uri, mode=self.mode)
        #self.current_size = self.file_uri.stat().st_size if self.file_uri.exists() else 0

    async def close(self) -> None:
        if self.client and not self.client.closed:
            await self.client.close()  
        
    async def export(self, event: BaseSignal) -> None:
        await self.export_batch([event])
    
    async def export_batch(self, event_batch: List[BaseSignal]) -> None:
        if not self.client:
            logger.error(f"client for {self.__class__.__name__} not initialized")
        lines = []
        for event in event_batch:
            if event.event_type not in self.SUPPORTED_SIGNALS:
                logger.warning(
                    "Event type '%s' with id: '%s' is not supported by FileExporter. Skipping export for event.",
                    event.event_type,
                    event.id
                )
            else:
                lines.append(f"{datetime.now(UTC)}: {event.model_dump_json()}\n")

        bytes_lines = len(bytes("".join(lines).encode()))

        await self._check_and_rotate(incoming_file_size=bytes_lines)

        await self.client.writelines(lines)
        await self.client.flush()