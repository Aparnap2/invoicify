"""
Event Producer Implementation (TDD - Step 2)
Fixed: CodeRabbit review issues
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class EventProducer:
    """
    Kafka event producer for invoice events.

    Uses aiokafka for async Kafka operations.
    Compatible with Redpanda (Kafka API).
    """

    def __init__(self, bootstrap_servers: str, topic: str = "invoice.ingested") -> None:
        """
        Initialize producer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            topic: Default topic to produce to
        """
        self.bootstrap_servers: str = bootstrap_servers
        self.topic: str = topic
        self._producer: Optional[AIOKafkaProducer] = None

    def _serialize_value(self, v: Dict[str, Any]) -> bytes:
        """Serialize value to JSON bytes."""
        return json.dumps(v).encode("utf-8")

    def _serialize_key(self, v: Optional[str]) -> Optional[bytes]:
        """Serialize key to bytes."""
        return v.encode("utf-8") if v else None

    async def start(self) -> None:
        """Start the producer."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=self._serialize_value,
                key_serializer=self._serialize_key,
            )
            await self._producer.start()
            logger.info(f"EventProducer started: {self.bootstrap_servers}")

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("EventProducer stopped")

    async def produce(self, event: Dict[str, Any], key: Optional[str] = None) -> None:
        """
        Produce an event to Kafka.

        Args:
            event: Event data (will be JSON serialized)
            key: Optional partition key

        Raises:
            TypeError: If event is not a dict
            RuntimeError: If producer fails to send
        """
        if not isinstance(event, dict):
            raise TypeError(f"Event must be a dict, got {type(event).__name__}")

        if self._producer is None:
            await self.start()

        # Create new dict to avoid mutating input
        event_with_meta = {
            **event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "producer": "nivi-worker",
        }

        try:
            await self._producer.send(topic=self.topic, value=event_with_meta, key=key)
            logger.debug(f"Produced event: {event.get('invoice_id', 'N/A')}")
        except Exception as e:
            logger.error(f"Failed to produce event: {e}")
            raise RuntimeError(f"Failed to produce event: {e}") from e
