"""
TDD Tests for Switchable Architecture - Factory Pattern
RED Phase: Tests will fail until implementation is complete
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.config.factory import (
    get_database_adapter,
    get_secrets_adapter,
    get_db,
    get_secrets,
)
from src.interfaces import DatabaseAdapter, SecretsAdapter


class TestFactoryGetDatabaseAdapter:
    """Test database adapter factory with TDD."""

    def test_factory_returns_postgres_adapter_in_free_mode(self):
        """RED: Factory should return PostgresAdapter when DB_MODE=free."""
        with patch.dict(
            "os.environ",
            {"DB_MODE": "free", "DATABASE_URL": "postgresql://test"},
            clear=True,
        ):
            adapter = get_database_adapter()

            # Assert it's a DatabaseAdapter
            assert isinstance(adapter, DatabaseAdapter)
            # Assert it's PostgresAdapter
            assert adapter.__class__.__name__ == "PostgresAdapter"

    def test_factory_returns_hyper_protect_in_trial_mode(self):
        """RED: Factory should return HyperProtectAdapter when DB_MODE=trial."""
        with patch.dict(
            "os.environ",
            {
                "DB_MODE": "trial",
                "DATABASE_URL": "postgresql://test",
                "IBM_DB_CERT_PATH": "/certs/client.crt",
            },
            clear=True,
        ):
            adapter = get_database_adapter()

            # Assert it's a DatabaseAdapter
            assert isinstance(adapter, DatabaseAdapter)
            # Assert it's HyperProtectAdapter
            assert adapter.__class__.__name__ == "HyperProtectAdapter"

    def test_factory_defaults_to_free_mode(self):
        """RED: Factory should default to free mode when DB_MODE not set."""
        with patch.dict(
            "os.environ", {"DATABASE_URL": "postgresql://test"}, clear=True
        ):
            adapter = get_database_adapter()
            assert adapter.__class__.__name__ == "PostgresAdapter"

    def test_factory_raises_error_when_database_url_missing(self):
        """RED: Factory should raise error when DATABASE_URL not set."""
        with patch.dict("os.environ", {"DB_MODE": "free"}, clear=True):
            with pytest.raises(ValueError, match="DATABASE_URL"):
                get_database_adapter()


class TestFactoryGetSecretsAdapter:
    """Test secrets adapter factory with TDD."""

    def test_factory_returns_env_adapter_by_default(self):
        """RED: Factory should return EnvSecretsAdapter by default."""
        with patch.dict("os.environ", {}, clear=True):
            adapter = get_secrets_adapter()

            assert isinstance(adapter, SecretsAdapter)
            assert adapter.__class__.__name__ == "EnvSecretsAdapter"

    def test_factory_returns_ibm_adapter_when_configured(self):
        """RED: Factory should return IBMSecretsAdapter when SECRET_PROVIDER=ibm_sm."""
        with patch.dict(
            "os.environ",
            {"SECRET_PROVIDER": "ibm_sm", "IBM_CLOUD_API_KEY": "test-api-key"},
            clear=True,
        ):
            adapter = get_secrets_adapter()

            assert isinstance(adapter, SecretsAdapter)
            assert adapter.__class__.__name__ == "IBMSecretsAdapter"

    def test_factory_raises_error_when_ibm_key_missing(self):
        """RED: Factory should raise error when IBM_CLOUD_API_KEY not set."""
        with patch.dict("os.environ", {"SECRET_PROVIDER": "ibm_sm"}, clear=True):
            with pytest.raises(ValueError, match="IBM_CLOUD_API_KEY"):
                get_secrets_adapter()


class TestFactorySingletonPattern:
    """Test that factory returns singleton instances."""

    def test_get_db_returns_same_instance(self):
        """RED: get_db() should return cached/singleton instance."""
        with patch.dict(
            "os.environ", {"DATABASE_URL": "postgresql://test"}, clear=True
        ):
            # Clear any existing singleton
            if hasattr(get_db, "_instance"):
                delattr(get_db, "_instance")

            db1 = get_db()
            db2 = get_db()

            assert db1 is db2

    def test_get_secrets_returns_same_instance(self):
        """RED: get_secrets() should return cached/singleton instance."""
        # Clear any existing singleton
        if hasattr(get_secrets, "_instance"):
            delattr(get_secrets, "_instance")

        secrets1 = get_secrets()
        secrets2 = get_secrets()

        assert secrets1 is secrets2


class TestAdapterInterfaceCompliance:
    """Test that adapters implement interface correctly."""

    @pytest.mark.asyncio
    async def test_postgres_adapter_implements_all_methods(self):
        """RED: PostgresAdapter should implement all DatabaseAdapter methods."""
        from src.infrastructure.db_postgres import PostgresAdapter

        adapter = PostgresAdapter("postgresql://test")

        # Check all required methods exist
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "save_invoice")
        assert hasattr(adapter, "get_vendor_history")
        assert hasattr(adapter, "update_vendor_trust")
        assert hasattr(adapter, "get_invoice_by_id")
        assert hasattr(adapter, "health_check")

    @pytest.mark.asyncio
    async def test_hyper_protect_adapter_implements_all_methods(self):
        """RED: HyperProtectAdapter should implement all DatabaseAdapter methods."""
        from src.infrastructure.db_ibm_hyper import HyperProtectAdapter

        adapter = HyperProtectAdapter("postgresql://test")

        # Check all required methods exist
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "save_invoice")
        assert hasattr(adapter, "get_vendor_history")
        assert hasattr(adapter, "update_vendor_trust")
        assert hasattr(adapter, "get_invoice_by_id")
        assert hasattr(adapter, "health_check")


class TestSwitchableConfiguration:
    """Test switching between modes via environment variables."""

    def test_can_switch_from_free_to_trial_mode(self):
        """RED: Should be able to switch adapters by changing env var."""
        # Start in free mode
        with patch.dict(
            "os.environ",
            {"DB_MODE": "free", "DATABASE_URL": "postgresql://test"},
            clear=True,
        ):
            adapter_free = get_database_adapter()
            assert adapter_free.__class__.__name__ == "PostgresAdapter"

        # Switch to trial mode
        with patch.dict(
            "os.environ",
            {
                "DB_MODE": "trial",
                "DATABASE_URL": "postgresql://test",
                "IBM_DB_CERT_PATH": "/certs/client.crt",
            },
            clear=True,
        ):
            adapter_trial = get_database_adapter()
            assert adapter_trial.__class__.__name__ == "HyperProtectAdapter"

    def test_mode_is_case_insensitive(self):
        """RED: DB_MODE should be case insensitive."""
        for mode in ["FREE", "Free", "free", "FrEe"]:
            with patch.dict(
                "os.environ",
                {"DB_MODE": mode, "DATABASE_URL": "postgresql://test"},
                clear=True,
            ):
                adapter = get_database_adapter()
                assert adapter.__class__.__name__ == "PostgresAdapter"


class TestLoggingOutput:
    """Test that factory logs mode selection."""

    def test_logs_free_mode_selection(self, caplog):
        """RED: Factory should log when selecting free mode."""
        with patch.dict(
            "os.environ",
            {"DB_MODE": "free", "DATABASE_URL": "postgresql://test"},
            clear=True,
        ):
            with caplog.at_level("INFO"):
                get_database_adapter()

            assert "Free Mode" in caplog.text or "free" in caplog.text.lower()

    def test_logs_trial_mode_selection(self, caplog):
        """RED: Factory should log when selecting trial mode."""
        with patch.dict(
            "os.environ",
            {
                "DB_MODE": "trial",
                "DATABASE_URL": "postgresql://test",
                "IBM_DB_CERT_PATH": "/certs/client.crt",
            },
            clear=True,
        ):
            with caplog.at_level("INFO"):
                get_database_adapter()

            assert (
                "Enterprise" in caplog.text
                or "Trial" in caplog.text
                or "Hyper Protect" in caplog.text
            )
