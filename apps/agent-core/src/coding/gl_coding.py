"""
GL Coding for AP Workflow.

Uses historical invoice data from Azure AI Search to suggest GL codes:
- Looks up historical invoices with same vendor
- Uses semantic search to find similar line item descriptions
- Falls back to LLM for ambiguous cases

Memory-based coding using Azure AI Search index: ap_history
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import structlog

from src.schemas.ap_models import (
    GLCodingResult,
    NodeName,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Confidence thresholds
HIGH_CONFIDENCE = 0.90
MEDIUM_CONFIDENCE = 0.70

# Default GL code for unknown items
DEFAULT_GL_CODE = "6000-OPERATING"  # Default operating expense

# GL code categories
GL_CATEGORIES = {
    "6000-OPERATING": "Operating Expenses",
    "6100-RENT": "Rent Expense",
    "6200-UTILITIES": "Utilities",
    "6300-SUPPLIES": "Office Supplies",
    "6400-TRAVEL": "Travel & Entertainment",
    "6500-SOFTWARE": "Software & Subscriptions",
    "6600-PROFESSIONAL": "Professional Services",
    "6700-MARKETING": "Marketing & Advertising",
    "6800-INSURANCE": "Insurance",
    "6900-OTHER": "Other Expenses",
}


# ─────────────────────────────────────────────────────────────────────────────
# Azure AI Search Client for AP History
# ─────────────────────────────────────────────────────────────────────────────


class APHistorySearchClient:
    """Client for searching AP history in Azure AI Search."""
    
    def __init__(self):
        from src.config import get_settings
        from azure.search.documents import SearchClient
        from azure.identity import DefaultAzureCredential
        
        self.settings = get_settings()
        self.client = None
        
        if self.settings.azure_search_endpoint:
            try:
                credential = DefaultAzureCredential()
                self.client = SearchClient(
                    endpoint=self.settings.azure_search_endpoint,
                    index_name="ap_history",
                    credential=credential,
                )
                logger.info("ap_history_search_client_initialized")
            except Exception as e:
                logger.warning("ap_history_client_init_failed", error=str(e))
                self.client = None
    
    async def find_historical_invoices(
        self,
        vendor_name: str,
        top: int = 10,
    ) -> list[dict[str, Any]]:
        """Find historical invoices for a vendor."""
        if not self.client:
            return []
        
        try:
            results = self.client.search(
                search_text=vendor_name,
                top=top,
                select=["invoice_number", "vendor_name", "gl_code", "line_items", "total"],
                order_by=["created_at desc"],
            )
            
            return [
                {
                    "invoice_number": r.get("invoice_number"),
                    "vendor_name": r.get("vendor_name"),
                    "gl_code": r.get("gl_code"),
                    "line_items": r.get("line_items", []),
                    "total": r.get("total"),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("ap_history_search_failed", error=str(e))
            return []
    
    async def find_similar_line_items(
        self,
        description: str,
        vendor_name: str,
        top: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar line items using semantic search."""
        if not self.client:
            return []
        
        try:
            results = self.client.search(
                search_text=description,
                filter=f"vendor_name eq '{vendor_name}'",
                top=top,
                select=["line_description", "gl_code", "amount"],
            )
            
            return [
                {
                    "description": r.get("line_description"),
                    "gl_code": r.get("gl_code"),
                    "amount": r.get("amount"),
                    "score": r.get("@search_score", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("line_item_search_failed", error=str(e))
            return []


# ─────────────────────────────────────────────────────────────────────────────
# GL Coding Logic
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GLCodingInput:
    """Input for GL coding."""
    
    trace_id: str
    vendor_id: Optional[str]
    vendor_name: str
    invoice_line_items: list[dict[str, Any]]
    total_amount: Decimal


def find_gl_code_from_history(
    vendor_name: str,
    line_items: list[dict[str, Any]],
    ai_client: Optional[APHistorySearchClient],
) -> tuple[Optional[str], float, list[dict[str, Any]]]:
    """
    Find GL code from historical invoices.
    
    Returns:
        Tuple of (gl_code, confidence, historical_matches)
    """
    if not ai_client:
        return None, 0.0, []
    
    # Get historical invoices for vendor
    history = await ai_client.find_historical_invoices(vendor_name)
    
    if not history:
        return None, 0.0, []
    
    # Count GL code frequency
    gl_code_counts: dict[str, int] = {}
    for inv in history:
        gl_code = inv.get("gl_code")
        if gl_code:
            gl_code_counts[gl_code] = gl_code_counts.get(gl_code, 0) + 1
    
    if not gl_code_counts:
        return None, 0.0, []
    
    # Find most common GL code
    most_common_gl = max(gl_code_counts, key=gl_code_counts.get)
    frequency = gl_code_counts[most_common_gl]
    
    # Calculate confidence based on frequency
    confidence = min(1.0, frequency / 3.0)  # 3+ invoices = high confidence
    
    return most_common_gl, confidence, history[:5]


def find_gl_code_from_line_items(
    vendor_name: str,
    line_items: list[dict[str, Any]],
    ai_client: Optional[APHistorySearchClient],
) -> tuple[Optional[str], float]:
    """
    Find GL code by matching line item descriptions.
    
    Uses semantic similarity to find similar historical line items.
    """
    if not ai_client or not line_items:
        return None, 0.0
    
    # Try each line item
    for item in line_items:
        description = item.get("description", "")
        if not description:
            continue
        
        similar = ai_client.find_similar_line_items(description, vendor_name)
        
        if similar:
            best_match = similar[0]
            gl_code = best_match.get("gl_code")
            score = best_match.get("score", 0)
            
            if gl_code:
                confidence = min(1.0, score / 10.0)
                return gl_code, confidence
    
    return None, 0.0


def suggest_gl_code_with_llm(
    vendor_name: str,
    line_items: list[dict[str, Any]],
) -> tuple[Optional[str], str]:
    """
    Use LLM as fallback to suggest GL code.
    
    Only used when memory-based matching fails.
    """
    # This would call the LLM - for now, return default
    return DEFAULT_GL_CODE, "llm_fallback"


def run_gl_coding(
    input_data: GLCodingInput,
    ai_client: Optional[APHistorySearchClient] = None,
) -> GLCodingResult:
    """
    Run GL coding using memory-based approach.
    
    Priority:
    1. Historical vendor GL codes (from AI Search)
    2. Similar line item descriptions (from AI Search)
    3. LLM fallback
    
    Returns:
        GLCodingResult with suggested GL code
    """
    trace_id = input_data.trace_id
    vendor_name = input_data.vendor_name
    line_items = input_data.invoice_line_items
    total = input_data.total_amount
    
    # Try 1: Find GL code from vendor history
    gl_code, confidence, history = find_gl_code_from_history(
        vendor_name, line_items, ai_client
    )
    
    if gl_code and confidence >= HIGH_CONFIDENCE:
        logger.info(
            "gl_coding_from_history",
            trace_id=trace_id,
            gl_code=gl_code,
            confidence=confidence,
        )
        
        return GLCodingResult(
            node_name=NodeName.GL_CODING,
            confidence=confidence,
            reasons=[f"Found GL code from vendor history ({len(history)} invoices)"],
            status="success",
            gl_code=gl_code,
            gl_description=GL_CATEGORIES.get(gl_code, "Unknown"),
            source="memory",
            historical_matches=[
                {
                    "invoice_number": h.get("invoice_number"),
                    "gl_code": h.get("gl_code"),
                }
                for h in history
            ],
        )
    
    # Try 2: Find GL code from similar line items
    line_gl_code, line_confidence = find_gl_code_from_line_items(
        vendor_name, line_items, ai_client
    )
    
    if line_gl_code:
        combined_confidence = (confidence + line_confidence) / 2
        logger.info(
            "gl_coding_from_line_items",
            trace_id=trace_id,
            gl_code=line_gl_code,
            confidence=combined_confidence,
        )
        
        return GLCodingResult(
            node_name=NodeName.GL_CODING,
            confidence=combined_confidence,
            reasons=["Found GL code from similar line items"],
            status="success",
            gl_code=line_gl_code,
            gl_description=GL_CATEGORIES.get(line_gl_code, "Unknown"),
            source="memory",
        )
    
    # Try 3: LLM fallback
    llm_gl_code, llm_source = suggest_gl_code_with_llm(vendor_name, line_items)
    
    logger.warning(
        "gl_coding_llm_fallback",
        trace_id=trace_id,
        gl_code=llm_gl_code,
    )
    
    return GLCodingResult(
        node_name=NodeName.GL_CODING,
        confidence=MEDIUM_CONFIDENCE,
        reasons=["Using LLM fallback for GL coding"],
        status="success",
        gl_code=llm_gl_code,
        gl_description=GL_CATEGORIES.get(llm_gl_code, "Unknown"),
        source=llm_source,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async Wrapper (for LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def gl_coding_node(state: dict) -> dict:
    """
    LangGraph node for GL coding.
    
    Args:
        state: APWorkflowState as dict
        
    Returns:
        Updated state with coding_result
    """
    trace_id = state.get("trace_id")
    extracted = state.get("extracted_invoice")
    vendor_id = state.get("vendor_id")
    
    if not extracted:
        logger.error("gl_coding_no_extraction", trace_id=trace_id)
        return {
            "coding_result": GLCodingResult(
                node_name=NodeName.GL_CODING,
                confidence=0.0,
                reasons=["No extracted invoice data"],
                status="error",
            )
        }
    
    vendor_name = extracted.get("vendor_name", "")
    invoice_line_items = extracted.get("line_items", [])
    total_amount = Decimal(str(extracted.get("total_amount", 0)))
    
    # Initialize AI Search client
    ai_client = APHistorySearchClient()
    
    # Build input
    input_data = GLCodingInput(
        trace_id=trace_id,
        vendor_id=str(vendor_id) if vendor_id else None,
        vendor_name=vendor_name,
        invoice_line_items=invoice_line_items,
        total_amount=total_amount,
    )
    
    # Run GL coding
    result = run_gl_coding(input_data, ai_client)
    
    logger.info(
        "gl_coding_completed",
        trace_id=trace_id,
        vendor=vendor_name,
        gl_code=result.gl_code,
        confidence=result.confidence,
        source=result.source,
    )
    
    return {
        "coding_result": result.model_dump(),
        "invoice_status": "coded",
    }
