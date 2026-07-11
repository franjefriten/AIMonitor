import pytest
import asyncio
import pytest_asyncio
from exporters.base import BaseExporter
from core.registry import ExporterRegistry
from core.registry import registry
from datetime import datetime, UTC
from core.decorators import monitor_tool

class MockExporter(BaseExporter):
    async def export():
        raise ConnectionError("Service Down")   

@pytest.mark.asyncio
async def test_tool_monitoring_workflow():
    # 1. Setup: añadimos un exportador mockeado
    mock = MockExporter()
    registry.add_exporter(mock)
    
    # 2. Definimos una tool mock
    @monitor_tool
    async def sample_tool(name: str, api_key: str):
        return f"Hello {name}"
    
    # 3. Ejecutamos
    await sample_tool(name="Gemini", api_key="secret_123")
    
    # 4. Esperamos a que el worker procese (pequeño sleep por la async nature)
    await asyncio.sleep(0.1)
    
    # 5. Verificaciones
    assert len(mock.events) == 1
    assert mock.events[0].tool_name == "sample_tool"
    assert mock.events[0].arguments["api_key"] == "********" # Verificamos redacción