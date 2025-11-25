"""
TDD test suite for linear invoice processor workflow.

This test suite follows Test-Driven Development principles:
1. Write failing tests for each node and state transition
2. Implement minimal functionality to pass tests
3. Refactor for clean code
4. Test state transitions and error handling comprehensively

Tests cover:
- Individual node functionality
- State transitions
- Error handling and escalation
- Integration testing
- Performance and reliability
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.workflows.linear_invoice_processor import LinearInvoiceProcessor
from app.states.linear_state import (
    LinearInvoiceState, LinearProcessingStatus,
    create_initial_linear_state, set_error_state
)
from app.schemas.invoice_extraction import InvoiceExtraction, Vendor, InvoiceHeader, LineItem, ConfidenceScores
from app.core.exceptions import WorkflowException, ExtractionException, ValidationException


class TestLinearInvoiceProcessor:
    """Test suite for LinearInvoiceProcessor."""

    @pytest.fixture
    def processor(self):
        """Create a LinearInvoiceProcessor instance for testing."""
        with patch('app.workflows.linear_invoice_processor.InstructorExtractionService') as mock_extraction:
            with patch('app.workflows.linear_invoice_processor.StorageService') as mock_storage:
                with patch('app.workflows.linear_invoice_processor.ValidationEngine') as mock_validation:
                    with patch('app.workflows.linear_invoice_processor.ERPAdapterService') as mock_erp:

                        # Configure mock services
                        mock_extraction.return_value.extract_with_validation = AsyncMock()
                        mock_storage.return_value.file_exists = AsyncMock(return_value=True)
                        mock_storage.return_value.get_file_content = AsyncMock(return_value=b"mock pdf content")
                        mock_storage.return_value.get_service_status = AsyncMock()

                        processor = LinearInvoiceProcessor()
                        processor.extraction_service = mock_extraction.return_value
                        processor.storage_service = mock_storage.return_value
                        processor.validation_engine = mock_validation.return_value
                        processor.erp_service = mock_erp.return_value

                        yield processor

    @pytest.fixture
    def sample_state(self):
        """Create a sample linear state for testing."""
        return create_initial_linear_state(
            invoice_id=str(uuid.uuid4()),
            file_path="/test/path/invoice.pdf",
            file_hash="abc123",
            workflow_id=str(uuid.uuid4())
        )

    @pytest.fixture
    def mock_extraction_result(self):
        """Create a mock extraction result."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            invoice_number="INV-001",
            total_amount=100.00,
            currency="USD"
        )
        line_item = LineItem(
            description="Test Item",
            quantity=1,
            unit_price=100.00,
            total_amount=100.00
        )
        confidence = ConfidenceScores(overall=0.95)

        extraction = InvoiceExtraction(
            vendor=vendor,
            header=header,
            line_items=[line_item],
            confidence=confidence
        )

        return extraction, {
            "validation": {"is_valid": True, "issues": [], "warnings": [], "issue_count": 0, "warning_count": 0},
            "quality": {"completeness_score": 0.9, "accuracy_score": 0.95},
            "auto_patched": False
        }

    class TestStateManagement:
        """Test state management functions."""

        def test_create_initial_linear_state(self):
            """Test creating initial linear state."""
            invoice_id = str(uuid.uuid4())
            file_path = "/test/path.pdf"
            file_hash = "hash123"
            workflow_id = str(uuid.uuid4())

            state = create_initial_linear_state(
                invoice_id=invoice_id,
                file_path=file_path,
                file_hash=file_hash,
                workflow_id=workflow_id
            )

            assert state["invoice_id"] == invoice_id
            assert state["file_path"] == file_path
            assert state["file_hash"] == file_hash
            assert state["workflow_id"] == workflow_id
            assert state["status"] == LinearProcessingStatus.INITIALIZED
            assert state["current_step"] == "receive"
            assert state["error_message"] is None
            assert state["extraction_result"] is None
            assert state["validation_passed"] is None
            assert not state["requires_human_review"]

        def test_set_error_state(self):
            """Test setting error state."""
            state = create_initial_linear_state(
                invoice_id="test",
                file_path="/test.pdf",
                file_hash="hash",
                workflow_id="workflow"
            )

            error_state = set_error_state(
                state,
                "Test error message",
                {"detail": "error context"},
                escalate=True
            )

            assert error_state["status"] == LinearProcessingStatus.ESCALATED
            assert error_state["current_step"] == "error"
            assert error_state["error_message"] == "Test error message"
            assert error_state["error_details"] == {"detail": "error context"}
            assert error_state["requires_human_review"] is True
            assert error_state["escalation_reason"] == "Test error message"

    class TestReceiveNode:
        """Test the receive node functionality."""

        @pytest.mark.asyncio
        async def test_receive_node_success(self, processor, sample_state):
            """Test successful file reception."""
            # Mock successful file operations
            processor.storage_service.file_exists.return_value = True
            processor.storage_service.get_file_content.return_value = b"mock pdf content"

            # Mock file size validation
            with patch('app.workflows.linear_invoice_processor.settings') as mock_settings:
                mock_settings.MAX_FILE_SIZE_MB = 10

                result = await processor._receive_node(sample_state)

                assert result["status"] == LinearProcessingStatus.RECEIVED
                assert result["current_step"] == "extract"
                assert "receive" in result["processing_steps"]
                assert result["step_timings"]["receive"] > 0
                assert result["error_message"] is None

        @pytest.mark.asyncio
        async def test_receive_node_file_not_found(self, processor, sample_state):
            """Test handling of missing file."""
            processor.storage_service.file_exists.return_value = False

            result = await processor._receive_node(sample_state)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert result["current_step"] == "error"
            assert "File not found" in result["error_message"]
            assert result["requires_human_review"] is False

        @pytest.mark.asyncio
        async def test_receive_node_file_too_large(self, processor, sample_state):
            """Test handling of oversized file."""
            processor.storage_service.file_exists.return_value = True
            processor.storage_service.get_file_content.return_value = b"x" * (11 * 1024 * 1024)  # 11MB

            with patch('app.workflows.linear_invoice_processor.settings') as mock_settings:
                mock_settings.MAX_FILE_SIZE_MB = 10

                result = await processor._receive_node(sample_state)

                assert result["status"] == LinearProcessingStatus.FAILED
                assert "exceeds maximum" in result["error_message"]

    class TestExtractNode:
        """Test the extract node functionality."""

        @pytest.mark.asyncio
        async def test_extract_node_success(self, processor, sample_state, mock_extraction_result):
            """Test successful data extraction."""
            # Set state to received
            sample_state["status"] = LinearProcessingStatus.RECEIVED
            sample_state["current_step"] = "extract"

            # Mock extraction service
            extraction, validation_metadata = mock_extraction_result
            processor.extraction_service.extract_with_validation.return_value = (extraction, validation_metadata)
            processor.storage_service.get_file_content.return_value = b"mock pdf"

            with patch.object(processor, '_extract_text_from_pdf') as mock_extract_text:
                mock_extract_text.return_value = "Sample invoice text"

                result = await processor._extract_node(sample_state)

                assert result["status"] == LinearProcessingStatus.EXTRACTED
                assert result["current_step"] == "validate"
                assert result["extraction_result"] is not None
                assert result["extraction_confidence"] == 0.95
                assert "extract" in result["processing_steps"]
                assert result["error_message"] is None

        @pytest.mark.asyncio
        async def test_extract_node_low_confidence(self, processor, sample_state, mock_extraction_result):
            """Test extraction with low confidence."""
            # Set state to received
            sample_state["status"] = LinearProcessingStatus.RECEIVED
            sample_state["current_step"] = "extract"

            # Mock low confidence extraction
            extraction, validation_metadata = mock_extraction_result
            extraction.confidence.overall = 0.6  # Low confidence
            processor.extraction_service.extract_with_validation.return_value = (extraction, validation_metadata)
            processor.storage_service.get_file_content.return_value = b"mock pdf"

            with patch.object(processor, '_extract_text_from_pdf') as mock_extract_text:
                with patch('app.workflows.linear_invoice_processor.settings') as mock_settings:
                    mock_settings.DOCLING_CONFIDENCE_THRESHOLD = 0.8
                    mock_extract_text.return_value = "Sample invoice text"

                    result = await processor._extract_node(sample_state)

                    assert result["status"] == LinearProcessingStatus.EXTRACTED
                    assert result["extraction_confidence"] == 0.6
                    # Should still succeed, but with warning logged

        @pytest.mark.asyncio
        async def test_extract_node_service_failure(self, processor, sample_state):
            """Test handling of extraction service failure."""
            sample_state["status"] = LinearProcessingStatus.RECEIVED
            sample_state["current_step"] = "extract"

            # Mock service failure
            processor.extraction_service.extract_with_validation.side_effect = ExtractionException("Extraction failed")

            result = await processor._extract_node(sample_state)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert "Extraction failed" in result["error_message"]

    class TestValidateNode:
        """Test the validate node functionality."""

        @pytest.mark.asyncio
        async def test_validate_node_success(self, processor, sample_state, mock_extraction_result):
            """Test successful validation."""
            # Set state with extraction result
            extraction, _ = mock_extraction_result
            sample_state["status"] = LinearProcessingStatus.EXTRACTED
            sample_state["current_step"] = "validate"
            sample_state["extraction_result"] = extraction.model_dump()

            # Mock successful validation
            processor.extraction_service.comprehensive_validation.return_value = {
                "is_valid": True,
                "requires_review": False,
                "issues": [],
                "warnings": [],
                "issue_count": 0,
                "warning_count": 0
            }
            processor.extraction_service._validate_mathematics.return_value = []

            result = await processor._validate_node(sample_state)

            assert result["status"] == LinearProcessingStatus.VALIDATED
            assert result["current_step"] == "sync"
            assert result["validation_passed"] is True
            assert len(result["validation_issues"]) == 0
            assert result["requires_human_review"] is False
            assert "validate" in result["processing_steps"]

        @pytest.mark.asyncio
        async def test_validate_node_with_issues(self, processor, sample_state, mock_extraction_result):
            """Test validation with issues."""
            # Set state with extraction result
            extraction, _ = mock_extraction_result
            sample_state["status"] = LinearProcessingStatus.EXTRACTED
            sample_state["current_step"] = "validate"
            sample_state["extraction_result"] = extraction.model_dump()

            # Mock validation with issues
            processor.extraction_service.comprehensive_validation.return_value = {
                "is_valid": False,
                "requires_review": True,
                "issues": ["Missing required field"],
                "warnings": ["Minor formatting issue"],
                "issue_count": 1,
                "warning_count": 1
            }
            processor.extraction_service._validate_mathematics.return_value = []

            result = await processor._validate_node(sample_state)

            assert result["status"] == LinearProcessingStatus.VALIDATED
            assert result["validation_passed"] is False
            assert len(result["validation_issues"]) == 1
            assert result["requires_human_review"] is True
            assert result["escalation_reason"] is not None

        @pytest.mark.asyncio
        async def test_validate_node_no_extraction_result(self, processor, sample_state):
            """Test validation without extraction result."""
            sample_state["status"] = LinearProcessingStatus.EXTRACTED
            sample_state["current_step"] = "validate"
            sample_state["extraction_result"] = None

            result = await processor._validate_node(sample_state)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert "No extraction result" in result["error_message"]

    class TestSyncNode:
        """Test the sync node functionality."""

        @pytest.mark.asyncio
        async def test_sync_node_success(self, processor, sample_state, mock_extraction_result):
            """Test successful ERP sync."""
            # Set state with validation passed
            extraction, _ = mock_extraction_result
            sample_state["status"] = LinearProcessingStatus.VALIDATED
            sample_state["current_step"] = "sync"
            sample_state["extraction_result"] = extraction.model_dump()
            sample_state["validation_passed"] = True
            sample_state["validation_issues"] = []

            # Mock successful sync
            processor.erp_service.sync_invoice.return_value = {
                "success": True,
                "erp_invoice_id": "ERP-123",
                "synced_at": datetime.utcnow().isoformat()
            }

            result = await processor._sync_node(sample_state)

            assert result["status"] == LinearProcessingStatus.SYNCED
            assert result["current_step"] == "completed"
            assert result["export_payload"] is not None
            assert result["sync_result"]["success"] is True
            assert "sync" in result["processing_steps"]

        @pytest.mark.asyncio
        async def test_sync_node_dry_run(self, processor, sample_state, mock_extraction_result):
            """Test ERP sync with dry run (validation failed)."""
            # Set state with validation failed
            extraction, _ = mock_extraction_result
            sample_state["status"] = LinearProcessingStatus.VALIDATED
            sample_state["current_step"] = "sync"
            sample_state["extraction_result"] = extraction.model_dump()
            sample_state["validation_passed"] = False
            sample_state["validation_issues"] = ["Validation failed"]

            # Mock dry run sync
            processor.erp_service.sync_invoice.return_value = {
                "success": True,
                "dry_run": True,
                "validation_failures": ["Validation failed"]
            }

            result = await processor._sync_node(sample_state)

            assert result["status"] == LinearProcessingStatus.COMPLETED  # Not SYNCED due to dry run
            assert result["export_payload"] is not None
            assert result["sync_result"]["dry_run"] is True

        @pytest.mark.asyncio
        async def test_sync_node_no_extraction_result(self, processor, sample_state):
            """Test sync without extraction result."""
            sample_state["status"] = LinearProcessingStatus.VALIDATED
            sample_state["current_step"] = "sync"
            sample_state["extraction_result"] = None

            result = await processor._sync_node(sample_state)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert "No extraction result" in result["error_message"]

    class TestEscalateNode:
        """Test the escalate node functionality."""

        @pytest.mark.asyncio
        async def test_escalate_node_success(self, processor, sample_state):
            """Test successful escalation."""
            # Set state for escalation
            sample_state["status"] = LinearProcessingStatus.VALIDATED
            sample_state["current_step"] = "escalate"
            sample_state["escalation_reason"] = "Critical validation errors"
            sample_state["validation_issues"] = ["Error 1", "Error 2"]

            result = await processor._escalate_node(sample_state)

            assert result["status"] == LinearProcessingStatus.ESCALATED
            assert result["current_step"] == "escalated"
            assert result["escalation_context"] is not None
            assert result["escalation_context"]["escalation_reason"] == "Critical validation errors"
            assert "escalate" in result["processing_steps"]

        @pytest.mark.asyncio
        async def test_escalate_node_with_error(self, processor, sample_state):
            """Test escalation when even escalation fails."""
            # Mock escalation failure
            with patch.object(processor, '_escalate_node') as mock_escalate:
                mock_escalate.side_effect = Exception("Escalation service down")

                # This would be called from the workflow
                result = await processor._escalate_node(sample_state)

                # Should not fail completely
                assert result["status"] == LinearProcessingStatus.FAILED
                assert result["current_step"] == "escalation_failed"

    class TestIntegration:
        """Integration tests for the complete workflow."""

        @pytest.mark.asyncio
        async def test_successful_full_workflow(self, processor, sample_state, mock_extraction_result):
            """Test complete successful workflow."""
            invoice_id = str(uuid.uuid4())
            file_path = "/test/invoice.pdf"

            # Mock all service calls
            processor.storage_service.file_exists.return_value = True
            processor.storage_service.get_file_content.return_value = b"mock pdf"
            processor._extract_text_from_pdf = AsyncMock(return_value="Invoice text")

            extraction, validation_metadata = mock_extraction_result
            processor.extraction_service.extract_with_validation.return_value = (extraction, validation_metadata)
            processor.extraction_service.comprehensive_validation.return_value = {
                "is_valid": True,
                "requires_review": False,
                "issues": [],
                "warnings": [],
                "issue_count": 0,
                "warning_count": 0
            }
            processor.extraction_service._validate_mathematics.return_value = []
            processor.erp_service.sync_invoice.return_value = {"success": True}

            with patch('app.workflows.linear_invoice_processor.settings') as mock_settings:
                mock_settings.MAX_FILE_SIZE_MB = 10
                mock_settings.DOCLING_CONFIDENCE_THRESHOLD = 0.8

                result = await processor.process_invoice(invoice_id, file_path)

                assert result["status"] in [LinearProcessingStatus.SYNCED, LinearProcessingStatus.COMPLETED]
                assert len(result["processing_steps"]) == 4  # receive, extract, validate, sync
                assert result["validation_passed"] is True
                assert result["requires_human_review"] is False
                assert result["error_message"] is None

        @pytest.mark.asyncio
        async def test_workflow_with_validation_failure(self, processor, sample_state, mock_extraction_result):
            """Test workflow with validation failures leading to human review."""
            invoice_id = str(uuid.uuid4())
            file_path = "/test/invoice.pdf"

            # Mock service calls with validation failure
            processor.storage_service.file_exists.return_value = True
            processor.storage_service.get_file_content.return_value = b"mock pdf"
            processor._extract_text_from_pdf = AsyncMock(return_value="Invoice text")

            extraction, validation_metadata = mock_extraction_result
            processor.extraction_service.extract_with_validation.return_value = (extraction, validation_metadata)
            processor.extraction_service.comprehensive_validation.return_value = {
                "is_valid": False,
                "requires_review": True,
                "issues": ["Critical validation error"],
                "warnings": [],
                "issue_count": 1,
                "warning_count": 0
            }
            processor.extraction_service._validate_mathematics.return_value = ["Math error"]
            processor.erp_service.sync_invoice.return_value = {"success": True, "dry_run": True}

            with patch('app.workflows.linear_invoice_processor.settings') as mock_settings:
                mock_settings.MAX_FILE_SIZE_MB = 10
                mock_settings.DOCLING_CONFIDENCE_THRESHOLD = 0.8

                result = await processor.process_invoice(invoice_id, file_path)

                assert result["status"] in [LinearProcessingStatus.COMPLETED]  # Still completes with dry run
                assert result["validation_passed"] is False
                assert result["requires_human_review"] is True
                assert len(result["validation_issues"]) > 0

    class TestErrorHandling:
        """Test error handling scenarios."""

        @pytest.mark.asyncio
        async def test_workflow_failure_escalation(self, processor):
            """Test workflow failure that escalates."""
            invoice_id = str(uuid.uuid4())
            file_path = "/test/invoice.pdf"

            # Mock file not found
            processor.storage_service.file_exists.return_value = False

            result = await processor.process_invoice(invoice_id, file_path)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert result["error_message"] is not None

        @pytest.mark.asyncio
        async def test_exception_in_workflow(self, processor):
            """Test handling of unexpected exceptions."""
            invoice_id = str(uuid.uuid4())
            file_path = "/test/invoice.pdf"

            # Mock storage service to raise unexpected exception
            processor.storage_service.file_exists.side_effect = Exception("Database connection lost")

            result = await processor.process_invoice(invoice_id, file_path)

            assert result["status"] == LinearProcessingStatus.FAILED
            assert "Workflow execution failed" in result["error_message"]

    class TestPerformance:
        """Test performance and reliability."""

        @pytest.mark.asyncio
        async def test_processing_timing(self, processor, sample_state, mock_extraction_result):
            """Test that processing steps are properly timed."""
            sample_state["status"] = LinearProcessingStatus.RECEIVED
            sample_state["current_step"] = "extract"

            extraction, validation_metadata = mock_extraction_result
            processor.extraction_service.extract_with_validation.return_value = (extraction, validation_metadata)
            processor.storage_service.get_file_content.return_value = b"mock pdf"
            processor._extract_text_from_pdf = AsyncMock(return_value="Sample invoice text")

            start_time = datetime.utcnow()
            result = await processor._extract_node(sample_state)
            end_time = datetime.utcnow()

            # Verify timing was recorded
            assert "extract" in result["processing_steps"]
            assert "extract" in result["step_timings"]
            assert result["step_timings"]["extract"] > 0
            assert result["step_timings"]["extract"] < (end_time - start_time).total_seconds() * 1000 + 100  # Allow some margin

        def test_health_check(self, processor):
            """Test health check functionality."""
            health = asyncio.run(processor.health_check())

            assert health["processor"] == "linear_invoice_processor"
            assert health["status"] in ["healthy", "degraded"]
            assert "services" in health
            assert "timestamp" in health

        def test_processing_status(self, processor):
            """Test processing status functionality."""
            status = processor.get_processing_status("test-invoice-id")

            assert status["invoice_id"] == "test-invoice-id"
            assert status["processor"] == "linear_invoice_processor"
            assert status["architecture"] == "straight_line_pipeline"
            assert "receive" in status["supported_nodes"]


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v", "--tb=short"])