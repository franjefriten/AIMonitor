from exporters.base import BaseExporter
from core.event import BaseSignal
from utils.logger import logger
from exporters.base import with_retry

class RedisExporter(BaseExporter):
    """
    Exporter for Redis, used to send events to a Redis server.
    """

    def __init__(self, redis):
        """
        Initialize the RedisExporter with a Redis client.

        :param redis: The Redis client to use for sending events.
        """
        self.redis = redis

    @with_retry
    def export(self, event: BaseSignal) -> None:
        """
        Export the given event to Redis.

        :param event: The event to be exported.
        """
        event_dict = event.model_dump_json()
        status_icon = "✅" if str(event.status).lower() == "success" else "❌"
        logger.info(
            "%s [Exec time: %s] %s - Status: %s, Args: %s, Result: %s",
            status_icon,
            event.delta,
            event.tool_name,
            event.status,
            event.args,
            event.result,
        )
        self.redis.publish("mcp_events", str(event_dict))