"""
Invoicify End-to-End Test Suite.

This package contains comprehensive E2E tests for the Invoicify
invoice processing pipeline.

Modules:
    generate_invoice: Test invoice PDF generator
    test_full_workflow: Complete workflow E2E test

Usage:
    pytest tests/e2e/ -v
    python -m tests.e2e.test_full_workflow
"""

from tests.e2e.generate_invoice import TestInvoiceData, TestInvoiceGenerator, InvoiceLineItem

__all__ = [
    "TestInvoiceData",
    "TestInvoiceGenerator",
    "InvoiceLineItem",
]
