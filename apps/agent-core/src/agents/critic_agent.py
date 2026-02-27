"""
Critic Agent for Invoice Validation.

Validates extracted invoice data:
- Math validation (line items sum to total)
- Duplicate detection (via RAG)
- Contract terms (price variance)
"""

from typing import Any, Dict, List, Optional
import structlog

from src.schemas.invoice_v2 import ExtractedInvoice

logger = structlog.get_logger()


class CriticAgent:
    """
    Validates extracted invoice data.
    
    Checks:
    1. Math validation: line items sum to subtotal, subtotal + tax = total
    2. Duplicate detection: similar invoices in database
    3. Price anomaly: variance from historical prices
    4. Contract terms: PO matching, approved vendors
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize critic.
        
        Args:
            config: Configuration with RAG client settings
        """
        self.config = config if config is not None else {}
        self.search_client = self.config.get("search_client")
    
    async def validate(self, extracted: ExtractedInvoice) -> Dict[str, Any]:
        """
        Validate extracted invoice.
        
        Args:
            extracted: Extracted invoice data
            
        Returns:
            Validation result dict
        """
        validation_result = {
            "math_valid": True,
            "math_errors": [],
            "is_duplicate": False,
            "duplicate_invoice_id": None,
            "price_anomaly": False,
            "price_variance_pct": None,
            "contract_terms_found": False,
        }
        
        # 1. Math validation
        math_errors = self._validate_math(extracted)
        if math_errors:
            validation_result["math_valid"] = False
            validation_result["math_errors"] = math_errors
        
        # 2. Duplicate detection (placeholder - needs RAG)
        # duplicate_result = await self._check_duplicates(extracted)
        # validation_result.update(duplicate_result)
        
        # 3. Price anomaly detection (placeholder)
        # price_result = await self._check_price_anomaly(extracted)
        # validation_result.update(price_result)
        
        logger.info(
            "invoice_validated",
            invoice_id=extracted.invoice_id,
            math_valid=validation_result["math_valid"],
            is_duplicate=validation_result["is_duplicate"],
        )
        
        return validation_result
    
    def _validate_math(self, extracted: ExtractedInvoice) -> List[str]:
        """
        Validate mathematical accuracy.
        
        Checks:
        - Each line item: quantity * unit_price ≈ total (2 cent tolerance)
        - Sum of line items ≈ subtotal (2 cent tolerance)
        - subtotal + tax_amount ≈ total_amount (5 cent tolerance)
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Check line items
        for i, item in enumerate(extracted.line_items):
            expected_total = item.quantity * item.unit_price
            if abs(item.total - expected_total) > 0.02:
                errors.append(
                    f"Line item {i+1} total mismatch: "
                    f"got {item.total:.2f}, expected {expected_total:.2f}"
                )
        
        # Check subtotal
        line_total = sum(item.total for item in extracted.line_items)
        if abs(extracted.subtotal - line_total) > 0.02:
            errors.append(
                f"Subtotal mismatch: "
                f"got {extracted.subtotal:.2f}, expected {line_total:.2f}"
            )
        
        # Check total amount
        expected_total = extracted.subtotal + extracted.tax_amount
        if abs(extracted.total_amount - expected_total) > 0.05:
            errors.append(
                f"Total amount mismatch: "
                f"got {extracted.total_amount:.2f}, expected {expected_total:.2f}"
            )
        
        return errors
    
    async def _check_duplicates(self, extracted: ExtractedInvoice) -> Dict[str, Any]:
        """
        Check for duplicate invoices via RAG.
        
        Uses vector similarity search to find invoices with:
        - Same vendor + same amount + same date
        - Similar line items + same amount
        
        Returns:
            Duplicate check result
        """
        # Placeholder - needs Azure AI Search implementation
        return {
            "is_duplicate": False,
            "duplicate_invoice_id": None,
        }
    
    async def _check_price_anomaly(self, extracted: ExtractedInvoice) -> Dict[str, Any]:
        """
        Check for price anomalies vs historical data.
        
        Compares line item prices to historical averages.
        Flags if variance > 20%.
        
        Returns:
            Price anomaly result
        """
        # Placeholder - needs historical data lookup
        return {
            "price_anomaly": False,
            "price_variance_pct": None,
        }
