"""
Linear invoice processor following "Straight-Line Pipeline with Guardrails" architecture.

This workflow implements a pure linear flow: receive → extract → validate → sync → end
Each node has single responsibility and clear error handling.
No conditional routing - handle errors through separate escalation nodes.

SOLID Principles:
- Single Responsibility: Each node has one purpose
- Open/Closed: Easy to extend with new nodes
- Interface Segregation: Minimal interfaces
- Dependency Inversion: Depend on abstractions
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.states.linear_state import (
    LinearInvoiceState, LinearProcessingStatus,
    create_initial_linear_state, update_state_timestamp,
    add_processing_step, set_error_state
)
from app.services.instructor_extraction_service import InstructorExtractionService
from app.services.storage_service import StorageService
from app.services.validation_engine import ValidationEngine
# from app.services.erp_adapter_service import ERPAdapterService
from app.core.config import settings
from app.core.exceptions import WorkflowException, ExtractionException, ValidationException

logger = logging.getLogger(__name__)


class LinearInvoiceProcessor:
    """
    Linear invoice processor with simplified, straight-line workflow.

    This processor follows a factory-line pattern where each step
    has a single responsibility and clear success/failure paths.
    """

    def __init__(self):
        """Initialize the linear invoice processor."""
        # Initialize services (dependency injection ready)
        self.extraction_service = InstructorExtractionService()
        self.storage_service = StorageService()
        self.validation_engine = ValidationEngine()
        # self.erp_service = ERPAdapterService()
        self.erp_service = None  # Simplified for testing

        # Initialize state persistence
        self.checkpointer = MemorySaver()

        # Build the linear state graph
        self.graph = self._build_linear_graph()
        self.runner = self.graph.compile(checkpointer=self.checkpointer)

    def _build_linear_graph(self) -> StateGraph:
        """
        Build the linear LangGraph state machine.

        Architecture: receive → extract → validate → sync → end
        No conditional routing - pure linear flow with guardrails.
        """
        workflow = StateGraph(LinearInvoiceState)

        # Add linear processing nodes
        workflow.add_node("receive", self._receive_node)
        workflow.add_node("extract", self._extract_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("sync", self._sync_node)
        workflow.add_node("escalate", self._escalate_node)

        # Set entry point
        workflow.set_entry_point("receive")

        # Define linear workflow edges (straight line)
        workflow.add_edge("receive", "extract")
        workflow.add_edge("extract", "validate")
        workflow.add_edge("validate", "sync")
        workflow.add_edge("sync", END)
        workflow.add_edge("escalate", END)

        return workflow

    async def process_invoice(
        self,
        invoice_id: str,
        file_path: str,
        **kwargs
    ) -> LinearInvoiceState:
        """
        Process invoice through linear pipeline.

        Args:
            invoice_id: Unique invoice identifier
            file_path: Path to invoice file
            **kwargs: Additional processing parameters

        Returns:
            Final state after processing
        """
        workflow_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        logger.info(f"Starting linear processing for {invoice_id} (workflow: {workflow_id})")

        # Calculate file hash
        file_hash = kwargs.get("file_hash")
        if not file_hash:
            file_hash = await self._calculate_file_hash(file_path)

        # Initialize linear state
        initial_state = create_initial_linear_state(
            invoice_id=invoice_id,
            file_path=file_path,
            file_hash=file_hash,
            workflow_id=workflow_id,
            export_format=kwargs.get("export_format", "json")
        )

        try:
            # Run the linear workflow
            thread_config = {"configurable": {"thread_id": workflow_id}}
            result = await self.runner.ainvoke(initial_state, config=thread_config)

            # Calculate total processing time
            total_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result["step_timings"]["total_processing"] = total_time

            logger.info(
                f"Linear processing completed for {invoice_id}: {result['status']} "
                f"in {total_time}ms with {len(result['processing_steps'])} steps"
            )

            return result

        except Exception as e:
            logger.error(f"Linear workflow failed for invoice {invoice_id}: {e}")
            return set_error_state(
                initial_state,
                f"Workflow execution failed: {str(e)}",
                {"error_type": type(e).__name__, "workflow_failed": True},
                escalate=True
            )

    async def _receive_node(self, state: LinearInvoiceState) -> LinearInvoiceState:
        """
        Receive and validate input data.

        Single Responsibility: Input validation and file verification
        Guardrails: File existence, size, and hash validation
        """
        start_time = datetime.utcnow()
        logger.info(f"Receiving invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state = update_state_timestamp(state)

            # Validate file existence
            file_path = state["file_path"]
            if not await self.storage_service.file_exists(file_path):
                raise WorkflowException(f"File not found: {file_path}")

            # Get file content for validation
            file_content = await self.storage_service.get_file_content(file_path)
            file_size = len(file_content)

            # Validate file size
            max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            if file_size > max_size_bytes:
                raise WorkflowException(
                    f"File size {file_size} exceeds maximum {settings.MAX_FILE_SIZE_MB}MB"
                )

            # Verify file hash
            calculated_hash = hashlib.sha256(file_content).hexdigest()
            if calculated_hash != state["file_hash"]:
                raise WorkflowException("File hash mismatch - possible corruption")

            # Update state with successful reception
            state.update({
                "status": LinearProcessingStatus.RECEIVED,
                "current_step": "extract"
            })

            # Record step timing
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state = add_processing_step(state, "receive", duration)

            logger.info(f"Successfully received invoice {state['invoice_id']} in {duration}ms")
            return state

        except Exception as e:
            logger.error(f"Receive failed for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Reception failed: {str(e)}")

    async def _extract_node(self, state: LinearInvoiceState) -> LinearInvoiceState:
        """
        Extract structured data using instructor.

        Single Responsibility: Data extraction with LLM
        Guardrails: Confidence validation and error handling
        """
        start_time = datetime.utcnow()
        logger.info(f"Extracting data for invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state = update_state_timestamp(state)

            # Get file content
            file_path = state["file_path"]
            file_content = await self.storage_service.get_file_content(file_path)

            # Extract text content (assume we have a method to extract text from PDF)
            text_content = await self._extract_text_from_pdf(file_content)

            # Perform structured extraction with instructor
            extraction, validation_metadata = await self.extraction_service.extract_with_validation(
                text_content=text_content,
                metadata={"file_path": file_path, "invoice_id": state["invoice_id"]},
                auto_patch=True
            )

            # Validate extraction confidence
            confidence = float(extraction.confidence.overall)
            if confidence < settings.DOCLING_CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"Low extraction confidence {confidence:.3f} for invoice {state['invoice_id']}"
                )

            # Update state with extraction results
            state.update({
                "status": LinearProcessingStatus.EXTRACTED,
                "current_step": "validate",
                "extraction_result": extraction.model_dump(),
                "extraction_confidence": confidence,
                "extraction_metadata": validation_metadata
            })

            # Record step timing
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state = add_processing_step(state, "extract", duration)

            logger.info(
                f"Successfully extracted invoice {state['invoice_id']} "
                f"with confidence {confidence:.3f} in {duration}ms"
            )
            return state

        except ExtractionException as e:
            logger.error(f"Extraction failed for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Extraction failed: {str(e)}")
        except Exception as e:
            logger.error(f"Extraction error for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Extraction error: {str(e)}")

    async def _validate_node(self, state: LinearInvoiceState) -> LinearInvoiceState:
        """
        Validate business logic and mathematical consistency.

        Single Responsibility: Business rule validation
        Guardrails: Mathematical validation and business logic checks
        """
        start_time = datetime.utcnow()
        logger.info(f"Validating invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state = update_state_timestamp(state)

            extraction_result = state.get("extraction_result")
            if not extraction_result:
                raise ValidationException("No extraction result to validate")

            # Convert back to InvoiceExtraction model
            from app.schemas.invoice_extraction import InvoiceExtraction
            extraction = InvoiceExtraction.model_validate(extraction_result)

            # Perform comprehensive validation
            validation_result = await self.extraction_service.comprehensive_validation(extraction)

            # Validate mathematical consistency
            math_issues = await self.extraction_service._validate_mathematics(extraction)

            # Combine all validation results
            all_issues = validation_result["issues"] + math_issues
            validation_passed = len(all_issues) == 0

            # Check for critical issues that require escalation
            critical_issues = [
                issue for issue in all_issues
                if any(keyword in issue.lower() for keyword in [
                    "mathematical inconsistency", "invalid", "missing", "required"
                ])
            ]

            requires_review = len(critical_issues) > 0 or len(all_issues) > 5

            # Update state with validation results
            state.update({
                "status": LinearProcessingStatus.VALIDATED,
                "current_step": "sync",
                "validation_result": validation_result,
                "validation_passed": validation_passed,
                "validation_issues": all_issues,
                "requires_human_review": requires_review,
                "escalation_reason": "Validation issues detected" if requires_review else None,
                "escalation_context": {"validation_issues": all_issues} if requires_review else None
            })

            # Record step timing
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state = add_processing_step(state, "validate", duration)

            logger.info(
                f"Validation completed for invoice {state['invoice_id']}: "
                f"{'PASSED' if validation_passed else 'FAILED'} "
                f"({len(all_issues)} issues) in {duration}ms"
            )
            return state

        except ValidationException as e:
            logger.error(f"Validation failed for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Validation error for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Validation error: {str(e)}")

    async def _sync_node(self, state: LinearInvoiceState) -> LinearInvoiceState:
        """
        Sync validated data to ERP system (simplified for testing).

        Single Responsibility: ERP synchronization
        Guardrails: Data validation and error handling
        """
        start_time = datetime.utcnow()
        logger.info(f"Syncing invoice {state['invoice_id']} to ERP")

        try:
            # Update processing metadata
            state = update_state_timestamp(state)

            extraction_result = state.get("extraction_result")
            if not extraction_result:
                raise WorkflowException("No extraction result to sync")

            # Prepare export payload
            export_format = state.get("export_format", "json")
            export_payload = {
                "invoice_id": state["invoice_id"],
                "workflow_id": state["workflow_id"],
                "extraction_data": extraction_result,
                "validation_passed": state.get("validation_passed", False),
                "validation_issues": state.get("validation_issues", []),
                "processed_at": datetime.utcnow().isoformat(),
                "format": export_format
            }

            # Simulate sync (simplified for testing - replace with actual ERP service)
            validation_passed = state.get("validation_passed", False)
            sync_result = {
                "success": True,
                "sync_method": "simulated",
                "dry_run": not validation_passed,
                "synced_at": datetime.utcnow().isoformat(),
                "message": "Sync completed successfully (simulated)"
            }

            # Update state with sync results
            state.update({
                "status": LinearProcessingStatus.COMPLETED,
                "current_step": "completed",
                "export_payload": export_payload,
                "sync_result": sync_result
            })

            # Record step timing
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state = add_processing_step(state, "sync", duration)

            logger.info(
                f"Sync completed for invoice {state['invoice_id']}: "
                f"{'SUCCESS' if sync_result['success'] else 'DRY_RUN'} in {duration}ms"
            )
            return state

        except Exception as e:
            logger.error(f"Sync failed for invoice {state['invoice_id']}: {e}")
            return set_error_state(state, f"Sync failed: {str(e)}")

    async def _escalate_node(self, state: LinearInvoiceState) -> LinearInvoiceState:
        """
        Handle escalation for human review.

        Single Responsibility: Escalation management
        Guardrails: Context preservation and notification
        """
        start_time = datetime.utcnow()
        logger.info(f"Escalating invoice {state['invoice_id']} for human review")

        try:
            # Update processing metadata
            state = update_state_timestamp(state)

            # Prepare escalation context
            escalation_context = {
                "invoice_id": state["invoice_id"],
                "workflow_id": state["workflow_id"],
                "escalation_reason": state.get("escalation_reason", "Processing error"),
                "error_details": state.get("error_details"),
                "validation_issues": state.get("validation_issues", []),
                "extraction_confidence": state.get("extraction_confidence"),
                "processing_steps": state.get("processing_steps", []),
                "escalated_at": datetime.utcnow().isoformat()
            }

            # Update state with escalation details
            state.update({
                "status": LinearProcessingStatus.ESCALATED,
                "current_step": "escalated",
                "escalation_context": escalation_context
            })

            # Record step timing
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state = add_processing_step(state, "escalate", duration)

            logger.info(f"Successfully escalated invoice {state['invoice_id']} in {duration}ms")
            return state

        except Exception as e:
            logger.error(f"Escalation failed for invoice {state['invoice_id']}: {e}")
            # Even escalation shouldn't fail the workflow
            state["status"] = LinearProcessingStatus.FAILED
            state["current_step"] = "escalation_failed"
            state["error_message"] = f"Escalation failed: {str(e)}"
            return update_state_timestamp(state)

    # Helper methods

    async def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file."""
        file_content = await self.storage_service.get_file_content(file_path)
        return hashlib.sha256(file_content).hexdigest()

    async def _extract_text_from_pdf(self, file_content: bytes) -> str:
        """
        Extract text content from PDF file.

        This is a placeholder - in production, you'd use a proper PDF text extraction
        service like pdfplumber, PyMuPDF, or Docling.
        """
        # For now, return a placeholder
        # In production, integrate with your PDF text extraction service
        logger.warning("Using placeholder text extraction - integrate with proper PDF service")
        return "PDF text content extraction placeholder"

    def get_processing_status(self, invoice_id: str) -> Dict[str, Any]:
        """Get processing status for an invoice."""
        # This would typically query your state persistence
        return {
            "invoice_id": invoice_id,
            "processor": "linear_invoice_processor",
            "architecture": "straight_line_pipeline",
            "supported_nodes": ["receive", "extract", "validate", "sync", "escalate"],
            "error_handling": "escalation_on_failure",
            "state_management": "typeddict_minimal"
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check of all dependent services."""
        health_status = {
            "processor": "linear_invoice_processor",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {}
        }

        try:
            # Check extraction service
            if hasattr(self.extraction_service, 'get_service_status'):
                health_status["services"]["extraction"] = self.extraction_service.get_service_status()
            else:
                health_status["services"]["extraction"] = {"status": "available"}

            # Check storage service
            try:
                # Simple test - try to access storage
                await self.storage_service.get_service_status()
                health_status["services"]["storage"] = {"status": "available"}
            except Exception as e:
                health_status["services"]["storage"] = {"status": "unavailable", "error": str(e)}

            # Check validation engine
            health_status["services"]["validation"] = {"status": "available"}

            # Check ERP service (simplified)
            health_status["services"]["erp"] = {"status": "simulated", "note": "Using simplified sync for testing"}

        except Exception as e:
            health_status["status"] = "degraded"
            health_status["error"] = str(e)

        return health_status