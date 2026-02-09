"""
Unit tests for Event Producer (TDD - Step 2)
Fixed: CodeRabbit review issues - proper mocking, resource cleanup
"""

import sys

sys.path.insert(0, "/home/aparna/Desktop/invoicify/python-worker/src")

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import json

from lib.events import EventProducer


class TestEventProducer:
    """Unit tests for Kafka/Redpanda event producer."""

    @pytest.fixture
    def producer_config(self):
        """Test configuration."""
        return {"bootstrap_servers": "localhost:19092", "topic": "invoice.ingested"}

    @pytest.mark.asyncio
    async def test_producer_initializes_with_config(self, producer_config):
        """Test producer initializes with correct config."""
        # Arrange & Act
        producer = EventProducer(**producer_config)

        # Assert
        assert producer.bootstrap_servers == "localhost:19092"
        assert producer.topic == "invoice.ingested"

    @pytest.mark.asyncio
    async def test_produce_sends_json_message(self, producer_config):
        """Test that produce sends JSON message to Kafka."""
        # Arrange
        mock_producer = AsyncMock()
        mock_producer.send = AsyncMock()

        with patch.object(EventProducer, "_serialize_value") as mock_serialize:
            mock_serialize.return_value = b'{"test": "data"}'

            producer = EventProducer(**producer_config)
            producer._producer = mock_producer  # Inject mock

            test_event = {
                "invoice_id": "test-001",
                "vendor": "Acme Corp",
                "amount": 500.00,
            }

            # Act
            await producer.produce(test_event)

            # Assert
            mock_producer.send.assert_called_once()
            call_kwargs = mock_producer.send.call_args[1]
            assert call_kwargs["topic"] == "invoice.ingested"
            assert "value" in call_kwargs

    @pytest.mark.asyncio
    async def test_producer_adds_timestamp(self, producer_config):
        """Test that producer adds timestamp to events."""
        # Arrange
        mock_producer = AsyncMock()
        mock_producer.send = AsyncMock()

        with patch.object(EventProducer, "_serialize_value") as mock_serialize:
            captured_event = {}

            def capture_event(v):
                captured_event.update(v)
                return json.dumps(v).encode("utf-8")

            mock_serialize.side_effect = capture_event

            producer = EventProducer(**producer_config)
            producer._producer = mock_producer

            # Act
            await producer.produce({"test": "data"})

            # Assert
            assert "timestamp" in captured_event
            assert "producer" in captured_event
            assert captured_event["producer"] == "nivi-worker"

    @pytest.mark.asyncio
    async def test_producer_uses_custom_key(self, producer_config):
        """Test that producer uses custom partition key."""
        # Arrange
        mock_producer = AsyncMock()
        mock_producer.send = AsyncMock()

        producer = EventProducer(**producer_config)
        producer._producer = mock_producer

        # Act
        await producer.produce({"data": "test"}, key="custom-key-123")

        # Assert
        call_kwargs = mock_producer.send.call_args[1]
        assert call_kwargs["key"] == "custom-key-123"

    @pytest.mark.asyncio
    async def test_producer_handles_send_error(self, producer_config):
        """Test that producer handles send errors gracefully."""
        # Arrange
        mock_producer = AsyncMock()
        mock_producer.send = AsyncMock(side_effect=Exception("Kafka connection failed"))

        producer = EventProducer(**producer_config)
        producer._producer = mock_producer

        # Act & Assert
        with pytest.raises(RuntimeError, match="Kafka connection failed"):
            await producer.produce({"data": "test"})

    @pytest.mark.asyncio
    async def test_producer_validates_event_type(self, producer_config):
        """Test that producer validates event is a dict."""
        # Arrange
        producer = EventProducer(**producer_config)

        # Act & Assert
        with pytest.raises(TypeError, match="Event must be a dict"):
            await producer.produce("not a dict")

    @pytest.mark.asyncio
    async def test_producer_stops_cleanly(self, producer_config):
        """Test that producer stops cleanly."""
        # Arrange
        mock_producer = AsyncMock()
        mock_producer.stop = AsyncMock()

        producer = EventProducer(**producer_config)
        producer._producer = mock_producer

        # Act
        await producer.stop()

        # Assert
        mock_producer.stop.assert_called_once()
        assert producer._producer is None
