"""
Deterministic Fraud Gate for AP Workflow.

Performs deterministic fraud checks WITHOUT using LLMs:
- Bank detail change detection
- Vendor mismatch detection
- IFSC/IBAN validation
- Account number pattern validation

This is a HARD security gate - any failure requires human review.
"""

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import structlog

from src.schemas.ap_models import (
    FraudGateResult,
    NodeName,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Bank Detail Hashing
# ─────────────────────────────────────────────────────────────────────────────


def hash_bank_details(
    account_number: Optional[str] = None,
    ifsc_code: Optional[str] = None,
    iban: Optional[str] = None,
) -> str:
    """
    Create a deterministic hash of bank details.
    
    Normalizes the input before hashing for consistent matching.
    """
    parts = []
    
    if account_number:
        # Normalize: remove spaces, dashes, keep only digits
        normalized = re.sub(r"[^0-9]", "", account_number)
        parts.append(f"acc:{normalized}")
    
    if ifsc_code:
        # Normalize: uppercase, remove spaces
        normalized = re.sub(r"[^A-Z0-9]", "", ifsc_code.upper())
        parts.append(f"ifsc:{normalized}")
    
    if iban:
        # Normalize: uppercase, remove spaces
        normalized = re.sub(r"[^A-Z0-9]", "", iban.upper())
        parts.append(f"iban:{normalized}")
    
    if not parts:
        return ""
    
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def extract_account_from_text(text: str) -> Optional[str]:
    """
    Extract potential account number from invoice text.
    
    Looks for:
    - Indian account numbers (8-18 digits)
    - Patterns like "Account No: XXXXXX"
    """
    # Pattern: Account No/Number followed by digits
    patterns = [
        r"(?:account|acct|a\/c|no|number|#)[:.\s]*(\d{8,18})",
        r"\b\d{8,18}\b",  # Standalone 8-18 digit number
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    
    return None


def extract_ifsc_from_text(text: str) -> Optional[str]:
    """
    Extract IFSC code from invoice text.
    
    Indian IFSC format: 4 letters + 0 + 6 alphanumeric
    """
    pattern = r"\b[A-Z]{4}0[A-Z0-9]{6}\b"
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return None


def extract_iban_from_text(text: str) -> Optional[str]:
    """
    Extract IBAN from invoice text.
    
    IBAN format: 2 letters + 2 digits + up to 30 alphanumeric
    """
    # Masked IBAN pattern (after PII redaction)
    if "[REDACTED_IBAN]" in text:
        return "[REDACTED_IBAN]"
    
    pattern = r"\b[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{4}){4}(?:[ ]?[A-Z0-9]{1,2})?\b"
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Validation Functions
# ─────────────────────────────────────────────────────────────────────────────


def validate_ifsc_format(ifsc: str) -> bool:
    """Validate IFSC code format."""
    if not ifsc:
        return True  # No IFSC is OK
    
    pattern = r"^[A-Z]{4}0[A-Z0-9]{6}$"
    return bool(re.match(pattern, ifsc.upper()))


def validate_iban_format(iban: str) -> bool:
    """Validate IBAN format."""
    if not iban:
        return True  # No IBAN is OK
    
    if iban == "[REDACTED_IBAN]":
        return True
    
    # Remove spaces and check format
    cleaned = re.sub(r"[^A-Z0-9]", "", iban.upper())
    if len(cleaned) < 15 or len(cleaned) > 34:
        return False
    
    # Check country code and check digits
    return bool(re.match(r"^[A-Z]{2}[0-9]{2}", cleaned))


def validate_account_number(account: str) -> bool:
    """Validate account number format."""
    if not account:
        return True  # No account is OK
    
    if account == "[REDACTED_ACCOUNT]":
        return True
    
    # Should be 8-18 digits
    cleaned = re.sub(r"[^0-9]", "", account)
    return 8 <= len(cleaned) <= 18


# ─────────────────────────────────────────────────────────────────────────────
# Fraud Gate Logic
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FraudCheckInput:
    """Input for fraud gate checks."""
    
    trace_id: str
    extracted_vendor_name: str
    extracted_bank_account: Optional[str] = None
    extracted_ifsc: Optional[str] = None
    extracted_iban: Optional[str] = None
    
    # From vendor profile (from database)
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    verified_bank_hash: Optional[str] = None
    vendor_trust_level: int = 50
    
    # Raw extraction data (for field extraction)
    raw_text: Optional[str] = None


@dataclass
class FraudGateDecision:
    """Decision from fraud gate."""
    
    is_safe: bool
    bank_detail_changed: bool
    vendor_mismatch: bool
    risk_flags: list[str]
    requires_security_review: bool
    
    # Details
    extracted_bank_hash: Optional[str] = None
    previous_bank_hash: Optional[str] = None


def run_fraud_gate(input_data: FraudCheckInput) -> FraudGateDecision:
    """
    Run deterministic fraud gate checks.
    
    This is a PURE FUNCTION - no async, no database calls.
    All necessary data must be passed in.
    
    Checks:
    1. Bank detail change (account number, IFSC, IBAN)
    2. Vendor name mismatch
    3. Bank detail format validation
    
    Returns:
        FraudGateDecision with is_safe=False if any check fails
    """
    risk_flags = []
    bank_detail_changed = False
    vendor_mismatch = False
    
    # 1. Extract bank details from invoice
    extracted_bank_account = input_data.extracted_bank_account
    extracted_ifsc = input_data.extracted_ifsc
    extracted_iban = input_data.extracted_iban
    
    # Try to extract from raw text if not provided directly
    if input_data.raw_text and not (extracted_bank_account or extracted_ifsc or extracted_iban):
        extracted_bank_account = extract_account_from_text(input_data.raw_text)
        extracted_ifsc = extract_ifsc_from_text(input_data.raw_text)
        extracted_iban = extract_iban_from_text(input_data.raw_text)
    
    # 2. Validate bank detail formats
    if extracted_bank_account and not validate_account_number(extracted_bank_account):
        risk_flags.append("INVALID_ACCOUNT_FORMAT")
    
    if extracted_ifsc and not validate_ifsc_format(extracted_ifsc):
        risk_flags.append("INVALID_IFSC_FORMAT")
    
    if extracted_iban and not validate_iban_format(extracted_iban):
        risk_flags.append("INVALID_IBAN_FORMAT")
    
    # 3. Hash extracted bank details
    extracted_bank_hash = hash_bank_details(
        account_number=extracted_bank_account,
        ifsc_code=extracted_ifsc,
        iban=extracted_iban,
    )
    
    # 4. Compare with verified bank hash
    previous_bank_hash = input_data.verified_bank_hash
    
    if extracted_bank_hash and previous_bank_hash:
        if extracted_bank_hash != previous_bank_hash:
            bank_detail_changed = True
            risk_flags.append("BANK_DETAIL_CHANGE")
            logger.warning(
                "fraud_gate_bank_change_detected",
                trace_id=input_data.trace_id,
                extracted=extracted_bank_hash[:8] + "...",
                previous=previous_bank_hash[:8] + "...",
            )
    
    # 5. Vendor name mismatch check
    if input_data.vendor_name and input_data.extracted_vendor_name:
        extracted_normalized = input_data.extracted_vendor_name.lower().strip()
        vendor_normalized = input_data.vendor_name.lower().strip()
        
        # Exact match
        if extracted_normalized != vendor_normalized:
            # Check for common variations
            extracted_words = set(extracted_normalized.split())
            vendor_words = set(vendor_normalized.split())
            
            # If no word overlap, it's a mismatch
            if not extracted_words & vendor_words:
                vendor_mismatch = True
                risk_flags.append("VENDOR_NAME_MISMATCH")
                logger.warning(
                    "fraud_gate_vendor_mismatch",
                    trace_id=input_data.trace_id,
                    extracted=input_data.extracted_vendor_name,
                    expected=input_data.vendor_name,
                )
    
    # 6. Determine if security review is required
    requires_security_review = (
        bank_detail_changed or
        vendor_mismatch or
        len(risk_flags) > 0
    )
    
    # 7. Determine overall safety
    # Bank change or vendor mismatch = NOT SAFE (requires HITL)
    is_safe = not requires_security_review
    
    return FraudGateDecision(
        is_safe=is_safe,
        bank_detail_changed=bank_detail_changed,
        vendor_mismatch=vendor_mismatch,
        risk_flags=risk_flags,
        requires_security_review=requires_security_review,
        extracted_bank_hash=extracted_bank_hash,
        previous_bank_hash=previous_bank_hash,
    )


def create_fraud_result(
    trace_id: str,
    decision: FraudGateDecision,
) -> FraudGateResult:
    """Create a FraudGateResult from a FraudGateDecision."""
    
    reasons = []
    if decision.bank_detail_changed:
        reasons.append("Bank details differ from vendor profile")
    if decision.vendor_mismatch:
        reasons.append("Vendor name does not match expected")
    if decision.risk_flags:
        reasons.extend(decision.risk_flags)
    
    return FraudGateResult(
        node_name=NodeName.FRAUD_GATE,
        confidence=1.0 if decision.is_safe else 0.0,  # Deterministic
        reasons=reasons,
        artifacts={
            "extracted_bank_hash": decision.extracted_bank_hash,
            "previous_bank_hash": decision.previous_bank_hash,
            "risk_flags": decision.risk_flags,
        },
        status="success",
        is_safe=decision.is_safe,
        bank_detail_changed=decision.bank_detail_changed,
        vendor_mismatch=decision.vendor_mismatch,
        requires_security_review=decision.requires_security_review,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async Wrapper (for LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def fraud_gate_node(state: dict) -> dict:
    """
    LangGraph node for fraud gate.
    
    Args:
        state: APWorkflowState as dict
        
    Returns:
        Updated state with fraud_result
    """
    from src.db import db
    
    trace_id = state.get("trace_id")
    extracted = state.get("extracted_invoice")
    
    if not extracted:
        logger.error("fraud_gate_no_extraction", trace_id=trace_id)
        return {
            "fraud_result": FraudGateResult(
                node_name=NodeName.FRAUD_GATE,
                confidence=0.0,
                reasons=["No extracted invoice data"],
                status="error",
                is_safe=False,
                requires_security_review=True,
            )
        }
    
    # Get vendor profile from database
    vendor_id = state.get("vendor_id")
    vendor_profile = None
    
    if vendor_id:
        vendor_profile = await db.get_vendor_by_id(vendor_id)
    
    # Build fraud check input
    input_data = FraudCheckInput(
        trace_id=trace_id,
        extracted_vendor_name=extracted.get("vendor_name", ""),
        extracted_bank_account=extracted.get("vendor_bank_account"),
        extracted_ifsc=extracted.get("vendor_ifsc"),
        extracted_iban=extracted.get("vendor_iban"),
        raw_text=state.get("raw_text"),
        vendor_id=str(vendor_id) if vendor_id else None,
        vendor_name=vendor_profile.get("name") if vendor_profile else None,
        verified_bank_hash=vendor_profile.get("verified_bank_hash") if vendor_profile else None,
        vendor_trust_level=vendor_profile.get("trust_level", 50) if vendor_profile else 50,
    )
    
    # Run fraud gate
    decision = run_fraud_gate(input_data)
    result = create_fraud_result(trace_id, decision)
    
    logger.info(
        "fraud_gate_completed",
        trace_id=trace_id,
        is_safe=decision.is_safe,
        requires_review=decision.requires_security_review,
        risk_flags=decision.risk_flags,
    )
    
    return {
        "fraud_result": result.model_dump(),
        "invoice_status": "fraud_checked",
    }
