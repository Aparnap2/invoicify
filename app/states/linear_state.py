"""
Linear workflow state definitions for simplified invoice processing.

This module defines minimal state structures following SOLID principles:
- Single Responsibility: State only tracks essential data
- Interface Segregation: Minimal interfaces for each concern
- Dependency Inversion: Depends on abstractions, not concretions
"""

from datetime import datetime
from typing import TypedDict, Optional, Dict, Any, List
from enum import Enum


class LinearProcessingStatus(str, Enum):
    """Linear workflow processing statuses."""

    INITIALIZED = "initialized"
    RECEIVED = "received"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    SYNCED = "synced"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


class LinearInvoiceState(TypedDict):
    """
    Minimal state for linear invoice processing pipeline.

    This state follows the "factory line" pattern with clear,
    sequential transitions and no complex routing logic.

    Attributes:
        Core identification
        Processing status and workflow tracking
        Extraction and validation results
        Error handling and escalation data
        Export and synchronization data
    """

    # Core Identification
    invoice_id: str
    file_path: str
    file_hash: str
    workflow_id: str
    created_at: str
    updated_at: str

    # Processing Status
    status: LinearProcessingStatus
    current_step: str
    error_message: Optional[str]
    error_details: Optional[Dict[str, Any]]

    # Extraction Results
    extraction_result: Optional[Dict[str, Any]]
    extraction_confidence: Optional[float]
    extraction_metadata: Optional[Dict[str, Any]]

    # Validation Results
    validation_result: Optional[Dict[str, Any]]
    validation_passed: Optional[bool]
    validation_issues: List[str]

    # Escalation Data
    requires_human_review: bool
    escalation_reason: Optional[str]
    escalation_context: Optional[Dict[str, Any]]

    # Export Data
    export_payload: Optional[Dict[str, Any]]
    export_format: str
    sync_result: Optional[Dict[str, Any]]

    # Processing Metadata
    processing_steps: List[str]
    step_timings: Dict[str, int]

  

def create_initial_linear_state(
    invoice_id: str,
    file_path: str,
    file_hash: str,
    workflow_id: str,
    **kwargs
) -> LinearInvoiceState:
    """
    Factory function to create initial linear state.

    Args:
        invoice_id: Unique invoice identifier
        file_path: Path to the invoice file
        file_hash: SHA-256 hash of the file
        workflow_id: Unique workflow identifier
        **kwargs: Additional optional parameters

    Returns:
        Initialized LinearInvoiceState
    """
    # Default values for all required fields
    defaults = {
        "status": LinearProcessingStatus.INITIALIZED,
        "current_step": "receive",
        "error_message": None,
        "error_details": None,
        "extraction_result": None,
        "extraction_confidence": None,
        "extraction_metadata": None,
        "validation_result": None,
        "validation_passed": None,
        "validation_issues": [],
        "requires_human_review": False,
        "escalation_reason": None,
        "escalation_context": None,
        "export_payload": None,
        "export_format": "json",
        "sync_result": None,
        "processing_steps": [],
        "step_timings": {}
    }

    # Merge with provided kwargs
    defaults.update(kwargs)

    return LinearInvoiceState(
        invoice_id=invoice_id,
        file_path=file_path,
        file_hash=file_hash,
        workflow_id=workflow_id,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        **defaults
    )


def update_state_timestamp(state: LinearInvoiceState) -> LinearInvoiceState:
    """Update the updated_at timestamp for a state."""
    state["updated_at"] = datetime.utcnow().isoformat()
    return state


def add_processing_step(
    state: LinearInvoiceState,
    step_name: str,
    duration_ms: int
) -> LinearInvoiceState:
    """
    Add a processing step to the state's history.

    Args:
        state: Current linear state
        step_name: Name of the processing step
        duration_ms: Duration in milliseconds

    Returns:
        Updated state with step recorded
    """
    state["processing_steps"].append(step_name)
    state["step_timings"][step_name] = duration_ms
    return update_state_timestamp(state)


def set_error_state(
    state: LinearInvoiceState,
    error_message: str,
    error_details: Optional[Dict[str, Any]] = None,
    escalate: bool = False
) -> LinearInvoiceState:
    """
    Set error state with optional escalation.

    Args:
        state: Current linear state
        error_message: Error message
        error_details: Additional error context
        escalate: Whether to escalate for human review

    Returns:
        Updated state with error information
    """
    state.update({
        "status": LinearProcessingStatus.ESCALATED if escalate else LinearProcessingStatus.FAILED,
        "current_step": "error",
        "error_message": error_message,
        "error_details": error_details,
        "requires_human_review": escalate,
        "escalation_reason": error_message if escalate else None,
        "escalation_context": error_details if escalate else None
    })

    return update_state_timestamp(state)