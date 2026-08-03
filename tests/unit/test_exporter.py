import pytest
from pathlib import Path
from datetime import datetime, UTC
import random

from exporters.file import FileExporter 
from exporters.sqlite import SQLiteExporter
from core.event import MCPEvent 
from tests.conftest import _generate_mcp_event, _generate_span_event

## FileExporter

@pytest.mark.asyncio
async def test_file_exporter_creates_file_and_writes(tmp_path):    
    exporter = FileExporter(base_uri=tmp_path, max_bytes=1024 * 1024)
    await exporter.connect()
    
    try:
        event = _generate_mcp_event()
        await exporter.export(event)
    finally:
        await exporter.close()
    
    # --- Asserts ---
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    
    content = files[0].read_text(encoding="utf-8")
    assert "success" in content


@pytest.mark.asyncio
async def test_file_exporter_count_events(tmp_path):
    # tmp_path made by asyncio
    file_exporter = FileExporter(base_uri=tmp_path, max_bytes=1024*1024)
    await file_exporter.connect()
    events_num = 1000
    try:
        events = [_generate_mcp_event() for _ in range(events_num)]
        await file_exporter.export_batch(event_batch=events)
    finally:
        await file_exporter.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1

    content_lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(content_lines) == events_num


@pytest.mark.asyncio
async def test_file_exporter_rotation(tmp_path):
    # small size for rotation purposes, 1 KB
    file_exporter = FileExporter(base_uri=tmp_path, max_bytes=1024)
    await file_exporter.connect()
    try:
        for _ in range(20):
            batch = [_generate_mcp_event() for _ in range(50)]
            await file_exporter.export_batch(event_batch=batch)
    finally:
        await file_exporter.close()    

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) >= 2


## SQLiteExporter

@pytest.mark.asyncio
async def test_writes_to_sqlite():
    try:
        import aiosqlite
    except ImportError:
        pytest.skip("aiosqlite is not installed, skipping SQLiteExporter test.")
    sqlite_exporter = SQLiteExporter(dsn=":memory:", table_name="events")
    batches = 20
    batch_length = 50
    try:
        await sqlite_exporter.connect()
        for _ in range(batches):
            batch = [_generate_mcp_event() for _ in range(batch_length)]
            await sqlite_exporter.export_batch(event_batch=batch)
        
        async with sqlite_exporter.client.execute("SELECT COUNT(*) FROM events_event;") as cursor:
            row = await cursor.fetchone()
            assert row[0] == batch_length * batches
    finally:
        await sqlite_exporter.close()


@pytest.mark.asyncio
async def test_span_events_wrote_to_sqlite():
    try:
        import aiosqlite
    except ImportError:
        pytest.skip("aiosqlite is not installed, skipping SQLiteExporter test.")
    
    sqlite_exporter = SQLiteExporter(dsn=":memory:", table_name="aimonitor")
    await sqlite_exporter.connect()
    try:
        batch = [
            _generate_span_event(
                parent_id="root_parent",
                trace_id="tool_call_trace",
                span_id="tool_1_call",
                operation_name=f"tool_1_call_operation_name"
            ),
            _generate_span_event(
                parent_id="tool_1_call",
                trace_id="tool_call_trace",
                span_id="tool_2_call",
                operation_name=f"tool_2_call_operation_name"
            ),
            _generate_span_event(
                parent_id="tool_2_call",
                trace_id="tool_call_trace",
                span_id="tool_3_call",
                operation_name=f"tool_3_call_operation_name"
            )
        ]
        await sqlite_exporter.export_batch(event_batch=batch)
    except Exception as e:
        pytest.fail(f"SQLiteExporter failed to write span events: {e}")

    try:
        async with sqlite_exporter.client.execute("SELECT COUNT(*) FROM aimonitor_span;") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 3
        async with sqlite_exporter.client.execute(
                "SELECT parent_id, trace_id, span_id, operation_name FROM aimonitor_span;") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 3
            for parent_id, trace_id, span_id, operation_name in rows:
                assert parent_id in ["root_parent", "tool_1_call", "tool_2_call"]
                assert trace_id == "tool_call_trace"
                assert span_id in ["tool_1_call", "tool_2_call", "tool_3_call"]
                assert operation_name in [
                    "tool_1_call_operation_name",
                    "tool_2_call_operation_name",
                    "tool_3_call_operation_name"
                ]
    except Exception as e:
        pytest.fail(f"Failed to query span events from SQLite: {e}")
    finally:
        await sqlite_exporter.close()
    
