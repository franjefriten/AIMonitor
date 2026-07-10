from exporters.base import BaseExporter
from core.event import MCPEvent
from utils.logger import logger

class RedisExporter(BaseExporter):
    """
    Exporter for Redis, used to send events to a Redis server.
    """
    
    def __init__(self, redis):
        """
        Initialize the RedisExporter with a Redis client.

        :param redis_client: The Redis client to use for sending events.
        """
        self.redis = redis

    @with_retry()
    def export(self, event: MCPEvent) -> None:
        """
        Export the given event to Redis.

        :param event: The event to be exported.
        """
        # Convert the event to a dictionary and send it to Redis
        event_dict = event.model_dump_json()
        status_icon = "✅" if event.status == "success" else "❌"
        logger.info(f"{status_icon} [Exec time: {event.delta}] {event.tool_name} - Status: {event.status}, Args: {event.args}, Result: {event.result}"f"{status_icon} [Exec time: {event.delta}] {event.tool_name} - Status: {event.status}, Args: {event.args}, Result: {event.result}")
        self.redis_client.publish('mcp_events', str(event_dict))