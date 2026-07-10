from exporters.base import BaseExporter
from core.event import MCPEvent

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

    def export(self, event: MCPEvent) -> None:
        """
        Export the given event to Redis.

        :param event: The event to be exported.
        """
        # Convert the event to a dictionary and send it to Redis
        event_dict = event.model_dump_json()
        self.redis_client.publish('mcp_events', str(event_dict))