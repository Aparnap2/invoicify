"""Invoice hashing utilities for duplicate detection.

Provides content-based hashing to detect duplicate invoices
regardless of trace_id or submission channel.
"""

import hashlib
from typing import Optional


def compute_invoice_hash(
    vendor_name: Optional[str],
    invoice_number: Optional[str],
    invoice_date: Optional[str],
    total_amount: Optional[float | str],
) -> str:
    """
    Compute SHA256 hash of invoice content for duplicate detection.
    
    Hash is computed from: vendor_name + invoice_number + invoice_date + total_amount
    This prevents duplicate payments even if trace_id differs.
    
    Args:
        vendor_name: Vendor/supplier name
        invoice_number: Invoice number from the document
        invoice_date: Invoice date (ISO format string)
        total_amount: Total invoice amount
        
    Returns:
        SHA256 hex digest (64 characters)
        
    Example:
        >>> hash = compute_invoice_hash(
        ...     vendor_name="Acme Corp",
        ...     invoice_number="INV-001",
        ...     invoice_date="2024-01-15",
        ...     total_amount=1000.00,
        ... )
        >>> len(hash)
        64
    """
    # Normalize inputs to strings, handle None gracefully
    vendor = (vendor_name or "").strip().lower()
    number = (invoice_number or "").strip().upper()
    date = (invoice_date or "").strip()
    amount = str(total_amount or "0").strip()
    
    # Create canonical string for hashing
    canonical = f"{vendor}|{number}|{date}|{amount}"
    
    # Compute SHA256 hash
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
