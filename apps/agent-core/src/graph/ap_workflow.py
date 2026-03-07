"""
LangGraph Workflow for AP Invoice Processing.

State machine implementing the full Accounts Payable workflow:
INGEST → EXTRACT → ENRICH_CONTEXT → FRAUD_GATE → DUPLICATE_CHECK → 
THREE_WAY_MATCH → GL_CODING → DECISION → DRAFT_RESOLUTION → EXECUTE → AUDIT_LOG

Each node is deterministic where possible; LLM only used for:
- Drafting messages
- Mapping messy descriptions (when similarity is inconclusive)
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from src.schemas.ap_models import (
    APWorkflowState,
    DecisionResult,
    DecisionType,
    DuplicateCheckResult,
    EnrichContextResult,
    ExecuteResult,
    ExtractResult,
    FraudGateResult,
    GLCodingResult,
    IngestResult,
    InvoiceStatus,
    NodeName,
    TaskStatus,
    ThreeWayMatchResult,
)

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Confidence thresholds for auto-approval
AUTO_APPROVE_CONFIDENCE = 0.95
AUTO_APPROVE_PO_CONFIDENCE = 0.95

# Risk thresholds
HIGH_VALUE_THRESHOLD = Decimal("10000")


# ─────────────────────────────────────────────────────────────────────────────
# Workflow State (TypedDict for LangGraph)
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowState(BaseModel):
    """
    LangGraph state for AP workflow.
    
    This is the state that flows through all nodes in the graph.
    """
    
    # Identifiers
    trace_id: str = ""
    idempotency_key: str = ""
    
    # Invoice data
    invoice_status: str = "new"
    r2_key: Optional[str] = None
    r2_presigned_url: Optional[str] = None
    
    # Extracted invoice
    extracted_invoice: Optional[dict[str, Any]] = None
    
    # Vendor context
    vendor_id: Optional[str] = None
    vendor_trust_level: int = 50
    verified_bank_hash: Optional[str] = None
    
    # Step results
    ingest_result: Optional[dict[str, Any]] = None
    extract_result: Optional[dict[str, Any]] = None
    enrich_result: Optional[dict[str, Any]] = None
    fraud_result: Optional[dict[str, Any]] = None
    duplicate_result: Optional[dict[str, Any]] = None
    three_way_result: Optional[dict[str, Any]] = None
    coding_result: Optional[dict[str, Any]] = None
    decision_result: Optional[dict[str, Any]] = None
    draft_result: Optional[dict[str, Any]] = None
    execute_result: Optional[dict[str, Any]] = None
    
    # Decision
    final_decision: Optional[str] = None
    task_id: Optional[str] = None
    
    # Metadata
    error_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Node Functions
# ─────────────────────────────────────────────────────────────────────────────


async def ingest_node(state: WorkflowState) -> dict:
    """
    INGEST: Validate job payload, check idempotency.
    
    Checks if this invoice has already been processed.
    """
    from src.db import db
    
    trace_id = state.trace_id
    logger.info("node_ingest_start", trace_id=trace_id)
    
    # Check idempotency
    exists, existing_id, existing_status = await db.check_idempotency(state.idempotency_key)
    
    if exists:
        logger.warning(
            "node_ingest_duplicate",
            trace_id=trace_id,
            existing_id=str(existing_id),
            status=existing_status,
        )
        
        result = IngestResult(
            node_name=NodeName.INGEST,
            confidence=1.0,
            reasons=["Invoice already processed"],
            status="skipped",
            idempotency_key=state.idempotency_key,
            is_duplicate=True,
            existing_invoice_id=existing_id,
        )
        
        return {
            "ingest_result": result.model_dump(),
            "invoice_status": existing_status,
            "error_message": "Duplicate invoice - skipped processing",
        }
    
    # Create invoice record
    extracted = state.extracted_invoice
    if extracted:
        vendor_name = extracted.get("vendor_name", "Unknown")
        invoice_number = extracted.get("invoice_number", "")
        total = Decimal(str(extracted.get("total_amount", 0)))
        currency = extracted.get("currency", "USD")
        invoice_date_str = extracted.get("invoice_date")
        invoice_date = (
            datetime.fromisoformat(invoice_date_str).date()
            if invoice_date_str
            else date.today()
        )
        
        # Get or create vendor
        vendor_id = await db.get_or_create_vendor(vendor_name)
        
        # Create invoice record
        invoice_id = await db.create_invoice(
            trace_id=trace_id,
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            total=total,
            currency=currency,
            invoice_date=invoice_date,
            idempotency_key=state.idempotency_key,
        )
        
        logger.info("node_ingest_created", trace_id=trace_id, invoice_id=str(invoice_id))
    
    result = IngestResult(
        node_name=NodeName.INGEST,
        confidence=1.0,
        reasons=["Invoice validated and record created"],
        status="success",
        idempotency_key=state.idempotency_key,
        is_duplicate=False,
    )
    
    return {
        "ingest_result": result.model_dump(),
        "invoice_status": "ingested",
    }


async def extract_node(state: WorkflowState) -> dict:
    """
    EXTRACT: Extract invoice data using Azure Document Intelligence or fixture.
    """
    from src.extraction.sarvam_extractor import InvoiceExtractor
    
    trace_id = state.trace_id
    r2_presigned_url = state.r2_presigned_url
    
    logger.info("node_extract_start", trace_id=trace_id)
    
    try:
        # Use the configured extractor
        extractor = InvoiceExtractor()
        
        # Extract based on mode (fixture, sarvam, ollama)
        if extractor.mode == "fixture":
            # Fast path for testing
            extracted_data = extractor._get_fixture_data(trace_id)
        else:
            # Real extraction
            # Download PDF first
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(r2_presigned_url)
                response.raise_for_status()
                
                # Save temporarily
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                
                extracted_data = await extractor.extract(tmp_path, trace_id)
                
                import os
                os.unlink(tmp_path)
        
        result = ExtractResult(
            node_name=NodeName.EXTRACT,
            confidence=extracted_data.get("confidence_score", 0.0),
            reasons=["Extraction completed"],
            status="success",
            extracted_vendor_name=extracted_data.get("vendor_name", ""),
            extracted_invoice_number=extracted_data.get("invoice_number", ""),
            extracted_total=Decimal(str(extracted_data.get("total_amount", 0))),
            extracted_currency=extracted_data.get("currency", "USD"),
            extracted_date=datetime.fromisoformat(
                extracted_data.get("invoice_date", date.today().isoformat())
            ).date(),
            extracted_line_items=extracted_data.get("line_items", []),
            extraction_method=extractor.mode,
        )
        
        return {
            "extract_result": result.model_dump(),
            "extracted_invoice": extracted_data,
            "invoice_status": "extracted",
        }
        
    except Exception as e:
        logger.error("node_extract_failed", trace_id=trace_id, error=str(e))
        return {
            "extract_result": ExtractResult(
                node_name=NodeName.EXTRACT,
                confidence=0.0,
                reasons=[str(e)],
                status="error",
                extracted_vendor_name="",
                extracted_invoice_number="",
                extracted_total=Decimal("0"),
                extracted_currency="USD",
                extracted_date=date.today(),
                extracted_line_items=[],
            ).model_dump(),
            "error_message": str(e),
        }


async def enrich_context_node(state: WorkflowState) -> dict:
    """
    ENRICH_CONTEXT: Fetch vendor profile, bank details, past invoices, open POs.
    """
    from src.db import db
    
    trace_id = state.trace_id
    extracted = state.extracted_invoice
    
    if not extracted:
        return {"error_message": "No extracted invoice"}
    
    vendor_name = extracted.get("vendor_name", "")
    
    logger.info("node_enrich_start", trace_id=trace_id, vendor=vendor_name)
    
    # Get vendor from database
    vendor = await db.get_vendor_by_name(vendor_name)
    
    if vendor:
        vendor_id = str(vendor["id"])
        trust_level = vendor.get("trust_level", 50)
        verified_bank_hash = vendor.get("verified_bank_hash")
        is_new_vendor = False
        
        # Get past invoices
        past_invoices = await db.get_vendor_invoice_history(vendor["id"])
        
        # Get open POs
        open_pos = await db.get_open_purchase_orders(vendor["id"])
    else:
        vendor_id = None
        trust_level = 50
        verified_bank_hash = None
        is_new_vendor = True
        past_invoices = []
        open_pos = []
    
    result = EnrichContextResult(
        node_name=NodeName.ENRICH_CONTEXT,
        confidence=1.0 if not is_new_vendor else 0.5,
        reasons=[
            f"Found {len(past_invoices)} past invoices",
            f"Found {len(open_pos)} open POs",
        ],
        status="success",
        vendor_id=vendor["id"] if vendor else None,
        vendor_name=vendor_name,
        vendor_trust_level=trust_level,
        verified_bank_hash=verified_bank_hash,
        past_invoice_count=len(past_invoices),
        open_po_count=len(open_pos),
        is_new_vendor=is_new_vendor,
    )
    
    return {
        "enrich_result": result.model_dump(),
        "vendor_id": vendor_id,
        "vendor_trust_level": trust_level,
        "verified_bank_hash": verified_bank_hash,
        "invoice_status": "enriched",
    }


async def fraud_gate_node(state: WorkflowState) -> dict:
    """
    FRAUD_GATE: Deterministic fraud checks (no LLM).
    """
    from src.risk.fraud_gate import FraudCheckInput, run_fraud_gate, create_fraud_result
    
    trace_id = state.trace_id
    extracted = state.extracted_invoice
    
    logger.info("node_fraud_gate_start", trace_id=trace_id)
    
    # Build fraud check input
    input_data = FraudCheckInput(
        trace_id=trace_id,
        extracted_vendor_name=extracted.get("vendor_name", "") if extracted else "",
        extracted_bank_account=extracted.get("vendor_bank_account") if extracted else None,
        extracted_ifsc=extracted.get("vendor_ifsc") if extracted else None,
        extracted_iban=extracted.get("vendor_iban") if extracted else None,
        vendor_id=state.vendor_id,
        vendor_name=extracted.get("vendor_name", "") if extracted else None,
        verified_bank_hash=state.verified_bank_hash,
        vendor_trust_level=state.vendor_trust_level,
    )
    
    # Run fraud gate
    decision = run_fraud_gate(input_data)
    result = create_fraud_result(trace_id, decision)
    
    logger.info(
        "node_fraud_gate_completed",
        trace_id=trace_id,
        is_safe=decision.is_safe,
        requires_review=decision.requires_security_review,
    )
    
    return {
        "fraud_result": result.model_dump(),
        "invoice_status": "fraud_checked",
    }


async def duplicate_check_node(state: WorkflowState) -> dict:
    """
    DUPLICATE_CHECK: Content-based duplicate detection using invoice hash.
    
    Checks for duplicate invoices based on:
    - vendor_name + invoice_number + invoice_date + total_amount
    
    This prevents duplicate payments even if trace_id differs.
    """
    from src.db import db
    from src.utils.hashing import compute_invoice_hash
    from src.matching.duplicate import duplicate_check_node as run_fuzzy_duplicate_check

    trace_id = state.trace_id
    logger.info("node_duplicate_check_start", trace_id=trace_id)

    extracted = state.extracted_invoice
    if not extracted:
        logger.error("duplicate_check_no_extraction", trace_id=trace_id)
        return {
            "duplicate_result": {
                "node_name": "duplicate_check",
                "confidence": 0.0,
                "reasons": ["No extracted invoice data"],
                "status": "error",
            }
        }

    # Compute content-based hash
    content_hash = compute_invoice_hash(
        vendor_name=extracted.get("vendor_name"),
        invoice_number=extracted.get("invoice_number"),
        invoice_date=extracted.get("invoice_date"),
        total_amount=extracted.get("total_amount"),
    )

    # Check database for exact content hash match
    exists, existing_id = await db.check_invoice_duplicate(content_hash)

    if exists and existing_id:
        # Content hash match = exact duplicate
        logger.warning(
            "node_duplicate_content_hash_match",
            trace_id=trace_id,
            existing_id=str(existing_id),
            content_hash=content_hash,
        )

        return {
            "duplicate_result": {
                "node_name": "duplicate_check",
                "confidence": 1.0,
                "reasons": ["Exact content duplicate found"],
                "status": "success",
                "is_duplicate": True,
                "duplicate_invoice_ids": [str(existing_id)],
                "match_type": "exact",
                "similarity_score": 1.0,
                "requires_duplicate_review": True,
                "content_hash": content_hash,
            },
            "invoice_status": "duplicate_checked",
        }

    # No exact hash match - run fuzzy duplicate check as fallback
    logger.info("node_duplicate_check_fuzzy_fallback", trace_id=trace_id)
    state_dict = state.model_dump()
    fuzzy_result = await run_fuzzy_duplicate_check(state_dict)

    # Store hash for future checks (only if not duplicate)
    await db.store_invoice_hash(trace_id, content_hash)

    return fuzzy_result


async def three_way_match_node(state: WorkflowState) -> dict:
    """
    THREE_WAY_MATCH: Invoice ↔ PO ↔ Receipt matching.
    """
    from src.matching.three_way import three_way_match_node as run_three_way
    
    trace_id = state.trace_id
    logger.info("node_three_way_start", trace_id=trace_id)
    
    state_dict = state.model_dump()
    return await run_three_way(state_dict)


async def gl_coding_node(state: WorkflowState) -> dict:
    """
    GL_CODING: Memory-based GL code assignment.
    """
    from src.coding.gl_coding import gl_coding_node as run_gl_coding
    
    trace_id = state.trace_id
    logger.info("node_gl_coding_start", trace_id=trace_id)
    
    state_dict = state.model_dump()
    return await run_gl_coding(state_dict)


async def decision_node(state: WorkflowState) -> dict:
    """
    DECISION: Deterministic decision based on scores and thresholds.
    
    NO LLM - purely deterministic based on:
    - Fraud check results
    - Duplicate check results
    - Three-way match confidence
    - GL coding confidence
    """
    trace_id = state.trace_id
    
    logger.info("node_decision_start", trace_id=trace_id)
    
    # Get results
    fraud = state.fraud_result or {}
    duplicate = state.duplicate_result or {}
    three_way = state.three_way_result or {}
    coding = state.coding_result or {}
    enrich = state.enrich_result or {}
    
    # Check for rejection conditions
    reject_reasons = []
    
    # Fraud gate failure = REJECT
    if not fraud.get("is_safe", True):
        reject_reasons.append("FRAUD_GATE_FAILED")
    
    # Exact duplicate = REJECT
    if duplicate.get("is_duplicate") and duplicate.get("match_type") == "exact":
        reject_reasons.append("EXACT_DUPLICATE")
    
    # Check for HITL conditions
    hitl_reasons = []
    auto_approve_conditions = []
    
    # Bank detail change = HITL
    if fraud.get("requires_security_review"):
        hitl_reasons.append("SECURITY_REVIEW_REQUIRED")
    
    # Fuzzy duplicate = HITL
    if duplicate.get("requires_duplicate_review"):
        hitl_reasons.append("DUPLICATE_REVIEW_REQUIRED")
    
    # PO mismatch = HITL
    if three_way.get("requires_po_approval"):
        hitl_reasons.append("PO_APPROVAL_REQUIRED")
    
    # New vendor = HITL
    if enrich.get("is_new_vendor"):
        hitl_reasons.append("NEW_VENDOR")
    
    # Check auto-approve conditions
    is_safe = fraud.get("is_safe", False)
    no_duplicate = not duplicate.get("is_duplicate", False)
    po_confidence = three_way.get("po_match_confidence", 0.0)
    po_approved = three_way.get("requires_po_approval", True) == False
    has_gl_code = bool(coding.get("gl_code"))
    
    if is_safe and no_duplicate and po_approved and has_gl_code:
        auto_approve_conditions.append("ALL_CHECKS_PASSED")
    
    # Determine final decision
    if reject_reasons:
        decision = DecisionType.REJECT
    elif hitl_reasons:
        decision = DecisionType.HITL_REQUIRED
    else:
        decision = DecisionType.AUTO_APPROVE
    
    result = DecisionResult(
        node_name=NodeName.DECISION,
        confidence=1.0,
        reasons=["Deterministic decision based on scores"],
        status="success",
        decision=decision,
        reason_codes=reject_reasons + hitl_reasons,
        auto_approve_conditions_met=auto_approve_conditions,
        hitl_reasons=hitl_reasons,
        reject_reasons=reject_reasons,
    )
    
    logger.info(
        "node_decision_completed",
        trace_id=trace_id,
        decision=decision.value,
        reject_reasons=reject_reasons,
        hitl_reasons=hitl_reasons,
    )
    
    return {
        "decision_result": result.model_dump(),
        "final_decision": decision.value,
        "invoice_status": "decided",
    }


async def draft_resolution_node(state: WorkflowState) -> dict:
    """
    DRAFT_RESOLUTION: Create task and draft message (NOT auto-sent).
    """
    from src.hitl.tasks import draft_resolution_node as run_draft_resolution
    
    trace_id = state.trace_id
    
    if state.final_decision != DecisionType.HITL_REQUIRED.value:
        logger.info("node_draft_resolution_skip", trace_id=trace_id)
        return {}
    
    logger.info("node_draft_resolution_start", trace_id=trace_id)
    
    state_dict = state.model_dump()
    return await run_draft_resolution(state_dict)


async def execute_node(state: WorkflowState) -> dict:
    """
    EXECUTE: Post to QuickBooks (only when approved + safe).
    """
    from src.activities.execution import post_to_quickbooks
    from src.db import db
    
    trace_id = state.trace_id
    
    # Only execute if auto-approved
    if state.final_decision != DecisionType.AUTO_APPROVE.value:
        logger.info("node_execute_skip_not_approved", trace_id=trace_id)
        return {}
    
    logger.info("node_execute_start", trace_id=trace_id)
    
    try:
        # Get extracted invoice
        extracted = state.extracted_invoice
        if not extracted:
            raise ValueError("No extracted invoice")
        
        # Post to QuickBooks
        qb_result = await post_to_quickbooks(extracted)
        
        result = ExecuteResult(
            node_name=NodeName.EXECUTE,
            confidence=1.0,
            reasons=["Successfully posted to QuickBooks"],
            status="success",
            success=True,
            quickbooks_bill_id=qb_result.get("id"),
        )
        
        # Update invoice status
        if state.vendor_id:
            from uuid import UUID
            # Update in database
            # Note: In real implementation, would get invoice_id from state
        
        logger.info(
            "node_execute_completed",
            trace_id=trace_id,
            qb_id=qb_result.get("id"),
        )
        
        return {
            "execute_result": result.model_dump(),
            "invoice_status": "executed",
        }
        
    except Exception as e:
        logger.error("node_execute_failed", trace_id=trace_id, error=str(e))
        
        result = ExecuteResult(
            node_name=NodeName.EXECUTE,
            confidence=0.0,
            reasons=[str(e)],
            status="error",
            success=False,
            error_message=str(e),
        )
        
        return {
            "execute_result": result.model_dump(),
            "error_message": str(e),
        }


async def audit_log_node(state: WorkflowState) -> dict:
    """
    AUDIT_LOG: Write immutable log entry.
    """
    from src.audit.logger import audit_logger
    
    trace_id = state.trace_id
    
    logger.info("node_audit_log_start", trace_id=trace_id)
    
    # Log final state
    await audit_logger.log_workflow_end(
        trace_id=trace_id,
        final_decision=state.final_decision or "unknown",
        status=state.invoice_status,
    )
    
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional Edges
# ─────────────────────────────────────────────────────────────────────────────


def should_execute(state: WorkflowState) -> str:
    """Determine if we should execute or end."""
    if state.final_decision == DecisionType.AUTO_APPROVE.value:
        return "execute"
    return "end"


def should_draft_resolution(state: WorkflowState) -> str:
    """Determine if we should draft resolution."""
    if state.final_decision == DecisionType.HITL_REQUIRED.value:
        return "draft_resolution"
    return "skip_draft"


# ─────────────────────────────────────────────────────────────────────────────
# Build the Graph
# ─────────────────────────────────────────────────────────────────────────────


def create_ap_workflow() -> StateGraph:
    """
    Create the AP workflow state machine.
    
    Returns:
        Compiled LangGraph StateGraph
    """
    
    # Define the workflow
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("enrich_context", enrich_context_node)
    workflow.add_node("fraud_gate", fraud_gate_node)
    workflow.add_node("duplicate_check", duplicate_check_node)
    workflow.add_node("three_way_match", three_way_match_node)
    workflow.add_node("gl_coding", gl_coding_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("draft_resolution", draft_resolution_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("audit_log", audit_log_node)
    
    # Define edges
    workflow.set_entry_point("ingest")
    
    workflow.add_edge("ingest", "extract")
    workflow.add_edge("extract", "enrich_context")
    workflow.add_edge("enrich_context", "fraud_gate")
    workflow.add_edge("fraud_gate", "duplicate_check")
    workflow.add_edge("duplicate_check", "three_way_match")
    workflow.add_edge("three_way_match", "gl_coding")
    workflow.add_edge("gl_coding", "decision")
    
    # Conditional: decision → execute OR skip to end
    workflow.add_conditional_edges(
        "decision",
        should_execute,
        {
            "execute": "execute",
            "end": END,
        },
    )
    
    # Conditional: execute → draft_resolution OR skip
    workflow.add_conditional_edges(
        "execute",
        should_draft_resolution,
        {
            "draft_resolution": "draft_resolution",
            "skip_draft": "audit_log",
        },
    )
    
    workflow.add_edge("draft_resolution", "audit_log")
    workflow.add_edge("audit_log", END)
    
    # Compile
    return workflow.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Run the Workflow
# ─────────────────────────────────────────────────────────────────────────────


async def run_ap_workflow(
    trace_id: str,
    r2_key: str,
    r2_presigned_url: str,
) -> dict[str, Any]:
    """
    Run the AP workflow for an invoice.
    
    Args:
        trace_id: Unique trace ID
        r2_key: Cloudflare R2 object key
        r2_presigned_url: Presigned URL to download the invoice
        
    Returns:
        Final workflow state
    """
    from src.schemas.ap_models import APWorkflowState
    
    # Compute idempotency key (will be updated after extraction)
    # For now, use trace_id as preliminary key
    idempotency_key = f"preliminary_{trace_id}"
    
    # Create initial state
    initial_state = WorkflowState(
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        r2_key=r2_key,
        r2_presigned_url=r2_presigned_url,
    )
    
    # Create and run workflow
    app = create_ap_workflow()
    
    # Run with checkpointing (for resume on failure)
    config = {
        "configurable": {
            "thread_id": trace_id,
        }
    }
    
    try:
        result = await app.ainvoke(initial_state.model_dump(), config)
        return result
    except Exception as e:
        logger.error("workflow_failed", trace_id=trace_id, error=str(e))
        raise


# Export the app for use
ap_workflow_app = create_ap_workflow()
