"""Vision Agent - Wraps existing extractor for LangGraph."""

import os
from typing import Any
from ..types.schemas import InvoiceState


class VisionAgent:
    """Vision extraction agent using Groq API."""
    
    def __init__(self):
        """Initialize the vision agent."""
        # We'll use the existing extractor logic from archive
        pass
    
    async def execute(self, state: InvoiceState) -> InvoiceState:
        """
        LangGraph node function.
        Extracts invoice data from PDF using Vision AI.
        """
        trace_id = state["trace_id"]
        r2_key = state["r2_key_raw"]
        
        # TODO: Implement actual vision extraction
        # For now, return mock data
        invoice_data = {
            "vendor_name": "Acme Corp",
            "invoice_number": "INV-001",
            "amount": 1000.00,
            "currency": "USD",
            "invoice_date": "2024-02-13",
            "due_date": "2024-03-13",
            "line_items": [],
            "confidence": 0.95
        }
        
        return {
            **state,
            "invoice_data": invoice_data
        }
