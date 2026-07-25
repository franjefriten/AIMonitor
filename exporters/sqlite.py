from exporters.base import BaseDatabaseExporter
from core.config import settings
from utils.logger import logger
from core.event import MCPEvent
from typing import List
import json
from datetime import datetime
from enum import Enum


class SQLiteExporter(BaseDatabaseExporter):
    def __init__(self, dsn: str = settings.sqlite_url, table_name: str = "events"):
        super().__init__(dsn=dsn)
        try:
            import aiosqlite
            self.aiosqlite = aiosqlite
        except ImportError:
            logger.error(f"aiosqlite is not installed, cannot use {self.__class__.__name__}")
            raise ImportError(
                (
                    f"aiosqlite is not installed, cannot use {self.__class__.__name__} exporter"
                    f"Please install it by running pip install .[sqlite] or uv sync --extra sqlite"
                )
            )
        self.client = None
        self.table_name = table_name

    async def _open_connection(self):
        self.client = await self.aiosqlite.connect(database=self.dsn)
        await self.client.execute("PRAGMA journal_mode=WAL;") # Faster execution
        await self.client.commit()
    
    async def _create_table_if_not_exists(self):
        query = MCPEvent.as_sqlite_table(table_name=self.table_name)
        print(query)
        await self.client.execute(query)

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None

    async def export(self, event: MCPEvent):
        await self.export_batch([event])
    
    async def export_batch(self, event_batch: List[MCPEvent]):
        if not self.client:
            raise RuntimeError(f"client for {self.__class__.__name__} not initialized")
        
        field_names = MCPEvent.model_fields
        columns = ", ".join(field_names)
        data = []
        for e in event_batch:
            row_values = []
            for field in field_names:
                val = getattr(e, field)
                
                # 1. DEPRECATED: datetime no longer supported for sqlite3 adapters, convert to ISO string
                if isinstance(val, datetime):
                    val = val.isoformat()
                # 2. If dict or list, serialize to json for BLOB management
                elif isinstance(val, (dict, list)):
                    import json
                    val = json.dumps(val)
                # 3. If enum, pick up native value
                elif isinstance(val, Enum):
                    val = val.value
                    
                row_values.append(val)
            
            data.append(tuple(row_values))     
        placeholders = ", ".join(["?" for _ in range(len(field_names))])
        await self.client.executemany(
            f"INSERT OR REPLACE INTO {self.table_name} ({columns}) VALUES ({placeholders})",
            data
        )

        await self.client.commit()
        
        
    
