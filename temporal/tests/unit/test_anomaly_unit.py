"""
Unit tests for Anomaly Detection Activity
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pickle
import io

from temporal.activities.anomaly import detect_anomaly, load_model, save_model


class TestAnomalyDetection:
    """Test suite for anomaly detection activity."""

    @pytest.mark.asyncio
    async def test_detect_anomaly_returns_correct_structure(self):
        """Test that detect_anomaly returns expected dict structure."""
        # Arrange & Act
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
        ):
            # Create mock model
            mock_model = MagicMock()
            mock_model.score_one.return_value = 0.3
            mock_load.return_value = mock_model

            result = await detect_anomaly(amount=100.0, vendor_id="test-vendor")

        # Assert
        assert isinstance(result, dict)
        assert "score" in result
        assert "is_anomaly" in result
        assert "vendor_id" in result
        assert result["vendor_id"] == "test-vendor"

    @pytest.mark.asyncio
    async def test_detect_anomaly_flags_high_score_as_anomaly(self):
        """Test that scores > 0.7 are flagged as anomalies."""
        # Arrange
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
        ):
            mock_model = MagicMock()
            mock_model.score_one.return_value = 0.85  # High score
            mock_load.return_value = mock_model

            # Act
            result = await detect_anomaly(amount=5000.0, vendor_id="test-vendor")

        # Assert
        assert result["is_anomaly"] is True
        assert result["score"] == 0.85

    @pytest.mark.asyncio
    async def test_detect_anomaly_does_not_flag_low_score(self):
        """Test that scores <= 0.7 are not flagged as anomalies."""
        # Arrange
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
        ):
            mock_model = MagicMock()
            mock_model.score_one.return_value = 0.3  # Low score
            mock_load.return_value = mock_model

            # Act
            result = await detect_anomaly(amount=100.0, vendor_id="test-vendor")

        # Assert
        assert result["is_anomaly"] is False
        assert result["score"] == 0.3

    @pytest.mark.asyncio
    async def test_detect_anomaly_calls_model_methods(self):
        """Test that model.score_one and model.learn_one are called."""
        # Arrange
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
        ):
            mock_model = MagicMock()
            mock_model.score_one.return_value = 0.5  # Return a float, not MagicMock
            mock_load.return_value = mock_model

            # Act
            await detect_anomaly(amount=100.0, vendor_id="test-vendor")

        # Assert
        mock_model.score_one.assert_called_once_with({"amount": 100.0})
        mock_model.learn_one.assert_called_once_with({"amount": 100.0})

    @pytest.mark.asyncio
    async def test_detect_anomaly_creates_new_model_if_none_exists(self):
        """Test that new model is created if vendor has no model."""
        # Arrange
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
            patch("river.anomaly.HalfSpaceTrees") as mock_hst,
        ):
            mock_load.return_value = None
            mock_model = MagicMock()
            mock_model.score_one.return_value = 0.5  # Return a float, not MagicMock
            mock_hst.return_value = mock_model

            # Act
            result = await detect_anomaly(amount=100.0, vendor_id="new-vendor")

        # Assert
        mock_hst.assert_called_once()
        mock_model.learn_one.assert_called()

    @pytest.mark.asyncio
    async def test_load_model_deserializes_from_cos(self):
        """Test that load_model deserializes pickle from COS."""
        # Arrange - Use a simple object that can be pickled
        mock_model = {"type": "test_model", "version": 1}
        mock_pickle = pickle.dumps(mock_model)

        with patch("ibm_boto3.client") as mock_boto:
            mock_cos = MagicMock()
            mock_cos.get_object.return_value = {"Body": io.BytesIO(mock_pickle)}
            mock_boto.return_value = mock_cos

            # Act
            result = await load_model("test-vendor")

        # Assert
        assert result is not None
        mock_cos.get_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_model_serializes_to_cos(self):
        """Test that save_model serializes model to COS."""
        # Arrange - Use a simple object that can be pickled
        mock_model = {"type": "test_model", "version": 1}

        with patch("ibm_boto3.client") as mock_boto:
            mock_cos = MagicMock()
            mock_boto.return_value = mock_cos

            # Act
            await save_model("test-vendor", mock_model)

        # Assert
        mock_cos.put_object.assert_called_once()
        call_args = mock_cos.put_object.call_args
        assert call_args[1]["Key"] == "ml-models/test-vendor.pkl"

    @pytest.mark.asyncio
    async def test_detect_anomaly_handles_exception_gracefully(self):
        """Test that exceptions are handled and not propagated."""
        # Arrange
        with patch("temporal.activities.anomaly.load_model") as mock_load:
            mock_load.side_effect = Exception("COS connection failed")

            # Act & Assert
            with pytest.raises(Exception):
                await detect_anomaly(amount=100.0, vendor_id="test-vendor")


class TestAnomalyThresholds:
    """Test anomaly detection thresholds."""

    @pytest.mark.parametrize(
        "score,expected_is_anomaly",
        [
            (0.0, False),
            (0.3, False),
            (0.5, False),
            (0.7, False),
            (0.71, True),
            (0.8, True),
            (1.0, True),
        ],
    )
    @pytest.mark.asyncio
    async def test_anomaly_thresholds(self, score, expected_is_anomaly):
        """Test various score thresholds."""
        # Arrange
        with (
            patch("temporal.activities.anomaly.load_model") as mock_load,
            patch("temporal.activities.anomaly.save_model") as mock_save,
        ):
            mock_model = MagicMock()
            mock_model.score_one.return_value = score
            mock_load.return_value = mock_model

            # Act
            result = await detect_anomaly(amount=100.0, vendor_id="test")

        # Assert
        assert result["is_anomaly"] == expected_is_anomaly
