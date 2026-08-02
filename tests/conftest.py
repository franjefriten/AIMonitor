import random
from datetime import datetime, UTC
from core.event import MCPEvent 


def _generate_mcp_event():
    return MCPEvent(
        tool_name="some_tool",
        args={"args": {"some_list": [random.randint(0, 10) for _ in range(10)]}},
        status="success",
        error="",
        metadata={},
        delta=random.random(),
        timestamp=datetime.now(UTC).strftime('%Y-%m-%d'),
        result={}
    )