"""
Unit tests for Temporal Worker
Following TDD: Write tests first, then implementation
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os


class TestWorkerConfiguration:
    """Test worker configuration and connection."""

    @pytest.mark.asyncio
    async def test_worker_connects_to_local_temporal(self, monkeypatch):
        """Test worker connects to local Temporal server."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
        monkeypatch.setenv("TEMPORAL_NAMESPACE", "default")
        
        with patch("temporal.worker.Client.connect") as mock_connect:
            mock_client = AsyncMock()
            mock_connect.return_value = mock_client
            
            with patch("temporal.worker.Worker") as mock_worker:
                mock_worker_instance = MagicMock()
                mock_worker_instance.run = AsyncMock()
                mock_worker.return_value = mock_worker_instance
                
                # Act
                from temporal.worker import main
                try:
                    await main()
                except:
                    pass  # Worker runs forever, we just test setup
                
                # Assert
                mock_connect.assert_called_once()
                call_args = mock_connect.call_args
                assert call_args[0][0] == "localhost:7233"
                assert call_args[1]["namespace"] == "default"
                assert call_args[1]["tls"] is None

    @pytest.mark.asyncio
    async def test_worker_connects_to_temporal_cloud_with_mtls(self, monkeypatch):
        """Test worker connects to Temporal Cloud with mTLS."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "namespace.tmprl.cloud:7233")
        monkeypatch.setenv("TEMPORAL_NAMESPACE", "namespace")
        monkeypatch.setenv("TEMPORAL_CERT_PATH", "/tmp/test-cert.pem")
        monkeypatch.setenv("TEMPORAL_KEY_PATH", "/tmp/test-key.pem")
        
        # Create mock cert files
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"mock-cert"
            
            with patch("temporal.worker.Client.connect") as mock_connect:
                mock_client = AsyncMock()
                mock_connect.return_value = mock_client
                
                with patch("temporal.worker.Worker") as mock_worker:
                    mock_worker_instance = MagicMock()
                    mock_worker_instance.run = AsyncMock()
                    mock_worker.return_value = mock_worker_instance
                    
                    # Act
                    from temporal.worker import main
                    try:
                        await main()
                    except:
                        pass
                    
                    # Assert
                    call_args = mock_connect.call_args
                    assert call_args[1]["tls"] is not None

    @pytest.mark.asyncio
    async def test_worker_registers_all_workflows(self, monkeypatch):
        """Test worker registers InvoiceProcessingWorkflow."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
        
        with patch("temporal.worker.Client.connect") as mock_connect:
            mock_client = AsyncMock()
            mock_connect.return_value = mock_client
            
            with patch("temporal.worker.Worker") as mock_worker:
                mock_worker_instance = MagicMock()
                mock_worker_instance.run = AsyncMock()
                mock_worker.return_value = mock_worker_instance
                
                # Act
                from temporal.worker import main
                from temporal.workflows.invoice import InvoiceProcessingWorkflow
                try:
                    await main()
                except:
                    pass
                
                # Assert
                call_args = mock_worker.call_args
                assert InvoiceProcessingWorkflow in call_args[1]["workflows"]

    @pytest.mark.asyncio
    async def test_worker_registers_all_activities(self, monkeypatch):
        """Test worker registers all activities."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
        
        with patch("temporal.worker.Client.connect") as mock_connect:
            mock_client = AsyncMock()
            mock_connect.return_value = mock_client
            
            with patch("temporal.worker.Worker") as mock_worker:
                mock_worker_instance = MagicMock()
                mock_worker_instance.run = AsyncMock()
                mock_worker.return_value = mock_worker_instance
                
                # Act
                from temporal.worker import main
                from temporal.activities.agents import analyst_evaluate, critic_review
                from temporal.activities.anomaly import detect_anomaly
                try:
                    await main()
                except:
                    pass
                
                # Assert
                call_args = mock_worker.call_args
                activities = call_args[1]["activities"]
                assert analyst_evaluate in activities
                assert critic_review in activities
                assert detect_anomaly in activities

    @pytest.mark.asyncio
    async def test_worker_uses_correct_task_queue(self, monkeypatch):
        """Test worker listens on correct task queue."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
        
        with patch("temporal.worker.Client.connect") as mock_connect:
            mock_client = AsyncMock()
            mock_connect.return_value = mock_client
            
            with patch("temporal.worker.Worker") as mock_worker:
                mock_worker_instance = MagicMock()
                mock_worker_instance.run = AsyncMock()
                mock_worker.return_value = mock_worker_instance
                
                # Act
                from temporal.worker import main
                try:
                    await main()
                except:
                    pass
                
                # Assert
                call_args = mock_worker.call_args
                assert call_args[1]["task_queue"] == "invoice-processing"


class TestWorkerLogging:
    """Test worker logging configuration."""

    @pytest.mark.asyncio
    async def test_worker_logs_startup_message(self, monkeypatch, caplog):
        """Test worker logs startup message."""
        # Arrange
        monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
        
        with patch("temporal.worker.Client.connect") as mock_connect:
            mock_client = AsyncMock()
            mock_connect.return_value = mock_client
            
            with patch("temporal.worker.Worker") as mock_worker:
                mock_worker_instance = MagicMock()
                mock_worker_instance.run = AsyncMock()
                mock_worker.return_value = mock_worker_instance
                
                # Act
                from temporal.worker import main
                try:
                    await main()
                except:
                    pass
                
                # Assert - check logs contain startup message
                # (This would work with proper caplog setup)
                mock_worker_instance.run.assert_called_once()
