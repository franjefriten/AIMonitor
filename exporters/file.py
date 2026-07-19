from exporters.base import BaseExporter, HTTPBaseExporter
from core.event import MCPEvent
from utils.logger import logger
import httpx
import asyncio
import datetime
from exporters.base import with_retry
from typing import List, Literal, Optional
import sys, os
from typing import Protocol
import aiofiles
from pathlib import Path


import aiofiles
import datetime
from typing import Literal, Optional, Protocol, List
from pathlib import Path

# Tu Protocolo está perfecto
class AsyncWritable(Protocol):
    async def write(self, data: str) -> int: ...
    async def writelines(self, lines: List[str]) -> None: ...
    async def close(self) -> None: ...
    async def flush(self) -> None: ...
    @property
    def closed(self) -> bool: ...

class FileExporter(BaseExporter):
    def __init__(self, uri: str | Path, mode: Literal['a', 'w', 'x'] = 'a'):
        super().__init__()
        self.uri = uri
        self.mode = mode
        self.client: Optional[AsyncWritable] = None

    async def connect(self) -> None:  
        self.client = await aiofiles.open(self.uri, mode=self.mode)

    async def close(self) -> None:
        if self.client and not self.client.closed:
            await self.client.close()  
        
    async def export(self, event: MCPEvent) -> None:
        await self.export_batch([event])
    
    async def export_batch(self, event_batch: List[MCPEvent]) -> None:
        if not self.client:
            raise RuntimeError("Exporter not connected")

        lines = [
            f"{datetime.datetime.now(datetime.UTC)}: {e.model_dump_json()}\n"
            for e in event_batch
        ]
        
        await self.client.writelines(lines)
        await self.client.flush()