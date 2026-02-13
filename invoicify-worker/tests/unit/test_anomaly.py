"""
Unit tests for Anomaly Detection (TDD - Step 3)
Fixed: CodeRabbit review issues - updated assertions, validation tests
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock, mock_open
import pickle

from activities.anomaly import AnomalyDetector, COSConfigError


class TestAnomalyDetector:
    """Unit tests for River ML anomaly detector."""

    @pytest.fixture
    def detector(self):
        """Create a fresh detector for each test."""
        return AnomalyDetector(vendor_id="test-vendor")

    def test_detector_initializes_with_vendor_id(self):
        """Test detector initializes with vendor ID."""
        # Arrange & Act
        detector = AnomalyDetector(vendor_id="acme-corp")

        # Assert - model is initialized immediately now
        assert detector.vendor_id == "acme-corp"
        assert detector.model is not None  # Model is auto-initialized

    def test_detector_raises_on_empty_vendor(self):
        """Test detector raises on empty vendor_id."""
        with pytest.raises(ValueError, match="vendor_id must be a non-empty string"):
            AnomalyDetector(vendor_id="")

    def test_detector_raises_on_invalid_threshold(self):
        """Test detector raises on invalid threshold."""
        with pytest.raises(ValueError, match="threshold must be between"):
            AnomalyDetector(vendor_id="test", threshold=1.5)

    def test_score_returns_float(self, detector):
        """Test that score returns a float."""
        # Act
        result = detector.score(amount=100.0)

        # Assert
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_score_raises_on_negative_amount(self, detector):
        """Test that score raises on negative amount."""
        with pytest.raises(ValueError, match="Amount cannot be negative"):
            detector.score(amount=-100.0)

    def test_learn_raises_on_negative_amount(self, detector):
        """Test that learn raises on negative amount."""
        with pytest.raises(ValueError, match="Amount cannot be negative"):
            detector.learn(amount=-100.0)

    def test_is_anomaly_returns_boolean(self, detector):
        """Test that is_anomaly returns boolean."""
        # Act
        result = detector.is_anomaly(amount=100.0)

        # Assert
        assert isinstance(result, bool)

    def test_save_model_creates_file(self, detector, tmp_path):
        """Test that save creates a model file."""
        # Arrange
        detector.learn(amount=100.0)
        model_path = tmp_path / "test-model.pkl"

        # Act
        detector.save(str(model_path))

        # Assert
        assert model_path.exists()
        assert model_path.stat().st_size > 0

    def test_save_raises_when_no_model(self, tmp_path):
        """Test that save raises when no model."""
        detector = AnomalyDetector(vendor_id="test")
        detector.model = None  # Explicitly set to None

        model_path = tmp_path / "test-model.pkl"

        with pytest.raises(ValueError, match="No model to save"):
            detector.save(str(model_path))

    def test_load_model_restores_state(self, detector, tmp_path):
        """Test that load restores model state."""
        # Arrange - Train and save
        for amount in [100, 105, 98, 110]:
            detector.learn(amount)

        score_before = detector.score(amount=200.0)
        model_path = tmp_path / "test-model.pkl"
        detector.save(str(model_path))

        # Act - Create new detector and load
        new_detector = AnomalyDetector(vendor_id="test-vendor")
        new_detector.load(str(model_path))

        score_after = new_detector.score(amount=200.0)

        # Assert - Scores should be similar
        assert abs(score_before - score_after) < 0.01

    def test_load_raises_on_missing_file(self):
        """Test that load raises on missing file."""
        detector = AnomalyDetector(vendor_id="test")

        with pytest.raises(FileNotFoundError):
            detector.load("/nonexistent/path/model.pkl")


class TestAnomalyDetectorCOS:
    """Tests for model persistence to MinIO/IBM COS."""

    @pytest.mark.asyncio
    async def test_save_to_cos_raises_when_not_configured(self):
        """Test saving to COS raises when not configured."""
        # Arrange
        detector = AnomalyDetector(vendor_id="test-vendor")
        detector.learn(amount=100.0)

        # Clear environment
        with patch.dict("os.environ", {}, clear=True):
            # Act & Assert
            with pytest.raises(COSConfigError):
                await detector.save_to_cos(bucket="test-bucket")

    @pytest.mark.asyncio
    async def test_save_to_cos_with_mocked_client(self):
        """Test saving to COS with mocked client."""
        # Arrange
        detector = AnomalyDetector(vendor_id="test-vendor")
        detector.learn(amount=100.0)

        mock_cos = Mock()
        mock_cos.put_object = Mock()

        with patch.object(detector, "_get_cos_client", return_value=mock_cos):
            # Act
            await detector.save_to_cos(bucket="test-bucket")

            # Assert
            mock_cos.put_object.assert_called_once()
            call_kwargs = mock_cos.put_object.call_args[1]
            assert call_kwargs["Bucket"] == "test-bucket"
            assert "test-vendor" in call_kwargs["Key"]

    @pytest.mark.asyncio
    async def test_load_from_cos_with_mocked_client(self):
        """Test loading from COS with mocked client."""
        # Arrange
        detector = AnomalyDetector(vendor_id="test-vendor")

        # Create a pickled model
        detector.learn(amount=100.0)
        model_bytes = pickle.dumps(detector.model)

        mock_response = {"Body": Mock(read=Mock(return_value=model_bytes))}
        mock_cos = Mock()
        mock_cos.get_object = Mock(return_value=mock_response)

        with patch.object(detector, "_get_cos_client", return_value=mock_cos):
            # Act
            await detector.load_from_cos(bucket="test-bucket")

            # Assert
            mock_cos.get_object.assert_called_once()
            assert detector.model is not None
