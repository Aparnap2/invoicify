"""Tests for configuration module."""

import os
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


class TestSettings:
    """Tests for Settings model."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8001
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.extraction_confidence_threshold == 0.8

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = Settings(
            host="127.0.0.1",
            port=9000,
            debug=True,
            log_level="DEBUG",
        )
        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.debug is True
        assert settings.log_level == "DEBUG"

    def test_invalid_log_level(self):
        """Test invalid log level raises error."""
        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")

    def test_log_level_case_insensitive(self):
        """Test log level is case insensitive."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_confidence_threshold_bounds(self):
        """Test confidence threshold bounds."""
        # Valid thresholds
        settings = Settings(extraction_confidence_threshold=0.0)
        assert settings.extraction_confidence_threshold == 0.0

        settings = Settings(extraction_confidence_threshold=1.0)
        assert settings.extraction_confidence_threshold == 1.0

    def test_invalid_confidence_threshold(self):
        """Test invalid confidence threshold raises error."""
        with pytest.raises(ValidationError):
            Settings(extraction_confidence_threshold=1.5)

        with pytest.raises(ValidationError):
            Settings(extraction_confidence_threshold=-0.1)

    def test_is_development_property(self):
        """Test is_development property."""
        settings = Settings(debug=False)
        assert settings.is_development is False

        settings = Settings(debug=True)
        assert settings.is_development is True

    def test_max_retries_bounds(self):
        """Test max retries bounds."""
        settings = Settings(max_retries=0)
        assert settings.max_retries == 0

        settings = Settings(max_retries=5)
        assert settings.max_retries == 5

        with pytest.raises(ValidationError):
            Settings(max_retries=-1)


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_settings(self):
        """Test get_settings returns Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_caches(self):
        """Test get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
