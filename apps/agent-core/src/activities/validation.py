"""
Validation Activity - Ported from critic.ts logic.
Performs mathematical verification on extracted invoice data.
"""
import structlog
from typing import Dict, Any, List

logger = structlog.get_logger()

def validate_invoice_math(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifies that the math on the invoice adds up.
    Returns a report of discrepancies.
    """
    trace_id = invoice_data.get("invoice_number", "unknown")
    log = logger.bind(trace_id=trace_id)
    
    total_amount = float(invoice_data.get("total_amount") or 0)
    subtotal = float(invoice_data.get("subtotal") or 0)
    tax = float(invoice_data.get("tax") or 0)
    line_items = invoice_data.get("line_items", [])
    
    issues = []
    
    # 1. Line Items Sum check
    if line_items:
        calculated_sum = sum(float(item.get("amount", 0)) for item in line_items)
        # If subtotal is provided, check against it. Otherwise, use total_amount - tax.
        target_subtotal = subtotal if subtotal > 0 else (total_amount - tax)
        
        if abs(calculated_sum - target_subtotal) > 0.05: # $0.05 tolerance for rounding
            issues.append(f"Line items sum ({calculated_sum:.2f}) does not match subtotal ({target_subtotal:.2f})")
    
    # 2. Total Equation check: Subtotal + Tax = Total
    if subtotal > 0:
        if abs((subtotal + tax) - total_amount) > 0.05:
            issues.append(f"Subtotal + Tax ({subtotal + tax:.2f}) does not match Total Amount ({total_amount:.2f})")
            
    # 3. Non-zero Total
    if total_amount <= 0:
        issues.append("Total amount is zero or negative")

    is_valid = len(issues) == 0
    log.info("math_validation_complete", is_valid=is_valid, issue_count=len(issues))
    
    return {
        "is_valid": is_valid,
        "issues": issues,
        "calculated_total": subtotal + tax if subtotal > 0 else total_amount
    }
