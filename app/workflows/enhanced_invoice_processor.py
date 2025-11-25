"""
Enhanced invoice processor with advanced extraction, validation, and exception management.
Integrates enhanced extraction service, validation engine, and comprehensive workflow orchestration.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict, Union

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.core.exceptions import ExtractionException, ValidationException, WorkflowException
from app.services.enhanced_extraction_service import EnhancedExtractionService
from app.services.validation_engine import ValidationEngine, ReasonTaxonomy
from app.services.llm_patch_service import LLMPatchService
from app.services.storage_service import StorageService
from app.services.exception_service import ExceptionService
from app.services.export_service import ExportService
from app.services.metrics_service import metrics_service
from app.services.vendor_communication_service import VendorCommunicationService
from app.db.session import AsyncSessionLocal
from app.models.invoice import Invoice, InvoiceStatus
# Import models when needed to avoid circular imports
# from app.models.extraction import FieldExtraction, ExtractionSession
# from app.models.validation import ValidationSession

logger = logging.getLogger(__name__)


class EnhancedInvoiceState(TypedDict):
    """Enhanced state for the advanced invoice processing workflow."""

    # Invoice metadata
    invoice_id: str
    file_path: str
    file_hash: str
    vendor_id: Optional[str]
    workflow_id: str
    created_at: str
    updated_at: str

    # Enhanced extraction results
    extraction_result: Optional[Dict[str, Any]]
    extraction_metadata: Optional[Dict[str, Any]]
    field_extractions: List[Dict[str, Any]]
    bbox_coordinates: List[Dict[str, Any]]
    extraction_session_id: Optional[str]

    # Validation results
    validation_result: Optional[Dict[str, Any]]
    validation_session_id: Optional[str]
    validation_issues: List[Dict[str, Any]]
    validation_rules_applied: List[str]

    # Exception management
    exceptions: List[Dict[str, Any]]
    exception_ids: List[str]
    exception_resolution_data: Optional[Dict[str, Any]]

    # Enhanced confidence tracking
    original_confidence: Optional[float]
    enhanced_confidence: Optional[float]
    llm_patched_fields: List[str]
    patch_metadata: Dict[str, Any]

    # Workflow state
    current_step: str
    status: str
    previous_step: Optional[str]
    error_message: Optional[str]
    error_details: Optional[Dict[str, Any]]
    requires_human_review: bool
    retry_count: int
    max_retries: int

    # Processing metadata
    processing_history: List[Dict[str, Any]]
    step_timings: Dict[str, Any]
    performance_metrics: Dict[str, Any]

    # Enhancement tracking
    enhancement_applied: bool
    enhancement_cost: float
    enhancement_time_ms: int

    # Export data
    export_payload: Optional[Dict[str, Any]]
    export_format: str
    export_ready: bool

    # Quality metrics
    completeness_score: Optional[float]
    accuracy_score: Optional[float]
    processing_quality: str  # excellent, good, fair, poor


class EnhancedInvoiceProcessor:
    """Enhanced invoice processor with advanced extraction and validation capabilities."""

    def __init__(self):
        """Initialize the enhanced invoice processor."""
        # Initialize services
        self.enhanced_extraction_service = EnhancedExtractionService()
        self.validation_engine = ValidationEngine()
        self.llm_patch_service = LLMPatchService()
        self.storage_service = StorageService()
        self.exception_service = ExceptionService()
        self.export_service = ExportService()
        self.vendor_communication_service = VendorCommunicationService()

        # Initialize state persistence
        self.checkpointer = MemorySaver()

        # Build the enhanced state graph
        self.graph = self._build_enhanced_graph()
        self.runner = self.graph.compile(checkpointer=self.checkpointer)

    def _build_enhanced_graph(self) -> StateGraph:
        """Build the enhanced LangGraph state machine."""
        workflow = StateGraph(EnhancedInvoiceState)

        # Add enhanced processing nodes
        workflow.add_node("receive", self._enhanced_receive_invoice)
        workflow.add_node("extract", self._enhanced_extract_document)
        workflow.add_node("enhance", self._enhance_extraction)
        workflow.add_node("validate", self._enhanced_validate_invoice)
        workflow.add_node("triage", self._enhanced_triage_results)
        workflow.add_node("stage_export", self._enhanced_stage_export)

        # Add specialized nodes
        workflow.add_node("error_handler", self._enhanced_handle_error)
        workflow.add_node("escalate", self._enhanced_escalate_exception)
        workflow.add_node("quality_check", self._quality_assessment)

        # Set entry point
        workflow.set_entry_point("receive")

        # Define enhanced workflow edges
        workflow.add_edge("receive", "extract")
        workflow.add_edge("extract", "enhance")
        workflow.add_edge("enhance", "validate")
        workflow.add_edge("validate", "quality_check")
        workflow.add_edge("quality_check", "triage")
        workflow.add_edge("stage_export", END)

        # Enhanced conditional routing
        workflow.add_conditional_edges(
            "triage",
            self._enhanced_triage_routing,
            {
                "stage_export": "stage_export",
                "error": "error_handler",
                "escalate": "escalate",
            }
        )

        workflow.add_conditional_edges(
            "error_handler",
            self._enhanced_error_routing,
            {
                "escalate": "escalate",
                "extract": "extract",
                "enhance": "enhance",
                "validate": "validate",
                "fail": END,
            }
        )

        return workflow

    async def process_invoice_enhanced(
        self,
        invoice_id: str,
        file_path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Process invoice with enhanced extraction and validation."""
        workflow_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        logger.info(f"Starting enhanced invoice processing for {invoice_id} (workflow: {workflow_id})")

        # Initialize enhanced state
        initial_state = EnhancedInvoiceState(
            invoice_id=invoice_id,
            file_path=file_path,
            file_hash=kwargs.get("file_hash", ""),
            vendor_id=kwargs.get("vendor_id"),
            workflow_id=workflow_id,
            created_at=start_time.isoformat(),
            updated_at=start_time.isoformat(),
            current_step="initialized",
            status="processing",
            previous_step=None,
            error_message=None,
            error_details=None,
            requires_human_review=False,
            retry_count=0,
            max_retries=kwargs.get("max_retries", 3),
            exceptions=[],
            exception_ids=[],
            exception_resolution_data=None,
            extraction_result=None,
            extraction_metadata=None,
            field_extractions=[],
            bbox_coordinates=[],
            extraction_session_id=None,
            validation_result=None,
            validation_session_id=None,
            validation_issues=[],
            validation_rules_applied=[],
            original_confidence=None,
            enhanced_confidence=None,
            llm_patched_fields=[],
            patch_metadata={},
            processing_history=[],
            step_timings={},
            performance_metrics={},
            enhancement_applied=False,
            enhancement_cost=0.0,
            enhancement_time_ms=0,
            export_payload=None,
            export_format=kwargs.get("export_format", "json"),
            export_ready=False,
            completeness_score=None,
            accuracy_score=None,
            processing_quality="unknown"
        )

        try:
            # Run the enhanced workflow
            thread_config = {"configurable": {"thread_id": workflow_id}}
            result = await self.runner.ainvoke(initial_state, config=thread_config)

            # Calculate comprehensive performance metrics
            total_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result["performance_metrics"] = {
                "total_processing_time_ms": total_time,
                "steps_completed": len(result.get("processing_history", [])),
                "average_step_time_ms": total_time // max(len(result.get("processing_history", [])), 1),
                "enhancement_applied": result.get("enhancement_applied", False),
                "enhancement_cost": result.get("enhancement_cost", 0.0),
                "enhancement_time_ms": result.get("enhancement_time_ms", 0),
                "quality_score": self._calculate_quality_score(result),
                "exceptions_created": len(result.get("exception_ids", []))
            }

            # Log completion
            logger.info(
                f"Enhanced processing completed for {invoice_id}: {result['status']} "
                f"in {total_time}ms with quality {result.get('processing_quality', 'unknown')}"
            )

            # Record comprehensive metrics
            await self._record_enhanced_metrics(invoice_id, result)

            return result

        except Exception as e:
            logger.error(f"Enhanced workflow failed for invoice {invoice_id}: {e}")

            # Update state with workflow failure
            initial_state.update({
                "status": "workflow_failed",
                "error_message": f"Enhanced workflow execution failed: {str(e)}",
                "error_details": {
                    "error_type": type(e).__name__,
                    "step": "workflow_execution",
                    "timestamp": datetime.utcnow().isoformat(),
                    "recovery_possible": False
                },
                "processing_quality": "poor"
            })

            return initial_state

    async def _enhanced_receive_invoice(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced invoice reception with comprehensive validation."""
        start_time = datetime.utcnow()
        logger.info(f"Enhanced receiving invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state["updated_at"] = datetime.utcnow().isoformat()

            # Validate file and extract metadata
            file_path = state["file_path"]
            if not await self.storage_service.file_exists(file_path):
                raise WorkflowException(f"File not found: {file_path}")

            # Get file content and metadata
            file_content = await self.storage_service.get_file_content(file_path)
            file_size = len(file_content)

            # Validate file size
            max_size_mb = settings.MAX_FILE_SIZE_MB
            max_size_bytes = max_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                raise WorkflowException(f"File size {file_size} exceeds maximum {max_size_mb}MB")

            # Calculate file hash if not provided
            if not state.get("file_hash"):
                import hashlib
                state["file_hash"] = hashlib.sha256(file_content).hexdigest()

            # Update state with enhanced reception data
            state.update({
                "current_step": "enhanced_received",
                "status": "processing",
                "previous_step": state.get("current_step"),
                "error_message": None,
                "error_details": None,
                "processing_history": state.get("processing_history", []) + [{
                    "step": "enhanced_receive",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "file_size": file_size,
                        "file_hash": state["file_hash"],
                        "reception_quality": "excellent"
                    }
                }]
            })

            # Update step timings
            step_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state["step_timings"] = state.get("step_timings", {})
            state["step_timings"]["enhanced_receive"] = step_time

            logger.info(f"Successfully enhanced received invoice {state['invoice_id']} in {step_time}ms")
            return state

        except Exception as e:
            logger.error(f"Enhanced receive failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhanced_receive_failed",
                "status": "error",
                "error_message": str(e),
                "error_details": {
                    "error_type": type(e).__name__,
                    "step": "enhanced_receive",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "processing_quality": "poor"
            })
            return state

    async def _enhanced_extract_document(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced document extraction with field-level confidence and bbox tracking."""
        start_time = datetime.utcnow()
        logger.info(f"Enhanced extracting document for invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state["updated_at"] = datetime.utcnow().isoformat()

            # Get file content
            file_path = state["file_path"]
            file_content = await self.storage_service.get_file_content(file_path)

            # Create extraction session
            extraction_session = await self._create_extraction_session(state["invoice_id"])
            state["extraction_session_id"] = str(extraction_session.id)

            # Perform enhanced extraction
            extraction_result = await self.enhanced_extraction_service.extract_with_enhancement(
                file_content=file_content,
                file_path=file_path,
                enable_llm_patching=True
            )

            # Extract detailed metadata
            extraction_metadata = extraction_result.metadata.model_dump()
            confidence_data = extraction_result.confidence.model_dump()

            # Store original confidence
            original_confidence = float(confidence_data.get("overall", 0.0))
            state["original_confidence"] = original_confidence

            # Check if LLM patching was applied
            llm_patched_fields = []
            processing_notes = extraction_result.processing_notes or []
            for note in processing_notes:
                if "LLM patched" in note:
                    llm_patched_fields.append(note)

            state["llm_patched_fields"] = llm_patched_fields
            state["enhancement_applied"] = len(llm_patched_fields) > 0

            # Update state with enhanced extraction results
            state.update({
                "extraction_result": extraction_result.model_dump(),
                "extraction_metadata": extraction_metadata,
                "current_step": "enhanced_extracted",
                "status": "processing",
                "previous_step": state.get("current_step"),
                "enhanced_confidence": original_confidence,
                "completeness_score": float(extraction_metadata.get("completeness_score", 0.0)),
                "accuracy_score": float(extraction_metadata.get("accuracy_score", 0.0)),
                "processing_history": state.get("processing_history", []) + [{
                    "step": "enhanced_extract",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "extraction_confidence": original_confidence,
                        "completeness_score": extraction_metadata.get("completeness_score"),
                        "accuracy_score": extraction_metadata.get("accuracy_score"),
                        "parser_version": extraction_metadata.get("parser_version"),
                        "page_count": extraction_metadata.get("page_count"),
                        "llm_patched_fields": len(llm_patched_fields)
                    }
                }]
            })

            # Update step timings
            step_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state["step_timings"] = state.get("step_timings", {})
            state["step_timings"]["enhanced_extract"] = step_time

            logger.info(
                f"Successfully enhanced extracted invoice {state['invoice_id']} "
                f"with confidence {original_confidence:.3f} in {step_time}ms"
            )
            return state

        except Exception as e:
            logger.error(f"Enhanced extraction failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhanced_extract_failed",
                "status": "error",
                "error_message": str(e),
                "error_details": {
                    "error_type": type(e).__name__,
                    "step": "enhanced_extract",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "processing_quality": "poor"
            })
            return state

    async def _enhance_extraction(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Apply additional enhancement to extraction results."""
        start_time = datetime.utcnow()
        logger.info(f"Enhancing extraction for invoice {state['invoice_id']}")

        try:
            # Check if enhancement is needed
            current_confidence = state.get("enhanced_confidence", 0.0)
            if current_confidence >= settings.DOCLING_CONFIDENCE_THRESHOLD:
                logger.info(f"Confidence {current_confidence:.3f} already above threshold, skipping enhancement")
                state.update({
                    "current_step": "enhancement_skipped",
                    "status": "processing",
                    "enhancement_time_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "processing_history": state.get("processing_history", []) + [{
                        "step": "enhance",
                        "status": "skipped",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                        "metadata": {"reason": "confidence_above_threshold"}
                    }]
                })
                return state

            # Apply additional LLM patching if needed
            extraction_result = state.get("extraction_result", {})
            if extraction_result:
                enhanced_result = await self._apply_additional_enhancement(extraction_result, current_confidence)

                # Calculate improvement
                new_confidence = enhanced_result.get("confidence", {}).get("overall", current_confidence)
                confidence_improvement = new_confidence - current_confidence

                # Update enhancement metadata
                state.update({
                    "extraction_result": enhanced_result,
                    "enhanced_confidence": new_confidence,
                    "enhancement_time_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "enhancement_cost": self._estimate_enhancement_cost(enhanced_result),
                    "current_step": "enhanced",
                    "status": "processing",
                    "previous_step": state.get("current_step"),
                    "processing_history": state.get("processing_history", []) + [{
                        "step": "enhance",
                        "status": "completed",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                        "metadata": {
                            "original_confidence": current_confidence,
                            "new_confidence": new_confidence,
                            "confidence_improvement": confidence_improvement,
                            "enhancement_cost": state.get("enhancement_cost", 0.0)
                        }
                    }]
                })

                logger.info(
                    f"Enhanced extraction confidence from {current_confidence:.3f} to {new_confidence:.3f} "
                    f"(improvement: {confidence_improvement:.3f})"
                )
            else:
                state.update({
                    "current_step": "enhancement_failed",
                    "status": "error",
                    "error_message": "No extraction result to enhance",
                    "processing_quality": "poor"
                })

            return state

        except Exception as e:
            logger.error(f"Enhancement failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhancement_failed",
                "status": "error",
                "error_message": str(e),
                "error_details": {
                    "error_type": type(e).__name__,
                    "step": "enhance",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "processing_quality": "fair"
            })
            return state

    async def _enhanced_validate_invoice(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced validation with comprehensive rule sets."""
        start_time = datetime.utcnow()
        logger.info(f"Enhanced validating invoice {state['invoice_id']}")

        try:
            # Update processing metadata
            state["updated_at"] = datetime.utcnow().isoformat()

            extraction_result = state.get("extraction_result", {})
            if not extraction_result:
                raise ValidationException("No extraction result to validate")

            # Create validation session
            validation_session = await self._create_validation_session(state["invoice_id"])
            state["validation_session_id"] = str(validation_session.id)

            # Perform comprehensive validation
            validation_result = await self.validation_engine.validate_comprehensive(
                extraction_result=extraction_result,
                invoice_id=state["invoice_id"],
                vendor_id=state.get("vendor_id"),
                strict_mode=False  # Can be made configurable
            )

            # Extract validation details
            validation_passed = validation_result.passed
            total_issues = validation_result.total_issues
            error_count = validation_result.error_count
            warning_count = validation_result.warning_count
            confidence_score = validation_result.confidence_score

            # Collect validation issues
            validation_issues = []
            for issue in validation_result.issues:
                validation_issues.append({
                    "code": issue.code.value if hasattr(issue.code, 'value') else str(issue.code),
                    "message": issue.message,
                    "severity": issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity),
                    "field": issue.field,
                    "line_number": issue.line_number,
                    "details": issue.details
                })

            # Get applied rules
            applied_rules = []
            if hasattr(validation_result, 'check_results'):
                check_results = validation_result.check_results.model_dump()
                applied_rules = [rule for rule, passed in check_results.items() if passed]

            # Create exceptions for validation failures
            exception_ids = []
            communication_results = []
            if not validation_passed and error_count > 0:
                try:
                    exceptions = await self.exception_service.create_exception_from_validation(
                        invoice_id=state["invoice_id"],
                        validation_issues=validation_result.issues
                    )
                    exception_ids = [exc.id for exc in exceptions]
                    logger.info(f"Created {len(exception_ids)} exceptions for invoice {state['invoice_id']}")
                except Exception as exc_error:
                    logger.error(f"Failed to create exceptions for invoice {state['invoice_id']}: {exc_error}")

                # Send vendor communication for validation failures
                try:
                    # Prepare validation result for vendor communication
                    validation_result_dict = validation_result.model_dump()

                    # Prepare invoice data from extraction result
                    extraction_result = state.get("extraction_result", {})
                    invoice_data = {
                        "invoice_id": state["invoice_id"],
                        "vendor_name": extraction_result.get("header", {}).get("vendor_name"),
                        "vendor_email": extraction_result.get("header", {}).get("vendor_email"),
                        "invoice_number": extraction_result.get("header", {}).get("invoice_number"),
                        "invoice_date": extraction_result.get("header", {}).get("invoice_date"),
                        "total_amount": extraction_result.get("header", {}).get("total_amount"),
                        "due_date": extraction_result.get("header", {}).get("due_date"),
                        "po_number": extraction_result.get("header", {}).get("po_number")
                    }

                    # Send vendor communication
                    communication_response = await self.vendor_communication_service.handle_validation_failure(
                        validation_result=validation_result_dict,
                        invoice_data=invoice_data
                    )

                    communication_results.append({
                        "success": communication_response.success,
                        "communication_id": communication_response.communication_id,
                        "message": communication_response.error_message if not communication_response.success else "Communication sent successfully"
                    })

                    if communication_response.success:
                        logger.info(f"Vendor communication sent for invoice {state['invoice_id']}: {communication_response.communication_id}")
                    else:
                        logger.warning(f"Failed to send vendor communication for invoice {state['invoice_id']}: {communication_response.error_message}")

                except Exception as comm_error:
                    logger.error(f"Failed to send vendor communication for invoice {state['invoice_id']}: {comm_error}")
                    communication_results.append({
                        "success": False,
                        "communication_id": None,
                        "message": f"Communication failed: {str(comm_error)}"
                    })

            # Update state with validation results
            state.update({
                "validation_result": validation_result.model_dump(),
                "validation_issues": validation_issues,
                "validation_rules_applied": applied_rules,
                "current_step": "enhanced_validated",
                "status": "exception" if not validation_passed else "processing",
                "previous_step": state.get("current_step"),
                "requires_human_review": not validation_passed or error_count > 0,
                "exceptions": validation_issues,
                "exception_ids": state.get("exception_ids", []) + exception_ids,
                "vendor_communications": communication_results,
                "error_message": None if validation_passed else f"Validation failed with {error_count} errors",
                "error_details": None if validation_passed else {
                    "validation_errors": error_count,
                    "validation_warnings": warning_count,
                    "validation_confidence": confidence_score,
                    "communications_sent": len([c for c in communication_results if c["success"]]),
                    "communication_failures": len([c for c in communication_results if not c["success"]])
                },
                "processing_history": state.get("processing_history", []) + [{
                    "step": "enhanced_validate",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "validation_passed": validation_passed,
                        "total_issues": total_issues,
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "validation_confidence": confidence_score,
                        "rules_applied": len(applied_rules),
                        "exceptions_created": len(exception_ids),
                        "vendor_communications_sent": len([c for c in communication_results if c["success"]]),
                        "vendor_communications_failed": len([c for c in communication_results if not c["success"]]),
                        "communication_ids": [c.get("communication_id") for c in communication_results if c.get("communication_id")]
                    }
                }]
            })

            # Update step timings
            step_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            state["step_timings"] = state.get("step_timings", {})
            state["step_timings"]["enhanced_validate"] = step_time

            logger.info(
                f"Enhanced validation completed for invoice {state['invoice_id']}: "
                f"{'PASSED' if validation_passed else 'FAILED'} "
                f"({error_count} errors, {warning_count} warnings) in {step_time}ms"
            )
            return state

        except Exception as e:
            logger.error(f"Enhanced validation failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhanced_validation_failed",
                "status": "error",
                "error_message": str(e),
                "error_details": {
                    "error_type": type(e).__name__,
                    "step": "enhanced_validate",
                    "timestamp": datetime.utcnow().isoformat()
                },
                "processing_quality": "poor"
            })
            return state

    async def _quality_assessment(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Assess overall processing quality."""
        start_time = datetime.utcnow()
        logger.info(f"Assessing quality for invoice {state['invoice_id']}")

        try:
            # Calculate quality metrics
            quality_score = self._calculate_quality_score(state)
            processing_quality = self._determine_quality_level(quality_score)

            # Update state with quality assessment
            state.update({
                "processing_quality": processing_quality,
                "current_step": "quality_assessed",
                "status": "processing",
                "previous_step": state.get("current_step"),
                "processing_history": state.get("processing_history", []) + [{
                    "step": "quality_assessment",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "quality_score": quality_score,
                        "quality_level": processing_quality,
                        "extraction_confidence": state.get("enhanced_confidence", 0.0),
                        "validation_passed": state.get("validation_result", {}).get("passed", False)
                    }
                }]
            })

            logger.info(
                f"Quality assessment completed for invoice {state['invoice_id']}: "
                f"score {quality_score:.3f} ({processing_quality})"
            )
            return state

        except Exception as e:
            logger.error(f"Quality assessment failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "processing_quality": "poor",
                "current_step": "quality_assessment_failed",
                "status": "error",
                "error_message": str(e)
            })
            return state

    async def _enhanced_triage_results(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced triage with intelligent routing based on quality and validation."""
        start_time = datetime.utcnow()
        logger.info(f"Enhanced triaging results for invoice {state['invoice_id']}")

        try:
            # Get key metrics
            validation_result = state.get("validation_result", {})
            quality_score = self._calculate_quality_score(state)
            confidence = state.get("enhanced_confidence", 0.0)
            processing_quality = state.get("processing_quality", "unknown")

            # Determine triage decision
            triage_decision = self._calculate_enhanced_triage_decision(
                validation_passed=validation_result.get("passed", False),
                confidence_score=confidence,
                quality_score=quality_score,
                processing_quality=processing_quality,
                error_count=validation_result.get("error_count", 0),
                exceptions=state.get("validation_issues", [])
            )

            # Determine human review requirements
            human_review_required = self._determine_enhanced_review_requirements(
                triage_decision, validation_result, quality_score, confidence
            )

            # Update state with triage results
            state.update({
                "current_step": "enhanced_triaged",
                "status": self._map_triage_to_status(triage_decision),
                "previous_step": state.get("current_step"),
                "requires_human_review": human_review_required,
                "processing_history": state.get("processing_history", []) + [{
                    "step": "enhanced_triage",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "triage_decision": triage_decision,
                        "quality_score": quality_score,
                        "processing_quality": processing_quality,
                        "human_review_required": human_review_required,
                        "confidence_score": confidence,
                        "validation_errors": validation_result.get("error_count", 0)
                    }
                }]
            })

            logger.info(
                f"Enhanced triage completed for invoice {state['invoice_id']}: "
                f"{triage_decision} (quality: {processing_quality}, review: {'required' if human_review_required else 'not required'})"
            )
            return state

        except Exception as e:
            logger.error(f"Enhanced triage failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhanced_triage_failed",
                "status": "error",
                "error_message": str(e),
                "processing_quality": "poor"
            })
            return state

    async def _enhanced_stage_export(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced export staging with quality metadata."""
        start_time = datetime.utcnow()
        logger.info(f"Enhanced staging export for invoice {state['invoice_id']}")

        try:
            # Prepare enhanced export payload
            extraction_result = state.get("extraction_result", {})
            export_format = state.get("export_format", "json")

            # Create comprehensive export payload
            export_payload = {
                "invoice_id": state["invoice_id"],
                "workflow_id": state["workflow_id"],
                "header": extraction_result.get("header", {}),
                "lines": extraction_result.get("lines", []),
                "confidence": extraction_result.get("confidence", {}),
                "metadata": {
                    "extraction_confidence": state.get("enhanced_confidence", 0.0),
                    "validation_passed": state.get("validation_result", {}).get("passed", False),
                    "processing_quality": state.get("processing_quality", "unknown"),
                    "quality_score": self._calculate_quality_score(state),
                    "processed_at": datetime.utcnow().isoformat(),
                    "export_format": export_format,
                    "export_version": "enhanced-2.0.0",
                    "enhancement_applied": state.get("enhancement_applied", False),
                    "enhancement_cost": state.get("enhancement_cost", 0.0),
                    "extraction_metadata": state.get("extraction_metadata", {}),
                    "validation_metadata": {
                        "rules_applied": state.get("validation_rules_applied", []),
                        "validation_issues": state.get("validation_issues", []),
                        "validation_session_id": state.get("validation_session_id")
                    },
                    "processing_summary": {
                        "total_steps": len(state.get("processing_history", [])),
                        "total_time_ms": sum(
                            step.get("duration_ms", 0) for step in state.get("processing_history", [])
                        ),
                        "step_timings": state.get("step_timings", {}),
                        "exceptions_resolved": len(state.get("exception_ids", []))
                    }
                }
            }

            # Generate export content
            if export_format.lower() == "json":
                export_content = await self.export_service.export_to_json(export_payload)
            elif export_format.lower() == "csv":
                export_content = await self.export_service.export_to_csv(export_payload)
            else:
                # Generate multiple formats
                export_content = {
                    "json": await self.export_service.export_to_json(export_payload),
                    "csv": await self.export_service.export_to_csv(export_payload),
                    "enhanced_json": export_payload  # Include enhanced metadata
                }

            # Update state with export results
            state.update({
                "export_payload": export_payload,
                "export_format": export_format,
                "export_ready": True,
                "current_step": "enhanced_export_staged",
                "status": "staged",
                "previous_step": state.get("current_step"),
                "processing_history": state.get("processing_history", []) + [{
                    "step": "enhanced_stage_export",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "metadata": {
                        "export_format": export_format,
                        "export_size": len(str(export_content)),
                        "export_version": "enhanced-2.0.0",
                        "quality_included": True,
                        "validation_included": True
                    }
                }]
            })

            logger.info(
                f"Successfully enhanced staged export for invoice {state['invoice_id']} "
                f"in {export_format} format with quality metadata"
            )
            return state

        except Exception as e:
            logger.error(f"Enhanced export staging failed for invoice {state['invoice_id']}: {e}")
            state.update({
                "current_step": "enhanced_export_failed",
                "status": "error",
                "error_message": str(e),
                "processing_quality": "poor"
            })
            return state

    # Enhanced routing and helper methods
    def _enhanced_triage_routing(self, state: EnhancedInvoiceState) -> str:
        """Enhanced triage routing based on quality and validation results."""
        status = state.get("status", "")
        processing_quality = state.get("processing_quality", "unknown")
        requires_review = state.get("requires_human_review", False)

        # High quality and passed validation -> auto export
        if (status == "processing" and processing_quality in ["excellent", "good"] and not requires_review):
            return "stage_export"

        # Any validation failures or low quality -> error handling
        if status in ["error", "exception"] or processing_quality in ["poor"]:
            return "error_handler"

        # Default to error handler for safety
        return "error_handler"

    def _enhanced_error_routing(self, state: EnhancedInvoiceState) -> str:
        """Enhanced error routing with intelligent recovery."""
        error_step = state.get("current_step", "")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        processing_quality = state.get("processing_quality", "unknown")

        # If quality is poor, escalate
        if processing_quality == "poor":
            return "escalate"

        # Retry specific steps if within limits
        if retry_count < max_retries:
            if "extract" in error_step or "enhance" in error_step:
                return "extract"
            elif "validate" in error_step:
                return "validate"

        # Escalate if retries exhausted
        return "escalate"

    def _calculate_quality_score(self, state: EnhancedInvoiceState) -> float:
        """Calculate overall quality score."""
        scores = []

        # Extraction confidence (40%)
        extraction_confidence = state.get("enhanced_confidence", 0.0)
        scores.append(("extraction", extraction_confidence, 0.4))

        # Validation results (30%)
        validation_result = state.get("validation_result", {})
        if validation_result:
            validation_passed = 1.0 if validation_result.get("passed", False) else 0.0
            error_penalty = min(validation_result.get("error_count", 0) * 0.1, 0.5)
            validation_score = max(validation_passed - error_penalty, 0.0)
            scores.append(("validation", validation_score, 0.3))

        # Completeness (20%)
        completeness_score = state.get("completeness_score", 0.0)
        scores.append(("completeness", completeness_score, 0.2))

        # Processing smoothness (10%)
        processing_issues = len([h for h in state.get("processing_history", []) if h.get("status") == "failed"])
        smoothness_score = max(1.0 - (processing_issues * 0.2), 0.0)
        scores.append(("smoothness", smoothness_score, 0.1))

        # Calculate weighted score
        total_score = sum(score * weight for name, score, weight in scores)
        return round(total_score, 3)

    def _determine_quality_level(self, quality_score: float) -> str:
        """Determine quality level from score."""
        if quality_score >= 0.9:
            return "excellent"
        elif quality_score >= 0.75:
            return "good"
        elif quality_score >= 0.5:
            return "fair"
        else:
            return "poor"

    def _calculate_enhanced_triage_decision(
        self,
        validation_passed: bool,
        confidence_score: float,
        quality_score: float,
        processing_quality: str,
        error_count: int,
        exceptions: List[Dict[str, Any]]
    ) -> str:
        """Calculate enhanced triage decision."""
        # Excellent quality and passed validation -> auto approve
        if processing_quality == "excellent" and validation_passed and confidence_score >= 0.9:
            return "auto_approve"

        # Good quality with minor issues -> conditional approve
        if processing_quality == "good" and validation_passed and error_count <= 1:
            return "conditional_approve"

        # Fair quality but passed validation -> review required
        if processing_quality == "fair" and validation_passed:
            return "review_required"

        # Any errors or poor quality -> manual review
        if not validation_passed or processing_quality == "poor":
            return "manual_review"

        # Default to review
        return "review_required"

    def _determine_enhanced_review_requirements(
        self,
        triage_decision: str,
        validation_result: Dict[str, Any],
        quality_score: float,
        confidence_score: float
    ) -> bool:
        """Determine if human review is required."""
        auto_review_decisions = ["auto_approve", "conditional_approve"]
        return triage_decision not in auto_review_decisions

    def _map_triage_to_status(self, triage_decision: str) -> str:
        """Map triage decision to workflow status."""
        status_map = {
            "auto_approve": "ready",
            "conditional_approve": "ready",
            "review_required": "review",
            "manual_review": "exception",
        }
        return status_map.get(triage_decision, "exception")

    # Enhanced helper methods
    async def _create_extraction_session(self, invoice_id: str):
        """Create extraction session record."""
        try:
            async with AsyncSessionLocal() as session:
                extraction_session = ExtractionSession(
                    invoice_id=uuid.UUID(invoice_id),
                    extraction_version="enhanced-2.0.0",
                    confidence_threshold=settings.DOCLING_CONFIDENCE_THRESHOLD,
                    llm_patching_enabled=True
                )
                session.add(extraction_session)
                await session.commit()
                await session.refresh(extraction_session)
                return extraction_session
        except Exception as e:
            logger.warning(f"Failed to create extraction session: {e}")
            return None

    async def _create_validation_session(self, invoice_id: str):
        """Create validation session record."""
        try:
            async with AsyncSessionLocal() as session:
                validation_session = ValidationSession(
                    invoice_id=uuid.UUID(invoice_id),
                    rules_version="2.0.0",
                    validator_version="2.0.0",
                    strict_mode=False
                )
                session.add(validation_session)
                await session.commit()
                await session.refresh(validation_session)
                return validation_session
        except Exception as e:
            logger.warning(f"Failed to create validation session: {e}")
            return None

    async def _apply_additional_enhancement(
        self, extraction_result: Dict[str, Any], current_confidence: float
    ) -> Dict[str, Any]:
        """Apply additional enhancement to extraction results."""
        try:
            # Use LLM patch service for additional enhancement
            enhanced_result = await self.llm_patch_service.patch_fields(
                extraction_result, target_fields=None
            )
            return enhanced_result
        except Exception as e:
            logger.warning(f"Additional enhancement failed: {e}")
            return extraction_result

    def _estimate_enhancement_cost(self, extraction_result: Dict[str, Any]) -> float:
        """Estimate enhancement cost."""
        # Simple cost estimation based on complexity
        line_count = len(extraction_result.get("lines", []))
        base_cost = 0.01
        per_line_cost = 0.002
        return base_cost + (line_count * per_line_cost)

    async def _enhanced_handle_error(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced error handling with quality consideration."""
        logger.error(f"Enhanced error handling for invoice {state['invoice_id']}")

        error_details = state.get("error_details", {})
        processing_quality = state.get("processing_quality", "unknown")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)

        # Update error state
        state.update({
            "current_step": "enhanced_error_handled",
            "status": "error",
            "processing_quality": "poor",
            "error_details": {
                **error_details,
                "enhanced_handling": True,
                "processing_quality": processing_quality,
                "retry_count": retry_count
            }
        })

        # Determine routing based on quality and retry count
        if processing_quality == "poor" or retry_count >= max_retries:
            return {**state, "status": "escalate"}
        else:
            return {**state, "status": "retry"}

    async def _enhanced_escalate_exception(self, state: EnhancedInvoiceState) -> EnhancedInvoiceState:
        """Enhanced exception escalation with quality context."""
        logger.error(f"Enhanced escalation for invoice {state['invoice_id']}")

        state.update({
            "current_step": "enhanced_escalated",
            "status": "escalated",
            "processing_quality": "poor",
            "error_message": f"Enhanced escalation after {state.get('retry_count', 0)} retries",
            "processing_history": state.get("processing_history", []) + [{
                "step": "enhanced_escalate",
                "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {
                    "reason": "max_retries_exceeded_or_poor_quality",
                    "retry_count": state.get("retry_count", 0),
                    "processing_quality": state.get("processing_quality", "unknown"),
                    "final_error": state.get("error_message")
                }
            }]
        })

        return state

    async def _record_enhanced_metrics(self, invoice_id: str, result: Dict[str, Any]):
        """Record comprehensive metrics for enhanced processing."""
        try:
            await metrics_service.record_enhanced_invoice_metric(
                invoice_id=invoice_id,
                workflow_data=result,
                extraction_data=result.get("extraction_result"),
                validation_data=result.get("validation_result"),
                quality_metrics={
                    "quality_score": self._calculate_quality_score(result),
                    "processing_quality": result.get("processing_quality", "unknown"),
                    "enhancement_applied": result.get("enhancement_applied", False),
                    "enhancement_cost": result.get("enhancement_cost", 0.0)
                }
            )
            logger.debug(f"Recorded enhanced metrics for invoice {invoice_id}")
        except Exception as e:
            logger.error(f"Failed to record enhanced metrics for invoice {invoice_id}: {e}")