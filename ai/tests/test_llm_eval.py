"""
LLM Evaluation Tests using DeepEval with Groq

Comprehensive evaluation of LLM outputs for invoice processing.
Configure Groq via environment variables:
- GROQ_API_KEY: Your Groq API key
- GROQ_MODEL: Model name (default: groq/llama-3.3-70b-versatile)
"""

import os
import pytest
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval
from deepeval.models import LiteLLMModel


# ============================================================================
# Invoice Extraction Test Cases
# ============================================================================

INVOICE_EXTRACTION_TEST_CASES = [
    LLMTestCase(
        input="Extract invoice details from: Invoice #INV-2024-001 dated 2024-01-15 from Acme Corp for $1,500.00 USD",
        actual_output="Invoice Number: INV-2024-001, Date: 2024-01-15, Vendor: Acme Corp, Amount: $1,500.00 USD",
        expected_output="Invoice number: INV-2024-001, Date: 2024-01-15, Vendor: Acme Corp, Amount: $1,500.00 USD",
    ),
    LLMTestCase(
        input="Extract data from: Purchase Order PO-9988 dated Feb 28, 2024. Vendor: Tech Solutions Inc. Total: $4,250.50. Due: March 30, 2024.",
        actual_output="PO Number: PO-9988, Order Date: 2024-02-28, Vendor: Tech Solutions Inc., Total: $4,250.50 USD, Due Date: 2024-03-30",
        expected_output="PO: PO-9988, Date: 2024-02-28, Vendor: Tech Solutions Inc., Amount: $4,250.50, Due: 2024-03-30",
    ),
]


# ============================================================================
# Invoice Classification Test Cases
# ============================================================================

INVOICE_CLASSIFICATION_TEST_CASES = [
    LLMTestCase(
        input="Classify this invoice: Construction materials - $25,000 for Building Materials LLC",
        actual_output="Category: CONSTRUCTION_SUPPLIES, Risk Level: MEDIUM, Payment Terms: NET30",
        expected_output="Category: CONSTRUCTION_SUPPLIES, Risk: MEDIUM, Terms: NET30",
    ),
    LLMTestCase(
        input="Classify: Software subscription - $299/month for SaaS Platform Pro",
        actual_output="Category: SOFTWARE_SUBSCRIPTION, Risk Level: LOW, Payment Terms: MONTHLY",
        expected_output="Category: SOFTWARE_SUBSCRIPTION, Risk: LOW, Terms: MONTHLY",
    ),
]


# ============================================================================
# Risk Assessment Test Cases
# ============================================================================

RISK_ASSESSMENT_TEST_CASES = [
    LLMTestCase(
        input="Assess risk for: Invoice from new vendor (first invoice), amount $50,000, overdue by 45 days",
        actual_output="Risk Score: 85/100, High Risk Factors: New vendor, Large amount, Overdue 45 days, Recommendations: Manual review",
        expected_output="Risk: 85/100, Factors: New vendor, Large amount, Overdue 45 days",
    ),
    LLMTestCase(
        input="Assess risk for: Recurring vendor (2 years), amount $500, always on time",
        actual_output="Risk Score: 10/100, Low Risk Factors: Established vendor, Small amount, Payment history, Recommendations: Auto-approve",
        expected_output="Risk: 10/100, Low risk due to established relationship and good payment history",
    ),
]


# ============================================================================
# Helper Functions
# ============================================================================

def get_litellm_model():
    """Get LiteLLM model wrapper for Groq"""
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")

    if not api_key:
        pytest.skip("GROQ_API_KEY not set")

    return LiteLLMModel(model=model)


# ============================================================================
# Invoice Extraction Tests
# ============================================================================

class TestInvoiceExtraction:
    """Test invoice data extraction accuracy using G-Eval"""

    def test_invoice_extraction_correctness(self):
        """Test that extracted invoice data matches expected output"""
        test_case = INVOICE_EXTRACTION_TEST_CASES[0]

        correctness = GEval(
            name="Invoice Extraction Correctness",
            criteria="Evaluate if the extracted invoice data matches the expected output. Check invoice number, date, vendor name, and amounts.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.7,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Correctness score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )

    def test_po_extraction_correctness(self):
        """Test that extracted PO data matches expected output"""
        test_case = INVOICE_EXTRACTION_TEST_CASES[1]

        correctness = GEval(
            name="PO Extraction Correctness",
            criteria="Evaluate if the extracted purchase order data matches the expected output. Check PO number, date, vendor, amount, and due date.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.6,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Correctness score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )


# ============================================================================
# Invoice Classification Tests
# ============================================================================

class TestInvoiceClassification:
    """Test invoice classification accuracy"""

    def test_classification_correctness(self):
        """Test that invoice classification matches expected output"""
        test_case = INVOICE_CLASSIFICATION_TEST_CASES[0]

        correctness = GEval(
            name="Classification Accuracy",
            criteria="Determine if the invoice classification matches the expected category and risk level.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.7,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Classification score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )

    def test_subscription_classification(self):
        """Test subscription classification"""
        test_case = INVOICE_CLASSIFICATION_TEST_CASES[1]

        correctness = GEval(
            name="Subscription Classification",
            criteria="Determine if the software subscription classification is correct.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.7,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Classification score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )


# ============================================================================
# Risk Assessment Tests
# ============================================================================

class TestRiskAssessment:
    """Test risk assessment accuracy"""

    def test_high_risk_assessment(self):
        """Test that high risk invoices are correctly identified"""
        test_case = RISK_ASSESSMENT_TEST_CASES[0]

        correctness = GEval(
            name="High Risk Assessment",
            criteria="Evaluate if the high risk assessment correctly identifies new vendor, large amount, and overdue status.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.6,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Risk assessment score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )

    def test_low_risk_assessment(self):
        """Test that low risk invoices are correctly identified"""
        test_case = RISK_ASSESSMENT_TEST_CASES[1]

        correctness = GEval(
            name="Low Risk Assessment",
            criteria="Evaluate if the low risk assessment correctly identifies established vendor and good payment history.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.65,
            model=get_litellm_model(),
        )

        correctness.measure(test_case)
        assert correctness.score >= correctness.threshold, (
            f"Low risk assessment score {correctness.score} below threshold {correctness.threshold}. Reason: {correctness.reason}"
        )


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
