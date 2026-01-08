"""Redis Streams for reliable event delivery."""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class StreamMessage:
    message_id: str
    event_type: str
    data: Dict[str, Any]
    timestamp: str


class EventStream:
    """Redis Streams wrapper for reliable event delivery."""

    STREAM_KEY = "ralph:stream:events"
    CONSUMER_GROUP = "ralph-agents"

    def __init__(self, redis_client, consumer_id: str):
        self.redis = redis_client
        self.consumer_id = consumer_id
        self._ensure_consumer_group()

    def _ensure_consumer_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self.redis.xgroup_create(
                self.STREAM_KEY,
                self.CONSUMER_GROUP,
                id='0',
                mkstream=True
            )
        except Exception as e:
            # Group already exists
            if 'BUSYGROUP' not in str(e):
                raise

    def publish(self, event_type: str, data: Dict[str, Any]) -> str:
        """Publish event to stream. Returns message ID."""
        message_id = self.redis.xadd(self.STREAM_KEY, {
            'type': event_type,
            'data': json.dumps(data),
            'timestamp': datetime.utcnow().isoformat(),
            'producer': self.consumer_id
        })
        return message_id.decode() if isinstance(message_id, bytes) else message_id

    def consume(self, count: int = 10, block_ms: int = 1000) -> List[StreamMessage]:
        """Consume messages from stream."""
        messages = []

        result = self.redis.xreadgroup(
            self.CONSUMER_GROUP,
            self.consumer_id,
            {self.STREAM_KEY: '>'},
            count=count,
            block=block_ms
        )

        if result:
            for stream_name, stream_messages in result:
                for msg_id, msg_data in stream_messages:
                    msg_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                    # Decode message data
                    decoded = {}
                    for k, v in msg_data.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        decoded[key] = val

                    messages.append(StreamMessage(
                        message_id=msg_id,
                        event_type=decoded.get('type', ''),
                        data=json.loads(decoded.get('data', '{}')),
                        timestamp=decoded.get('timestamp', '')
                    ))

        return messages

    def ack(self, message_id: str):
        """Acknowledge message was processed."""
        self.redis.xack(self.STREAM_KEY, self.CONSUMER_GROUP, message_id)

    def get_pending(self) -> List[Dict[str, Any]]:
        """Get pending messages that haven't been acknowledged."""
        pending = self.redis.xpending(self.STREAM_KEY, self.CONSUMER_GROUP)
        return pending if pending else []

    def claim_stale(self, min_idle_ms: int = 60000, count: int = 10) -> List[StreamMessage]:
        """Claim messages that have been pending too long (dead consumer)."""
        messages = []

        # Get pending messages
        pending = self.redis.xpending_range(
            self.STREAM_KEY,
            self.CONSUMER_GROUP,
            min='-',
            max='+',
            count=count
        )

        if pending:
            message_ids = [p['message_id'] for p in pending if p.get('time_since_delivered', 0) > min_idle_ms]

            if message_ids:
                claimed = self.redis.xclaim(
                    self.STREAM_KEY,
                    self.CONSUMER_GROUP,
                    self.consumer_id,
                    min_idle_ms,
                    message_ids
                )

                for msg_id, msg_data in claimed:
                    msg_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    decoded = {}
                    for k, v in msg_data.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        decoded[key] = val

                    messages.append(StreamMessage(
                        message_id=msg_id,
                        event_type=decoded.get('type', ''),
                        data=json.loads(decoded.get('data', '{}')),
                        timestamp=decoded.get('timestamp', '')
                    ))

        return messages
