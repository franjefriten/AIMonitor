from exporters.base import BaseDatabaseExporter
from configs.config import get_settings
from utils.logger import logger
from core.event import BaseSignal, SignalType, MCPEvent, LogEvent, MetricEvent, SpanEvent
from typing import List
import json
from datetime import datetime
from enum import Enum

settings = get_settings()

SIGNAL_TABLE_SUFFIX = {
    SignalType.EVENT: "event",
    SignalType.LOG: "log",
    SignalType.METRIC: "metric",
    SignalType.SPAN: "span",
}

SIGNAL_MODEL_MAP = {
    SignalType.EVENT: MCPEvent,
    SignalType.LOG: LogEvent,
    SignalType.METRIC: MetricEvent,
    SignalType.SPAN: SpanEvent
}

class SQLiteExporter(BaseDatabaseExporter):

    SUPPORTED_SIGNALS = {SignalType.EVENT, SignalType.LOG, SignalType.METRIC, SignalType.SPAN}

    def __init__(self, dsn: str = settings.sqlite_uri, table_name: str = "aimonitor"):
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

    def _signal_table_name(self, signal_type: SignalType) -> str:
        suffix = SIGNAL_TABLE_SUFFIX.get(signal_type, signal_type.value)
        return f"{self.table_name}_{suffix}"

    def _serialize_value(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        if isinstance(value, Enum):
            return value.value
        return value

    def _create_table_sql(self, signal_type: SignalType) -> str:
        model = SIGNAL_MODEL_MAP[signal_type]
        table_name = self._signal_table_name(signal_type)
        return model.as_sqlite_table(table_name=table_name)

    async def _open_connection(self):
        self.client = await self.aiosqlite.connect(database=self.dsn)
        await self.client.execute("PRAGMA journal_mode=WAL;")
        await self.client.commit()

    async def _create_table_if_not_exists(self):
        for signal_type in SignalType:
            if signal_type not in SIGNAL_MODEL_MAP:
                continue
            query = self._create_table_sql(signal_type)
            await self.client.execute(query)
        await self.client.commit()

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None

    async def export(self, event: BaseSignal):
        await self.export_batch([event])
    
    async def export_batch(self, event_batch: List[BaseSignal]):
        if not self.client:
            raise RuntimeError(f"client for {self.__class__.__name__} not initialized")

        batches: dict[str, List[BaseSignal]] = {}
        for event in event_batch:
            table_name = self._signal_table_name(event.event_type)
            batches.setdefault(table_name, []).append(event)

        for table_name, events in batches.items():
            field_names = list(events[0].__class__.model_fields.keys())
            columns = ", ".join(field_names)
            placeholders = ", ".join(["?" for _ in field_names])
            rows = []
            for event in events:
                row = [self._serialize_value(getattr(event, field)) for field in field_names]
                rows.append(tuple(row))
            await self.client.executemany(
                f"INSERT OR REPLACE INTO {table_name} ({columns}) VALUES ({placeholders})",
                rows,
            )

        await self.client.commit()

    
    async def healthcheck(self) -> bool:
        """
        Health check for the SQLiteExporter. This exporter is considered healthy if it can connect to the SQLite database.
        """
        success = True
        try:
            async with self.client.execute("SELECT 1;") as cursor:
                await cursor.fetchone()
        except Exception as e:
            logger.error(f"Health check failed for SQLiteExporter: {e}")
            success = False
        return success
    
    async def status(self) -> dict:
        """
        Returns the status of the SQLiteExporter, including the connection status and database file path.
        """
        if not self.client:
            return {"status": "unhealthy", "message": "SQLiteExporter is not connected."}
        
        return {
            "status": "healthy",
            "database": self.dsn,
            "table_name": self.table_name
        }
