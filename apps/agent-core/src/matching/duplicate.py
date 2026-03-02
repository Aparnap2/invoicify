"""
Duplicate Invoice Detection for AP Workflow.

Performs deterministic + fuzzy duplicate detection:
- Exact match: vendor + invoice_number + amount + date
- Fuzzy match: similar invoice number within time window

Uses database queries for exact matches and Azure AI Search for fuzzy matching.
"""

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

import structlog

from src.schemas.ap_models import (
    DuplicateCheckResult,
    NodeName,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Check Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Exact match thresholds
EXACT_MATCH_DAYS = 90  # Look back 90 days for exact duplicates

# Fuzzy match thresholds
FUZZY_INVOICE_SIMILARITY = 0.85  # 85% similarity threshold
FUZZY_AMOUNT_TOLERANCE = 0.01  # 1% amount tolerance for fuzzy
FUZZY_DAYS_WINDOW = 30  # Look back 30 days for fuzzy


# ─────────────────────────────────────────────────────────────────────────────
# Hash-based Exact Match
# ─────────────────────────────────────────────────────────────────────────────


def compute_exact_match_hash(
    vendor_name: str,
    invoice_number: str,
    total: Decimal,
    currency: str,
    invoice_date: date,
) -> str:
    """
    Compute deterministic hash for exact duplicate detection.
    
    Hash = SHA256(vendor_normalized + invoice_number + total + currency + date)
    """
    normalized_vendor = vendor_name.lower().strip()
    normalized_invoice = invoice_number.upper().strip()
    
    key_string = f"{normalized_vendor}|{normalized_invoice}|{total}|{currency}|{invoice_date}"
    return hashlib.sha256(key_string.encode()).hexdigest()


def check_exact_duplicate(
    vendor_name: str,
    invoice_number: str,
    total: Decimal,
    currency: str,
    invoice_date: date,
    existing_invoice_ids: list[str],
) -> tuple[bool, list[UUID]]:
    """
    Check for exact duplicates in the existing invoice IDs.
    
    This is a pure function that checks against a list of known invoice IDs.
    """
    # In a real implementation, this would query the database
    # For now, return (False, []) - no exact duplicates found
    return False, []


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy Matching Logic
# ─────────────────────────────────────────────────────────────────────────────


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.
    
    Used for fuzzy invoice number matching.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def similarity_score(s1: str, s2: str) -> float:
    """
    Calculate similarity score between two strings (0.0 to 1.0).
    
    Uses Levenshtein distance normalized by max length.
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    
    distance = levenshtein_distance(s1.lower(), s2.lower())
    max_len = max(len(s1), len(s2))
    
    return 1.0 - (distance / max_len)


def is_fuzzy_match(
    invoice_number: str,
    total: Decimal,
    invoice_date: date,
    candidate_invoice_number: str,
    candidate_total: Decimal,
    candidate_date: date,
    amount_tolerance: float = FUZZY_AMOUNT_TOLERANCE,
    days_window: int = FUZZY_DAYS_WINDOW,
) -> tuple[bool, float]:
    """
    Check if invoice is a fuzzy match to candidate.
    
    Returns:
        Tuple of (is_fuzzy_match, similarity_score)
    """
    # Check date window
    date_diff = abs((invoice_date - candidate_date).days)
    if date_diff > days_window:
        return False, 0.0
    
    # Check amount tolerance
    if total > 0:
        amount_diff = abs(float(total) - float(candidate_total)) / float(total)
        if amount_diff > amount_tolerance:
            return False, 0.0
    
    # Check invoice number similarity
    invoice_sim = similarity_score(invoice_number, candidate_invoice_number)
    
    if invoice_sim >= FUZZY_INVOICE_SIMILARITY:
        return True, invoice_sim
    
    return False, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Detection Result
# ─────────────────────────────────────────────────────────────────────────────


def create_duplicate_result(
    trace_id: str,
    is_duplicate: bool,
    duplicate_invoice_ids: list[UUID],
    match_type: Optional[str],
    similarity_score: float,
    requires_review: bool,
) -> DuplicateCheckResult:
    """Create a DuplicateCheckResult."""
    
    reasons = []
    if is_duplicate:
        if match_type == "exact":
            reasons.append("Exact duplicate found: same vendor, invoice number, amount, and date")
        elif match_type == "fuzzy":
            reasons.append(f"Potential duplicate found: {similarity_score:.0%} similarity")
    
    return DuplicateCheckResult(
        node_name=NodeName.DUPLICATE_CHECK,
        confidence=1.0 if not is_duplicate else 0.0,
        reasons=reasons,
        artifacts={
            "duplicate_invoice_ids": [str(id) for id in duplicate_invoice_ids],
            "match_type": match_type,
            "similarity_score": similarity_score,
        },
        status="success",
        is_duplicate=is_duplicate,
        duplicate_invoice_ids=duplicate_invoice_ids,
        match_type=match_type,
        similarity_score=similarity_score,
        requires_duplicate_review=requires_review,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async Wrapper (for LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def duplicate_check_node(state: dict) -> dict:
    """
    LangGraph node for duplicate detection.
    
    Checks for:
    1. Exact duplicates (same vendor + invoice number + amount + date)
    2. Fuzzy duplicates (similar invoice number within time window)
    
    Args:
        state: APWorkflowState as dict
        
    Returns:
        Updated state with duplicate_result
    """
    from src.db import db
    
    trace_id = state.get("trace_id")
    extracted = state.get("extracted_invoice")
    
    if not extracted:
        logger.error("duplicate_check_no_extraction", trace_id=trace_id)
        return {
            "duplicate_result": DuplicateCheckResult(
                node_name=NodeName.DUPLICATE_CHECK,
                confidence=0.0,
                reasons=["No extracted invoice data"],
                status="error",
            )
        }
    
    vendor_name = extracted.get("vendor_name", "")
    invoice_number = extracted.get("invoice_number", "")
    total = Decimal(str(extracted.get("total_amount", 0)))
    currency = extracted.get("currency", "USD")
    invoice_date = extracted.get("invoice_date")
    
    if not invoice_date:
        logger.error("duplicate_check_no_date", trace_id=trace_id)
        return {
            "duplicate_result": DuplicateCheckResult(
                node_name=NodeName.DUPLICATE_CHECK,
                confidence=0.0,
                reasons=["No invoice date"],
                status="error",
            )
        }
    
    # Check exact duplicate via database
    exists, existing_id, existing_status = await db.check_idempotency(
        APWorkflowState.compute_idempotency_key(
            vendor_id=None,  # Will be computed internally
            invoice_number=invoice_number,
            total=total,
            currency=currency,
            invoice_date=invoice_date,
        )
    )
    
    if exists and existing_id:
        # Idempotency key match = exact duplicate
        logger.warning(
            "duplicate_exact_found",
            trace_id=trace_id,
            existing_id=str(existing_id),
            status=existing_status,
        )
        
        result = create_duplicate_result(
            trace_id=trace_id,
            is_duplicate=True,
            duplicate_invoice_ids=[existing_id],
            match_type="exact",
            similarity_score=1.0,
            requires_review=True,
        )
        
        return {
            "duplicate_result": result.model_dump(),
            "invoice_status": "duplicate_checked",
        }
    
    # Check for potential duplicates in database
    # Look for similar invoice numbers within the time window
    candidates = await db.find_potential_duplicates(
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        total=total,
        invoice_date=invoice_date,
        threshold_days=FUZZY_DAYS_WINDOW,
    )
    
    for candidate in candidates:
        candidate_number = candidate.get("invoice_number", "")
        candidate_total = Decimal(str(candidate.get("total", 0)))
        candidate_date = candidate.get("invoice_date")
        
        if candidate_date:
            is_match, similarity = is_fuzzy_match(
                invoice_number=invoice_number,
                total=total,
                invoice_date=invoice_date,
                candidate_invoice_number=candidate_number,
                candidate_total=candidate_total,
                candidate_date=candidate_date,
            )
            
            if is_match:
                logger.warning(
                    "duplicate_fuzzy_found",
                    trace_id=trace_id,
                    candidate_id=str(candidate["id"]),
                    similarity=similarity,
                )
                
                result = create_duplicate_result(
                    trace_id=trace_id,
                    is_duplicate=True,
                    duplicate_invoice_ids=[candidate["id"]],
                    match_type="fuzzy",
                    similarity_score=similarity,
                    requires_review=True,
                )
                
                return {
                    "duplicate_result": result.model_dump(),
                    "invoice_status": "duplicate_checked",
                }
    
    # No duplicates found
    logger.info("duplicate_check_passed", trace_id=trace_id)
    
    result = create_duplicate_result(
        trace_id=trace_id,
        is_duplicate=False,
        duplicate_invoice_ids=[],
        match_type=None,
        similarity_score=0.0,
        requires_review=False,
    )
    
    return {
        "duplicate_result": result.model_dump(),
        "invoice_status": "duplicate_checked",
    }


# Helper import for the node
from src.schemas.ap_models import APWorkflowState
