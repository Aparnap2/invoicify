"""
Unit tests for DigitalOcean Spaces Adapter
Following TDD approach
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pickle
from io import BytesIO

from temporal.activities.anomaly import load_model, save_model, detect_anomaly
from river import anomaly


class TestDOSpacesAdapter:
    """Test suite for DigitalOcean Spaces adapter."""

    @pytest.fixture
    def mock_boto3_client(self):
        """Mock boto3 client for DO Spaces."""
        with patch("temporal.activities.anomaly.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            yield mock_client

    @pytest.mark.asyncio
    async def test_load_model_from_do_spaces(self, mock_boto3_client):
        """Test loading model from DigitalOcean Spaces."""
        # Arrange
        vendor_id = "test-vendor"
        model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)
        model_bytes = pickle.dumps(model)
        
        mock_response = {
            "Body": BytesIO(model_bytes)
        }
        mock_boto3_client.get_object.return_value = mock_response
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            result = await load_model(vendor_id)
        
        # Assert
        assert result is not None
        mock_boto3_client.get_object.assert_called_once_with(
            Bucket="invoicify-storage",
            Key=f"ml-models/{vendor_id}.pkl"
        )

    @pytest.mark.asyncio
    async def test_load_model_returns_none_when_not_found(self, mock_boto3_client):
        """Test that load_model returns None when model not found."""
        # Arrange
        vendor_id = "test-vendor"
        mock_boto3_client.get_object.side_effect = Exception("NoSuchKey")
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            result = await load_model(vendor_id)
        
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_save_model_to_do_spaces(self, mock_boto3_client):
        """Test saving model to DigitalOcean Spaces."""
        # Arrange
        vendor_id = "test-vendor"
        model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            await save_model(vendor_id, model)
        
        # Assert
        mock_boto3_client.put_object.assert_called_once()
        call_args = mock_boto3_client.put_object.call_args
        assert call_args[1]["Bucket"] == "invoicify-storage"
        assert call_args[1]["Key"] == f"ml-models/{vendor_id}.pkl"
        assert "Body" in call_args[1]

    @pytest.mark.asyncio
    async def test_detect_anomaly_creates_new_model_if_none_exists(self, mock_boto3_client):
        """Test that detect_anomaly creates new model if none exists."""
        # Arrange
        vendor_id = "test-vendor"
        amount = 100.0
        mock_boto3_client.get_object.side_effect = Exception("NoSuchKey")
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            result = await detect_anomaly(amount, vendor_id)
        
        # Assert
        assert result is not None
        assert "score" in result
        assert "is_anomaly" in result
        assert result["vendor_id"] == vendor_id
        # Should save the new model
        assert mock_boto3_client.put_object.called

    @pytest.mark.asyncio
    async def test_detect_anomaly_loads_existing_model(self, mock_boto3_client):
        """Test that detect_anomaly loads existing model."""
        # Arrange
        vendor_id = "test-vendor"
        amount = 100.0
        model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)
        model_bytes = pickle.dumps(model)
        
        mock_response = {
            "Body": BytesIO(model_bytes)
        }
        mock_boto3_client.get_object.return_value = mock_response
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            result = await detect_anomaly(amount, vendor_id)
        
        # Assert
        assert result is not None
        assert "score" in result
        assert "is_anomaly" in result
        # Should load and save the updated model
        assert mock_boto3_client.get_object.called
        assert mock_boto3_client.put_object.called

    @pytest.mark.asyncio
    async def test_do_spaces_client_uses_correct_endpoint(self):
        """Test that DO Spaces client uses correct endpoint."""
        # Arrange
        vendor_id = "test-vendor"
        model = anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=100)
        model_bytes = pickle.dumps(model)
        
        with patch("temporal.activities.anomaly.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_response = {
                "Body": BytesIO(model_bytes)
            }
            mock_client.get_object.return_value = mock_response
            mock_boto3.client.return_value = mock_client
            
            with patch.dict("os.environ", {
                "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
                "DO_SPACES_ACCESS_KEY": "test_key",
                "DO_SPACES_SECRET_KEY": "test_secret",
                "DO_SPACES_BUCKET": "invoicify-storage"
            }):
                # Act
                await load_model(vendor_id)
            
            # Assert
            mock_boto3.client.assert_called_once_with(
                service_name="s3",
                endpoint_url="https://nyc3.digitaloceanspaces.com",
                aws_access_key_id="test_key",
                aws_secret_access_key="test_secret",
                region_name="nyc3"
            )

    @pytest.mark.asyncio
    async def test_do_spaces_handles_timeout_gracefully(self, mock_boto3_client):
        """Test that DO Spaces adapter handles timeout gracefully."""
        # Arrange
        vendor_id = "test-vendor"
        mock_boto3_client.get_object.side_effect = TimeoutError("Connection timeout")
        
        with patch.dict("os.environ", {
            "DO_SPACES_ENDPOINT": "https://nyc3.digitaloceanspaces.com",
            "DO_SPACES_ACCESS_KEY": "test_key",
            "DO_SPACES_SECRET_KEY": "test_secret",
            "DO_SPACES_BUCKET": "invoicify-storage"
        }):
            # Act
            result = await load_model(vendor_id)
        
        # Assert
        assert result is None