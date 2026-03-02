"""
Human-in-the-Loop (HITL) Task Creation for AP Workflow.

Creates structured resolution packets and draft messages for:
- TASK_SECURITY_REVIEW: Bank detail changes, vendor mismatches
- TASK_DUPLICATE_REVIEW: Potential duplicate invoices
- TASK_PO_OWNER_APPROVAL: PO mismatches, variance issues
- TASK_VENDOR_ONBOARDING: New vendors without history

These tasks are queued for approval - NO AUTO-SEND.
"""

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

import structlog

from src.schemas.ap_models import (
    DecisionType,
    DraftResolutionResult,
    NodeName,
    TaskStatus,
    TaskType,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Resolution Packet Builders
# ─────────────────────────────────────────────────────────────────────────────


def build_security_review_packet(
    trace_id: str,
    fraud_result: dict,
    extracted_invoice: dict,
) -> dict[str, Any]:
    """Build resolution packet for security review."""
    
    risk_flags = fraud_result.get("artifacts", {}).get("risk_flags", [])
    bank_detail_changed = fraud_result.get("bank_detail_changed", False)
    vendor_mismatch = fraud_result.get("vendor_mismatch", False)
    
    packet = {
        "review_type": "SECURITY",
        "trace_id": trace_id,
        "risk_level": "HIGH",
        "flags": risk_flags,
        "issues": [],
        "invoice_summary": {
            "vendor_name": extracted_invoice.get("vendor_name"),
            "invoice_number": extracted_invoice.get("invoice_number"),
            "total_amount": extracted_invoice.get("total_amount"),
            "currency": extracted_invoice.get("currency"),
            "invoice_date": extracted_invoice.get("invoice_date"),
        },
        "bank_details": {
            "extracted_account": extracted_invoice.get("vendor_bank_account"),
            "extracted_ifsc": extracted_invoice.get("vendor_ifsc"),
            "extracted_iban": extracted_invoice.get("vendor_iban"),
        },
        "required_actions": [],
    }
    
    if bank_detail_changed:
        packet["issues"].append({
            "type": "BANK_CHANGE",
            "description": "Bank account details differ from vendor profile",
            "previous_bank": fraud_result.get("artifacts", {}).get("previous_bank_hash", "Unknown")[:8] + "...",
        })
        packet["required_actions"].append("Verify new bank details with vendor")
    
    if vendor_mismatch:
        packet["issues"].append({
            "type": "VENDOR_MISMATCH",
            "description": "Vendor name does not match expected",
            "extracted": extracted_invoice.get("vendor_name"),
            "expected": "Verify from vendor records",
        })
        packet["required_actions"].append("Confirm vendor identity")
    
    return packet


def build_duplicate_review_packet(
    trace_id: str,
    duplicate_result: dict,
    extracted_invoice: dict,
) -> dict[str, Any]:
    """Build resolution packet for duplicate review."""
    
    packet = {
        "review_type": "DUPLICATE",
        "trace_id": trace_id,
        "risk_level": "MEDIUM",
        "match_type": duplicate_result.get("match_type"),
        "similarity_score": duplicate_result.get("similarity_score"),
        "invoice_summary": {
            "vendor_name": extracted_invoice.get("vendor_name"),
            "invoice_number": extracted_invoice.get("invoice_number"),
            "total_amount": extracted_invoice.get("total_amount"),
            "currency": extracted_invoice.get("currency"),
            "invoice_date": extracted_invoice.get("invoice_date"),
        },
        "potential_duplicates": [
            {"invoice_id": str(id), "reason": "Similar to existing invoice"}
            for id in duplicate_result.get("duplicate_invoice_ids", [])
        ],
        "required_actions": [
            "Compare with potential duplicate invoices",
            "Confirm if this is a legitimate new invoice",
        ],
    }
    
    return packet


def build_po_approval_packet(
    trace_id: str,
    three_way_result: dict,
    extracted_invoice: dict,
) -> dict[str, Any]:
    """Build resolution packet for PO owner approval."""
    
    packet = {
        "review_type": "PO_MATCH",
        "trace_id": trace_id,
        "risk_level": "MEDIUM",
        "invoice_summary": {
            "vendor_name": extracted_invoice.get("vendor_name"),
            "invoice_number": extracted_invoice.get("invoice_number"),
            "total_amount": extracted_invoice.get("total_amount"),
            "po_number": extracted_invoice.get("po_number"),
            "currency": extracted_invoice.get("currency"),
        },
        "match_details": {
            "po_number": three_way_result.get("po_number"),
            "po_total": three_way_result.get("po_total"),
            "invoice_total": three_way_result.get("invoice_total"),
            "variance": three_way_result.get("variance"),
            "variance_percentage": three_way_result.get("variance_percentage"),
            "line_item_matches": three_way_result.get("line_item_matches", []),
        },
        "required_actions": [
            "Verify PO line items match invoice",
            f"Approve variance of {three_way_result.get('variance_percentage', 0):.2f}%",
        ],
    }
    
    return packet


def build_vendor_onboarding_packet(
    trace_id: str,
    enrich_result: dict,
    extracted_invoice: dict,
) -> dict[str, Any]:
    """Build resolution packet for new vendor onboarding."""
    
    packet = {
        "review_type": "VENDOR_ONBOARDING",
        "trace_id": trace_id,
        "risk_level": "MEDIUM",
        "invoice_summary": {
            "vendor_name": extracted_invoice.get("vendor_name"),
            "invoice_number": extracted_invoice.get("invoice_number"),
            "total_amount": extracted_invoice.get("total_amount"),
            "currency": extracted_invoice.get("currency"),
        },
        "vendor_details": {
            "address": extracted_invoice.get("vendor_address"),
            "tax_id": extracted_invoice.get("vendor_tax_id"),
        },
        "required_actions": [
            "Verify vendor legitimacy",
            "Set up vendor in accounting system",
            "Verify bank details",
        ],
    }
    
    return packet


# ─────────────────────────────────────────────────────────────────────────────
# Message Drafting (LLM-powered, but NOT auto-sent)
# ─────────────────────────────────────────────────────────────────────────────


def draft_approval_message(
    task_type: TaskType,
    packet: dict[str, Any],
) -> str:
    """
    Draft a message for the approver.
    
    This is queued for review - NOT auto-sent.
    """
    
    if task_type == TaskType.TASK_SECURITY_REVIEW:
        return f"""
AP Security Review Required
===========================

Invoice: {packet.get('invoice_summary', {}).get('invoice_number')}
Vendor: {packet.get('invoice_summary', {}).get('vendor_name')}
Amount: {packet.get('invoice_summary', {}).get('total_amount')} {packet.get('invoice_summary', {}).get('currency')}

Risk Level: {packet.get('risk_level')}

Issues Detected:
{chr(10).join(f"- {issue.get('description')}" for issue in packet.get('issues', []))}

Required Actions:
{chr(10).join(f"- {action}" for action in packet.get('required_actions', []))}

Please review and take action.
"""
    
    elif task_type == TaskType.TASK_DUPLICATE_REVIEW:
        return f"""
AP Duplicate Review Required
=============================

Invoice: {packet.get('invoice_summary', {}).get('invoice_number')}
Vendor: {packet.get('invoice_summary', {}).get('vendor_name')}
Amount: {packet.get('invoice_summary', {}).get('total_amount')} {packet.get('invoice_summary', {}).get('currency')}

Match Type: {packet.get('match_type')}
Similarity: {packet.get('similarity_score', 0):.0%}

Required Actions:
{chr(10).join(f"- {action}" for action in packet.get('required_actions', []))}

Please verify if this is a duplicate.
"""
    
    elif task_type == TaskType.TASK_PO_OWNER_APPROVAL:
        return f"""
AP PO Approval Required
========================

Invoice: {packet.get('invoice_summary', {}).get('invoice_number')}
Vendor: {packet.get('invoice_summary', {}).get('vendor_name')}
Amount: {packet.get('invoice_summary', {}).get('total_amount')} {packet.get('invoice_summary', {}).get('currency')}
PO Number: {packet.get('invoice_summary', {}).get('po_number')}

Variance: {packet.get('match_details', {}).get('variance_percentage', 0):.2f}%

Required Actions:
{chr(10).join(f"- {action}" for action in packet.get('required_actions', []))}

Please approve or reject.
"""
    
    elif task_type == TaskType.TASK_VENDOR_ONBOARDING:
        return f"""
AP Vendor Onboarding Required
===============================

New Vendor Detected: {packet.get('invoice_summary', {}).get('vendor_name')}

Invoice: {packet.get('invoice_summary', {}).get('invoice_number')}
Amount: {packet.get('invoice_summary', {}).get('total_amount')} {packet.get('invoice_summary', {}).get('currency')}

Required Actions:
{chr(10).join(f"- {action}" for action in packet.get('required_actions', []))}

Please onboard this vendor.
"""
    
    return "Please review this invoice."


# ─────────────────────────────────────────────────────────────────────────────
# Task Creation
# ─────────────────────────────────────────────────────────────────────────────


def determine_task_type(
    decision_result: dict,
    fraud_result: Optional[dict],
    duplicate_result: Optional[dict],
    three_way_result: Optional[dict],
    is_new_vendor: bool,
) -> Optional[TaskType]:
    """
    Determine which HITL task type is needed.
    
    Priority (most critical first):
    1. Security review (fraud)
    2. Duplicate review
    3. PO approval
    4. Vendor onboarding
    """
    
    # Security review has highest priority
    if fraud_result and fraud_result.get("requires_security_review"):
        return TaskType.TASK_SECURITY_REVIEW
    
    # Duplicate review
    if duplicate_result and duplicate_result.get("requires_duplicate_review"):
        return TaskType.TASK_DUPLICATE_REVIEW
    
    # PO approval
    if three_way_result and three_way_result.get("requires_po_approval"):
        return TaskType.TASK_PO_OWNER_APPROVAL
    
    # Vendor onboarding
    if is_new_vendor:
        return TaskType.TASK_VENDOR_ONBOARDING
    
    return None


async def create_hitl_task(
    trace_id: str,
    task_type: TaskType,
    payload: dict[str, Any],
    assigned_to: Optional[str] = None,
) -> UUID:
    """Create a human task in the database."""
    from src.db import db
    
    task_id = await db.create_human_task(
        trace_id=trace_id,
        task_type=task_type.value,
        payload_json=payload,
        assigned_to=assigned_to,
    )
    
    logger.info(
        "hitl_task_created",
        trace_id=trace_id,
        task_type=task_type.value,
        task_id=str(task_id),
    )
    
    return task_id


# ─────────────────────────────────────────────────────────────────────────────
# Async Wrapper (for LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def draft_resolution_node(state: dict) -> dict:
    """
    LangGraph node for drafting resolution packets.
    
    Creates tasks and drafts messages for human review.
    NO AUTO-SEND - messages are queued for approval.
    
    Args:
        state: APWorkflowState as dict
        
    Returns:
        Updated state with draft_result and task_id
    """
    trace_id = state.get("trace_id")
    decision_result = state.get("decision_result")
    fraud_result = state.get("fraud_result")
    duplicate_result = state.get("duplicate_result")
    three_way_result = state.get("three_way_result")
    enrich_result = state.get("enrich_result")
    extracted_invoice = state.get("extracted_invoice")
    
    # Check if HITL is required
    if not decision_result:
        logger.error("draft_resolution_no_decision", trace_id=trace_id)
        return {}
    
    if decision_result.get("decision") != DecisionType.HITL_REQUIRED.value:
        logger.info("draft_resolution_not_required", trace_id=trace_id)
        return {}
    
    # Determine task type
    is_new_vendor = enrich_result.get("is_new_vendor", True) if enrich_result else True
    
    task_type = determine_task_type(
        decision_result=decision_result,
        fraud_result=fraud_result,
        duplicate_result=duplicate_result,
        three_way_result=three_way_result,
        is_new_vendor=is_new_vendor,
    )
    
    if not task_type:
        logger.warning("draft_resolution_no_task_type", trace_id=trace_id)
        return {}
    
    # Build resolution packet based on task type
    if task_type == TaskType.TASK_SECURITY_REVIEW:
        packet = build_security_review_packet(trace_id, fraud_result, extracted_invoice)
    elif task_type == TaskType.TASK_DUPLICATE_REVIEW:
        packet = build_duplicate_review_packet(trace_id, duplicate_result, extracted_invoice)
    elif task_type == TaskType.TASK_PO_OWNER_APPROVAL:
        packet = build_po_approval_packet(trace_id, three_way_result, extracted_invoice)
    elif task_type == TaskType.TASK_VENDOR_ONBOARDING:
        packet = build_vendor_onboarding_packet(trace_id, enrich_result, extracted_invoice)
    else:
        packet = {"trace_id": trace_id, "unknown_task_type": True}
    
    # Draft message (NOT auto-sent)
    draft_message = draft_approval_message(task_type, packet)
    
    # Create human task
    task_id = await create_hitl_task(
        trace_id=trace_id,
        task_type=task_type,
        payload=packet,
    )
    
    logger.info(
        "draft_resolution_completed",
        trace_id=trace_id,
        task_type=task_type.value,
        task_id=str(task_id),
    )
    
    # Create result
    result = DraftResolutionResult(
        node_name=NodeName.DRAFT_RESOLUTION,
        confidence=1.0,
        reasons=[f"Created {task_type.value} task"],
        status="success",
        task_type=task_type,
        task_id=task_id,
        resolution_packet=packet,
        draft_message=draft_message,
    )
    
    return {
        "draft_result": result.model_dump(),
        "task_id": task_id,
        "invoice_status": "awaiting_approval",
    }
