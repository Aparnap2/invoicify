# Step 2: Event Producer Implementation (TDD)

## Task: Create worker/src/lib/events.py

### Test First (Red)

Create `worker/tests/unit/test_events.py`:

```python
import pytest
import asyncio
from unittest.mock import Mock, patch
import json

from worker.src.lib.events import EventProducer


class TestEventProducer:
    """Unit tests for event producer."""
    
    @pytest.fixture
    def producer_config(self):
        return {
            'bootstrap_servers': 'localhost:19092',
            'topic': 'invoice.ingested'
        }
    
    @pytest.mark.asyncio
    async def test_producer_initializes_with_config(self, producer_config):
        """Test producer initializes with correct config."""
        with patch('aiokafka.AIOKafkaProducer') as mock_kafka:
            producer = EventProducer(**producer_config)
            assert producer.bootstrap_servers == 'localhost:19092'
            assert producer.topic == 'invoice.ingested'
    
    @pytest.mark.asyncio
    async def test_produce_sends_json_message(self, producer_config):
        """Test that produce sends JSON message to Kafka."""
        with patch('aiokafka.AIOKafkaProducer') as mock_kafka:
            mock_producer = Mock()
            mock_kafka.return_value = mock_producer
            
            producer = EventProducer(**producer_config)
            await producer.start()
            
            test_event = {
                'invoice_id': 'test-001',
                'vendor': 'Acme Corp',
                'amount': 500.00
            }
            
            await producer.produce(test_event)
            
            # Assert send was called
            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            
            # Check topic
            assert call_args[0][0] == 'invoice.ingested'
            
            # Check message is valid JSON
            message = json.loads(call_args[1]['value'])
            assert message['invoice_id'] == 'test-001'
            assert message['vendor'] == 'Acme Corp'
            assert message['amount'] == 500.00
    
    @pytest.mark.asyncio
    async def test_producer_adds_timestamp(self, producer_config):
        """Test that producer adds timestamp to events."""
        with patch('aiokafka.AIOKafkaProducer') as mock_kafka:
            mock_producer = Mock()
            mock_kafka.return_value = mock_producer
            
            producer = EventProducer(**producer_config)
            await producer.start()
            
            await producer.produce({'test': 'data'})
            
            message = json.loads(mock_producer.send.call_args[1]['value'])
            assert 'timestamp' in message
            assert 'test' in message
```

### Implementation (Green)

Create `worker/src/lib/events.py`:

```python
import json
import logging
from datetime import datetime
from typing import Dict, Any

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class EventProducer:
    """
    Kafka event producer for invoice events.
    
    Uses aiokafka for async Kafka operations.
    Compatible with Redpanda (Kafka API).
    """
    
    def __init__(self, bootstrap_servers: str, topic: str = 'invoice.ingested'):
        """
        Initialize producer.
        
        Args:
            bootstrap_servers: Kafka bootstrap servers
            topic: Default topic to produce to
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._producer: AIOKafkaProducer | None = None
    
    async def start(self):
        """Start the producer."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda v: v.encode('utf-8') if v else None
            )
            await self._producer.start()
            logger.info(f"EventProducer started: {self.bootstrap_servers}")
    
    async def stop(self):
        """Stop the producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("EventProducer stopped")
    
    async def produce(self, event: Dict[str, Any], key: str | None = None) -> None:
        """
        Produce an event to Kafka.
        
        Args:
            event: Event data (will be JSON serialized)
            key: Optional partition key
        """
        if self._producer is None:
            await self.start()
        
        # Add metadata
        event['timestamp'] = datetime.utcnow().isoformat()
        event['producer'] = 'nivi-worker'
        
        try:
            await self._producer.send(
                topic=self.topic,
                value=event,
                key=key
            )
            logger.debug(f"Produced event: {event.get('invoice_id', 'N/A')}")
        except Exception as e:
            logger.error(f"Failed to produce event: {e}")
            raise
```

### Verification

Run the test:
```bash
cd /home/aparna/Desktop/invoicify/worker
pytest tests/unit/test_events.py -v
```

Expected: All tests pass.
