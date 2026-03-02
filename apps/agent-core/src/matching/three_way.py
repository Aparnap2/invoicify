"""
Three-Way Matching for AP Workflow.

Performs semantic 3-way matching using Azure AI Search vectors:
- Invoice lines ↔ PO lines ↔ Receipt lines

Uses Azure AI Search (free tier: 50 MB, 3 indexes) for vector similarity.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import structlog

from src.schemas.ap_models import (
    NodeName,
    ThreeWayMatchResult,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Tolerance for 3-way match (percentage)
DEFAULT_TOLERANCE = 5.0  # 5% variance allowed
HIGH_VALUE_TOLERANCE = 2.0  # 2% for high-value invoices

# Confidence thresholds
HIGH_CONFIDENCE = 0.95
MEDIUM_CONFIDENCE = 0.80
LOW_CONFIDENCE = 0.60

# High value threshold
HIGH_VALUE_THRESHOLD = Decimal("10000")


# ─────────────────────────────────────────────────────────────────────────────
# Azure AI Search Client
# ─────────────────────────────────────────────────────────────────────────────


class AISearchClient:
    """Client for Azure AI Search operations."""
    
    def __init__(self):
        from src.config import get_settings
        from azure.search.documents import SearchClient
        from azure.identity import DefaultAzureCredential
        
        self.settings = get_settings()
        self.client = None
        
        if self.settings.azure_search_endpoint:
            try:
                # Use Azure AD authentication
                credential = DefaultAzureCredential()
                self.client = SearchClient(
                    endpoint=self.settings.azure_search_endpoint,
                    index_name="po_receipt",
                    credential=credential,
                )
                logger.info("azure_search_client_initialized")
            except Exception as e:
                logger.warning("azure_search_client_init_failed", error=str(e))
                self.client = None
    
    async def find_similar_pos(
        self,
        invoice_line_items: list[dict[str, Any]],
        vendor_id: str,
        top: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Find similar POs using semantic search.
        
        Args:
            invoice_line_items: Invoice line items to match
            vendor_id: Vendor ID to filter POs
            top: Number of results to return
            
        Returns:
            List of similar PO records with scores
        """
        if not self.client:
            return []
        
        try:
            # Construct search query from line items
            query_text = " ".join(
                item.get("description", "") for item in invoice_line_items
            )
            
            results = self.client.search(
                search_text=query_text,
                filter=f"vendor_id eq '{vendor_id}'",
                top=top,
                select=["po_number", "po_id", "line_items", "total", "description"],
            )
            
            return [
                {
                    "po_number": r.get("po_number"),
                    "po_id": r.get("po_id"),
                    "description": r.get("description"),
                    "total": r.get("total"),
                    "score": r.get("@search_score", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("azure_search_failed", error=str(e))
            return []
    
    async def find_similar_line_items(
        self,
        invoice_line_description: str,
        po_id: str,
        top: int = 3,
    ) -> list[dict[str, Any]]:
        """Find similar PO line items using semantic search."""
        if not self.client:
            return []
        
        try:
            results = self.client.search(
                search_text=invoice_line_description,
                filter=f"po_id eq '{po_id}'",
                top=top,
                select=["line_number", "description", "quantity", "unit_price", "amount"],
            )
            
            return [
                {
                    "line_number": r.get("line_number"),
                    "description": r.get("description"),
                    "quantity": r.get("quantity"),
                    "unit_price": r.get("unit_price"),
                    "amount": r.get("amount"),
                    "score": r.get("@search_score", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("azure_search_line_items_failed", error=str(e))
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Three-Way Match Logic
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ThreeWayMatchInput:
    """Input for three-way matching."""
    
    trace_id: str
    po_number: Optional[str]
    invoice_total: Decimal
    invoice_line_items: list[dict[str, Any]]
    vendor_id: Optional[str]
    
    # From database/context
    po_data: Optional[dict[str, Any]] = None
    po_line_items: list[dict[str, Any]] = None
    receipt_data: Optional[dict[str, Any]] = None


@dataclass
class LineItemMatch:
    """Match result for a single line item."""
    
    invoice_line_number: int
    invoice_description: str
    invoice_amount: Decimal
    po_line_number: Optional[int] = None
    po_description: Optional[str] = None
    po_amount: Optional[Decimal] = None
    match_confidence: float = 0.0
    match_type: Optional[str] = None  # "exact" | "semantic" | "none"


def calculate_line_item_match(
    invoice_item: dict[str, Any],
    po_items: list[dict[str, Any]],
    ai_client: Optional[AISearchClient],
) -> LineItemMatch:
    """
    Match an invoice line item to PO line items.
    
    Uses:
    1. Exact match (description + amount)
    2. Semantic match (Azure AI Search)
    """
    invoice_desc = invoice_item.get("description", "").lower()
    invoice_amount = Decimal(str(invoice_item.get("amount", 0)))
    
    # Try exact match first
    for po_item in po_items:
        po_desc = po_item.get("description", "").lower()
        po_amount = Decimal(str(po_item.get("amount", 0)))
        
        # Exact match on description and amount
        if invoice_desc == po_desc and invoice_amount == po_amount:
            return LineItemMatch(
                invoice_line_number=invoice_item.get("line_number", 1),
                invoice_description=invoice_item.get("description", ""),
                invoice_amount=invoice_amount,
                po_line_number=po_item.get("line_number"),
                po_description=po_item.get("description", ""),
                po_amount=po_amount,
                match_confidence=1.0,
                match_type="exact",
            )
    
    # Try semantic match with AI Search
    if ai_client:
        try:
            similar = await ai_client.find_similar_line_items(
                invoice_line_description=invoice_item.get("description", ""),
                po_id=str(po_items[0].get("po_id", "")) if po_items else "",
            )
            
            if similar:
                best_match = similar[0]
                score = best_match.get("score", 0)
                
                # Normalize score to 0-1
                confidence = min(1.0, score / 10.0)
                
                return LineItemMatch(
                    invoice_line_number=invoice_item.get("line_number", 1),
                    invoice_description=invoice_item.get("description", ""),
                    invoice_amount=invoice_amount,
                    po_line_number=best_match.get("line_number"),
                    po_description=best_match.get("description", ""),
                    po_amount=Decimal(str(best_match.get("amount", 0))),
                    match_confidence=confidence,
                    match_type="semantic" if confidence >= MEDIUM_CONFIDENCE else "none",
                )
        except Exception as e:
            logger.warning("semantic_match_failed", error=str(e))
    
    # No match found
    return LineItemMatch(
        invoice_line_number=invoice_item.get("line_number", 1),
        invoice_description=invoice_item.get("description", ""),
        invoice_amount=invoice_amount,
        match_confidence=0.0,
        match_type="none",
    )


def run_three_way_match(
    input_data: ThreeWayMatchInput,
    ai_client: Optional[AISearchClient] = None,
) -> ThreeWayMatchResult:
    """
    Run deterministic 3-way matching.
    
    Matches:
    1. Invoice total vs PO total
    2. Invoice line items vs PO line items
    
    Returns:
        ThreeWayMatchResult with confidence and variance
    """
    trace_id = input_data.trace_id
    
    # No PO provided - return low confidence
    if not input_data.po_number:
        return ThreeWayMatchResult(
            node_name=NodeName.THREE_WAY_MATCH,
            confidence=0.0,
            reasons=["No PO number provided on invoice"],
            status="success",
            po_match_confidence=0.0,
            requires_po_approval=True,  # No PO = needs approval
        )
    
    # Use provided PO data or search
    po_data = input_data.po_data
    po_line_items = input_data.po_line_items or []
    
    if not po_data and input_data.vendor_id and ai_client:
        # Search for POs using AI Search
        similar_pos = await ai_client.find_similar_pos(
            invoice_line_items=input_data.invoice_line_items,
            vendor_id=input_data.vendor_id,
        )
        
        if similar_pos:
            po_data = similar_pos[0]
            # In real implementation, fetch PO line items from DB
    
    if not po_data:
        return ThreeWayMatchResult(
            node_name=NodeName.THREE_WAY_MATCH,
            confidence=0.0,
            reasons=[f"PO {input_data.po_number} not found"],
            status="success",
            po_match_confidence=0.0,
            po_number=input_data.po_number,
            requires_po_approval=True,
        )
    
    # Calculate variance
    po_total = Decimal(str(po_data.get("total", 0)))
    invoice_total = input_data.invoice_total
    
    if invoice_total > 0:
        variance = invoice_total - po_total
        variance_percentage = (float(variance) / float(po_total)) * 100
    else:
        variance = Decimal("0")
        variance_percentage = 0.0
    
    # Determine tolerance based on invoice value
    tolerance = HIGH_VALUE_TOLERANCE if invoice_total >= HIGH_VALUE_THRESHOLD else DEFAULT_TOLERANCE
    
    # Match line items
    line_item_matches = []
    total_confidence = 0.0
    
    for item in input_data.invoice_line_items:
        match = calculate_line_item_match(item, po_line_items, ai_client)
        line_item_matches.append({
            "invoice_line_number": match.invoice_line_number,
            "invoice_description": match.invoice_description,
            "invoice_amount": float(match.invoice_amount),
            "po_line_number": match.po_line_number,
            "po_description": match.po_description,
            "po_amount": float(match.po_amount) if match.po_amount else None,
            "match_confidence": match.match_confidence,
            "match_type": match.match_type,
        })
        total_confidence += match.match_confidence
    
    # Calculate overall confidence
    if line_item_matches:
        avg_confidence = total_confidence / len(line_item_matches)
    else:
        avg_confidence = 0.0
    
    # Determine if variance is within tolerance
    is_within_tolerance = abs(variance_percentage) <= tolerance
    
    # Determine if PO approval is required
    requires_approval = (
        not is_within_tolerance or
        avg_confidence < HIGH_CONFIDENCE or
        not po_line_items  # No PO line items to match
    )
    
    # Build reasons
    reasons = []
    if is_within_tolerance:
        reasons.append(f"Total variance {variance_percentage:.2f}% within {tolerance}% tolerance")
    else:
        reasons.append(f"Total variance {variance_percentage:.2f}% exceeds {tolerance}% tolerance")
    
    if avg_confidence >= HIGH_CONFIDENCE:
        reasons.append(f"Line item match confidence {avg_confidence:.0%} is high")
    elif avg_confidence >= MEDIUM_CONFIDENCE:
        reasons.append(f"Line item match confidence {avg_confidence:.0%} is medium")
    else:
        reasons.append(f"Line item match confidence {avg_confidence:.0%} is low")
    
    return ThreeWayMatchResult(
        node_name=NodeName.THREE_WAY_MATCH,
        confidence=avg_confidence,
        reasons=reasons,
        status="success",
        po_match_confidence=avg_confidence,
        po_number=po_data.get("po_number"),
        po_total=po_total,
        invoice_total=invoice_total,
        variance=variance,
        variance_percentage=variance_percentage,
        line_item_matches=line_item_matches,
        requires_po_approval=requires_approval,
        tolerance_percentage=tolerance,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async Wrapper (for LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def three_way_match_node(state: dict) -> dict:
    """
    LangGraph node for three-way matching.
    
    Args:
        state: APWorkflowState as dict
        
    Returns:
        Updated state with three_way_result
    """
    from src.db import db
    
    trace_id = state.get("trace_id")
    extracted = state.get("extracted_invoice")
    vendor_id = state.get("vendor_id")
    
    if not extracted:
        logger.error("three_way_no_extraction", trace_id=trace_id)
        return {
            "three_way_result": ThreeWayMatchResult(
                node_name=NodeName.THREE_WAY_MATCH,
                confidence=0.0,
                reasons=["No extracted invoice data"],
                status="error",
                requires_po_approval=True,
            )
        }
    
    po_number = extracted.get("po_number")
    invoice_total = Decimal(str(extracted.get("total_amount", 0)))
    invoice_line_items = extracted.get("line_items", [])
    
    # Get PO data from database if PO number exists
    po_data = None
    po_line_items = []
    
    if po_number:
        po_data = await db.get_purchase_order_by_number(po_number)
        if po_data:
            po_line_items = await db.get_po_line_items(po_data["id"])
    
    # Initialize AI Search client
    ai_client = AISearchClient()
    
    # Build input
    input_data = ThreeWayMatchInput(
        trace_id=trace_id,
        po_number=po_number,
        invoice_total=invoice_total,
        invoice_line_items=invoice_line_items,
        vendor_id=str(vendor_id) if vendor_id else None,
        po_data=po_data,
        po_line_items=po_line_items,
    )
    
    # Run matching
    result = await run_three_way_match(input_data, ai_client)
    
    logger.info(
        "three_way_match_completed",
        trace_id=trace_id,
        po_number=po_number,
        confidence=result.po_match_confidence,
        variance_pct=result.variance_percentage,
        requires_approval=result.requires_po_approval,
    )
    
    return {
        "three_way_result": result.model_dump(),
        "invoice_status": "matched",
    }
