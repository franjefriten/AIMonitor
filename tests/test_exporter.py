import pytest
from pathlib import Path
from datetime import datetime, UTC
import random

# Asumiendo que tu clase está en mcp.exporters.file
from exporters.file import FileExporter 
from core.event import MCPEvent # Tu modelo de evento


def _generate_mcp_event():
    return MCPEvent(
        tool_name="some_tool",
        args={"args": {"some_list": [random.randint(0, 10) for _ in range(10)]}},
        status="success",
        error="",
        metadata="",
        delta=random.random(),
        timestamp=datetime.now(UTC),
        result={}
    )


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
