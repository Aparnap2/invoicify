"""LangGraph workflow for invoice processing."""

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.agents.extractor import get_extractor_agent, InvoiceExtractionResult
from app.config import get_settings
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceExtracted,
    InvoiceStatus,
    POValidationResult,
    DuplicateCheck,
    ApprovalRequest,
    ApprovalAction,
    ApprovalStatus,
    RiskLevel,
    ProcessingResult,
)

logger = logging.getLogger(__name__)


class InvoiceState(TypedDict):
    """State for the invoice processing graph."""

    # Input
    invoice_data: InvoiceCreate
    raw_content: str

    # Processing state
    invoice_id: str
    status: InvoiceStatus
    extracted_data: InvoiceExtracted | None
    raw_text: str

    # Validation results
    po_validation: POValidationResult | None
    duplicate_check: DuplicateCheck | None

    # Approval state
    requires_approval: bool
    approval_request: ApprovalRequest | None
    approval_action: ApprovalAction | None

    # Output
    result: ProcessingResult | None
    error: str | None


def create_invoice_workflow() -> StateGraph:
    """Create the invoice processing workflow graph."""

    builder = StateGraph(InvoiceState)

    # Add nodes
    builder.add_node("extract_fields", extract_fields_node)
    builder.add_node("validate_po", validate_po_node)
    builder.add_node("check_duplicates", check_duplicates_node)
    builder.add_node("decide_escalation", decide_escalation_node)
    builder.add_node("request_approval", request_approval_node)
    builder.add_node("process_approval", process_approval_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_exception", handle_exception_node)

    # Set entry point
    builder.set_entry_point("extract_fields")

    # Flow: extract -> validate -> duplicate -> escalation -> (approval | finalize)
    builder.add_edge("extract_fields", "validate_po")
    builder.add_edge("validate_po", "check_duplicates")
    builder.add_edge("check_duplicates", "decide_escalation")

    # Conditional: based on escalation decision
    builder.add_conditional_edges(
        "decide_escalation",
        should_approve,
        {
            "approve": "request_approval",
            "finalize": "finalize",
            "exception": "handle_exception",
        },
    )

    # Approval flow
    builder.add_edge("request_approval", "process_approval")
    builder.add_edge("process_approval", "finalize")

    # Finalization
    builder.add_edge("finalize", END)
    builder.add_edge("handle_exception", END)

    return builder


def should_approve(state: InvoiceState) -> str:
    """Determine if invoice needs approval."""
    settings = get_settings()

    # Check confidence
    if state.get("extracted_data"):
        confidence = state["extracted_data"].overall_confidence
        if confidence < settings.extraction_confidence_threshold:
            return "exception"

    # Check PO validation
    if state.get("po_validation") and not state["po_validation"].is_valid:
        if not state["po_validation"].is_within_tolerance:
            return "exception"

    # Check duplicates
    if state.get("duplicate_check") and state["duplicate_check"].is_duplicate:
        return "exception"

    # Check amount thresholds for approval
    if state.get("extracted_data"):
        total = float(state["extracted_data"].total_amount)
        if total > 10000:  # High value requires approval
            return "approve"

    return "finalize"


async def extract_fields_node(state: InvoiceState) -> InvoiceState:
    """Extract fields from raw invoice content."""
    logger.info(f"Extracting fields for invoice {state.get('invoice_id')}")

    try:
        extractor = get_extractor_agent()
        result = await extractor.extract_from_text(state["raw_content"])

        if result.success and result.data:
            return {
                **state,
                "status": InvoiceStatus.EXTRACTED,
                "extracted_data": result.data,
                "raw_text": state["raw_content"],
            }
        else:
            return {
                **state,
                "status": InvoiceStatus.EXCEPTION,
                "error": result.error or "Extraction failed",
            }

    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return {
            **state,
            "status": InvoiceStatus.EXCEPTION,
            "error": str(e),
        }


async def validate_po_node(state: InvoiceState) -> InvoiceState:
    """Validate PO matching."""
    logger.info(f"Validating PO for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data to validate"}

    # Simulate PO validation (in production, query database)
    po_number = extracted.po_number

    if po_number:
        # Simulate PO lookup
        validation = POValidationResult(
            is_valid=True,
            po_number=po_number,
            po_amount=extracted.total_amount,
            invoice_amount=extracted.total_amount,
            variance=Decimal("0"),
            variance_percentage=0.0,
        )
    else:
        validation = POValidationResult(
            is_valid=False,
            po_number=None,
            invoice_amount=extracted.total_amount,
            errors=["No PO number provided"],
        )

    return {
        **state,
        "status": InvoiceStatus.VALIDATING,
        "po_validation": validation,
    }


async def check_duplicates_node(state: InvoiceState) -> InvoiceState:
    """Check for duplicate invoices."""
    logger.info(f"Checking duplicates for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data to check"}

    # Simulate duplicate check (in production, query database)
    duplicate_check = DuplicateCheck(
        is_duplicate=False,
        potential_duplicates=[],
        match_fields={
            "vendor": extracted.vendor_name,
            "invoice_number": extracted.invoice_number,
            "amount": str(extracted.total_amount),
        },
    )

    return {
        **state,
        "duplicate_check": duplicate_check,
    }


async def decide_escalation_node(state: InvoiceState) -> InvoiceState:
    """Decide if escalation is needed."""
    logger.info(f"Deciding escalation for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    # Calculate risk level
    total = float(extracted.total_amount)
    if total > 50000:
        risk_level = RiskLevel.CRITICAL
    elif total > 10000:
        risk_level = RiskLevel.HIGH
    elif total > 1000:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW

    decision = should_approve(state)

    return {
        **state,
        "requires_approval": decision == "approve",
        "risk_level": risk_level,
    }


async def request_approval_node(state: InvoiceState) -> InvoiceState:
    """Request human approval with interrupt."""

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    # Create approval request
    approval_request = ApprovalRequest(
        invoice_id=state["invoice_id"],
        reason="Invoice requires approval based on amount or validation",
        risk_level=state.get("risk_level", RiskLevel.MEDIUM),
        suggested_action="Review and approve/reject",
        extracted_data=extracted,
    )

    # Interrupt for human review
    interrupt_data = {
        "action": "invoice_approval",
        "invoice_id": str(approval_request.invoice_id),
        "vendor": extracted.vendor_name,
        "amount": str(extracted.total_amount),
        "currency": extracted.currency,
        "due_date": str(extracted.due_date),
        "po_number": extracted.po_number or "Not provided",
        "risk_level": approval_request.risk_level.value,
        "message": f"Invoice for {extracted.vendor_name} for {extracted.currency} {extracted.total_amount} requires approval",
    }

    # This will pause the graph and return control
    interrupt_result = interrupt(interrupt_data)

    # Process the human response
    if isinstance(interrupt_result, dict):
        action = interrupt_result.get("action", "approve")
        if action == "approve":
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.APPROVED,
                comments=interrupt_result.get("comments"),
                approver_id=interrupt_result.get("approver_id", "unknown"),
                approver_email=interrupt_result.get("approver_email", "unknown"),
            )
        elif action == "reject":
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.REJECTED,
                comments=interrupt_result.get("reason", "Rejected by approver"),
                approver_id=interrupt_result.get("approver_id", "unknown"),
                approver_email=interrupt_result.get("approver_email", "unknown"),
            )
        else:
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.PENDING,
                comments="No action taken",
                approver_id="unknown",
                approver_email="unknown",
            )
    else:
        approval_action = ApprovalAction(
            invoice_id=state["invoice_id"],
            decision=ApprovalStatus.PENDING,
            comments="Invalid response",
            approver_id="unknown",
            approver_email="unknown",
        )

    return {
        **state,
        "status": InvoiceStatus.APPROVAL_PENDING,
        "approval_request": approval_request,
        "approval_action": approval_action,
    }


async def process_approval_node(state: InvoiceState) -> InvoiceState:
    """Process the approval decision."""
    logger.info(f"Processing approval for invoice {state.get('invoice_id')}")

    action = state.get("approval_action")
    if not action:
        return {**state, "error": "No approval action"}

    if action.decision == ApprovalStatus.APPROVED:
        new_status = InvoiceStatus.APPROVED
    elif action.decision == ApprovalStatus.REJECTED:
        new_status = InvoiceStatus.REJECTED
    else:
        new_status = InvoiceStatus.APPROVAL_PENDING

    return {
        **state,
        "status": new_status,
    }


async def finalize_node(state: InvoiceState) -> InvoiceState:
    """Finalize the invoice processing."""
    logger.info(f"Finalizing invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    result = ProcessingResult(
        invoice_id=state["invoice_id"],
        status=state.get("status", InvoiceStatus.EXTRACTED),
        extraction=extracted,
        po_validation=state.get("po_validation"),
        duplicate_check=state.get("duplicate_check"),
        requires_approval=state.get("requires_approval", False),
        approval_request=state.get("approval_request"),
    )

    return {
        **state,
        "status": state.get("status", InvoiceStatus.EXTRACTED),
        "result": result,
    }


async def handle_exception_node(state: InvoiceState) -> InvoiceState:
    """Handle exception case."""
    logger.error(f"Exception for invoice {state.get('invoice_id')}: {state.get('error')}")

    result = ProcessingResult(
        invoice_id=state["invoice_id"],
        status=InvoiceStatus.EXCEPTION,
        extraction=state.get("extracted_data"),
        error_message=state.get("error", "Unknown error"),
        requires_approval=False,
    )

    return {
        **state,
        "status": InvoiceStatus.EXCEPTION,
        "result": result,
    }


class InvoiceWorkflow:
    """Workflow orchestrator for invoice processing."""

    def __init__(self):
        """Initialize the workflow."""
        self.builder = create_invoice_workflow()
        self.checkpointer = MemorySaver()
        self.graph = self.builder.compile(checkpointer=self.checkpointer)

    async def process_invoice(
        self,
        invoice_data: InvoiceCreate,
        raw_content: str,
        thread_id: str | None = None,
    ) -> ProcessingResult:
        """Process an invoice through the workflow."""
        import uuid

        thread_id = thread_id or str(uuid.uuid4())

        initial_state: InvoiceState = {
            "invoice_data": invoice_data,
            "raw_content": raw_content,
            "invoice_id": str(uuid4()),
            "status": InvoiceStatus.NEW,
            "extracted_data": None,
            "raw_text": "",
            "po_validation": None,
            "duplicate_check": None,
            "requires_approval": False,
            "approval_request": None,
            "approval_action": None,
            "result": None,
            "error": None,
        }

        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await self.graph.ainvoke(initial_state, config=config)
            return result.get("result") or ProcessingResult(
                invoice_id=initial_state["invoice_id"],
                status=InvoiceStatus.EXCEPTION,
                extraction=None,
                requires_approval=False,
                error_message=result.get("error", "Unknown error"),
            )
        except Exception as e:
            logger.error(f"Workflow error: {e}")
            return ProcessingResult(
                invoice_id=initial_state["invoice_id"],
                status=InvoiceStatus.EXCEPTION,
                extraction=None,
                requires_approval=False,
                error_message=str(e),
            )

    async def resume_with_approval(
        self,
        thread_id: str,
        decision: dict,
    ) -> ProcessingResult:
        """Resume workflow after human approval."""
        config = {"configurable": {"thread_id": thread_id}}

        command = Command(resume=decision)
        result = await self.graph.ainvoke(command, config=config)

        return result.get("result")


# Singleton workflow instance
_workflow: InvoiceWorkflow | None = None


def get_invoice_workflow() -> InvoiceWorkflow:
    """Get the singleton workflow instance."""
    global _workflow
    if _workflow is None:
        _workflow = InvoiceWorkflow()
    return _workflow
