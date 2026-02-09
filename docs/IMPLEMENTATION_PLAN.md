# Invoicify Implementation Plan - Master Checklist Gap Analysis

Based on the Master Checklist and current codebase analysis.

---

# # Current State Assessment

## # ✅ What We HAVE (Strong Foundation)

| Component | Status | Details |
| ----------- | -------- | --------- |
| **Database Schema** | ✅ Complete | invoices, line_items, vendors, approvals, audit_logs, duplicate_checks, risk_indicators, trust_battery, agent_decisions, strategic_config, budget_categories |
| **Vision OCR** | ✅ Complete | Cloudflare Workers AI (Llama 3.2 Vision) integration, multi-format support |
| **Trust Battery** | ✅ Complete | Per-vendor tracking, consecutive accurate/errors, trust levels (1-3), auto-approve thresholds |
| **Workflow Engine** | ✅ Complete | Analyst-Critic pattern, state machine, HITL routing |
| **Slack Intern** | ✅ Complete | Conversational queries, episode/instruction parsing, proactive alerts |
| **Evaluation Framework** | ✅ Complete | Code-based graders, test cases, trial runner |
| **Production Config** | ✅ Complete | wrangler.toml, CI/CD, logging, auth middleware |


## # ❌ What We're MISSING (Critical Gaps)

| Gap | Priority | Estimated Effort |
| ----- | ---------- | ------------------ |
| **PDF Multi-page Support** | P0 | Medium |
| **Math Validation (Critic Agent)** | P0 | Small |
| **LLM Evals (DeepEval)** | P1 | Medium |
| **PII Redaction** | P1 | Medium |
| **Row-Level Security** | P2 | Medium |
| **E2E Tests (Playwright)** | P1 | Medium |
| **Python AI Service** | P2 | Large |


---

# # Phase 1: Critical - Extraction & Validation (Week 1)

## # 1.1 PDF Multi-Page Support

**Problem:** Current vision-ocr only handles single images, not multi-page PDFs.

**Solution:** Use `pdfplumber` to extract text/tables from each page, then feed to LLM.

```python
# In Python service (ai/)
import pdfplumber
from typing import List, Dict

def extract_text_from_pdf(pdf_path: str) -> List[Dict]:
    """Extract text from all pages of a PDF."""
    all_pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True)
            tables = page.extract_tables()
            all_pages.append({
                "page": i + 1,
                "text": text,
                "tables": tables
            })
    return all_pages
```text
**Files to Create:**
- `ai/app/services/pdf_extractor.py` - PDF text/table extraction
- `worker/src/lib/pdf-processor.ts` - Cloudflare Worker compatible PDF handling

**Research Note:** Cloudflare Workers doesn't support native PDF libraries. Options:
1. Use Cloudflare Images (paid OCR)
2. Offload to Python service (recommended)
3. Use @cf/meta/llama-3.2-90b-vision-instruct (supports images)

---

## # 1.2 Math Validation (The Critic Agent)

**Problem:** LLM extraction might have math errors. Need hard validation.

**Solution:** Python function that validates line items.

```python
# In ai/app/services/critic.py

def validate_math(extracted_data: dict) -> dict:
    """
    Critic Agent: Validate extraction math
    Returns: { valid: bool, errors: list, signals: list }
    """
    errors = []
    signals = []

    # Calculate expected total from line items
    calculated_total = sum(
        item.get('quantity', 0) * item.get('unitPrice', 0)
        for item in extracted_data.get('lineItems', [])
    )

    declared_total = extracted_data.get('totalAmount', 0)

    # Check for math errors
    if abs(calculated_total - declared_total) > 0.01:
        errors.append(f"Math mismatch: Line items sum to {calculated_total}, but total is {declared_total}")
        signals.append({
            "type": "MATH_ERROR",
            "severity": "CRITICAL",
            "description": f"Declared total ${declared_total} != calculated ${calculated_total:.2f}",
            "score_contribution": 50
        })

    # Check for future dates
    invoice_date = extracted_data.get('invoiceDate')
    if invoice_date and invoice_date > datetime.now().strftime('%Y-%m-%d'):
        errors.append("Invoice date is in the future")
        signals.append({
            "type": "FUTURE_DATE",
            "severity": "WARNING",
            "description": f"Invoice date {invoice_date} is in the future",
            "score_contribution": 20
        })

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "signals": signals
    }
```text
**Files to Create:**
- `ai/app/services/critic.py` - Math and business rule validation
- Update `worker/src/lib/risk-scoring.ts` to call Critic

---

# # Phase 2: Testing & Evals (Week 2)

## # 2.1 LLM Evals with DeepEval

**Problem:** Need to catch hallucinations and measure extraction accuracy.

**Solution:** Add DeepEval metrics.

```python
# In ai/tests/test_evals.py

from deepeval import evaluate
from deepeval.metrics import HallucinationMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

def test_extraction_accuracy():
    """Test extraction faithfulness to source document."""

    hallucination_metric = HallucinationMetric(
        threshold=0.8,
        model="gpt-4o"
    )

    faithfulness_metric = FaithfulnessMetric(
        threshold=0.9,
        model="gpt-4o"
    )

    test_case = LLMTestCase(
        input="Extract invoice data from this image",
        actual_output='{"vendorName": "Acme Corp", "totalAmount": 1500.00, ...}',
        context="Ground truth: Acme Corp, $1500.00, Invoice #123"
    )

    results = evaluate([test_case], [hallucination_metric, faithfulness_metric])

    assert hallucination_metric.score >= 0.8
    assert faithfulness_metric.score >= 0.9
```text
**Files to Create:**
- `ai/tests/test_evals.py` - DeepEval test suite
- `ai/evals/config.py` - Evaluation configuration

---

## # 2.2 Math Test (Hard-Coded)

**Problem:** Don't rely on LLM for math validation.

**Solution:** Pure Python tests.

```typescript
// In worker/src/tests/math.test.ts

import { describe, it, expect } from 'vitest';

describe('Math Validation', () => {
  it('should detect line item math errors', () => {
    const lineItems = [
      { description: "Widget A", quantity: 2, unitPrice: 100, amount: 200 },
      { description: "Widget B", quantity: 3, unitPrice: 50, amount: 100 }, // Wrong: should be 150
    ];

    const calculated = lineItems.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
    const declared = 350; // Sum of amounts is 300

    expect(calculated).not.toBe(declared);
  });
});
```text
---

## # 2.3 E2E Tests (Playwright)

**Problem:** Need to test the full flow: Upload → Extract → Critic → Workflow → Result.

**Solution:** Playwright tests.

```typescript
// In worker/e2e/invoice-flow.spec.ts

import { test, expect } from '@playwright/test';

test('Happy Path: Clear invoice auto-approves', async ({ page }) => {
  await page.goto('/upload');
  await page.setInputFiles('input[type="file"]', 'test-invoices/clear-invoice.pdf');
  await page.click('button:has-text("Upload")');

  await expect(page.locator('text=Auto-Approved')).toBeVisible({ timeout: 60000 });
});
```text
---

# # Phase 3: Security (Week 3)

## # 3.1 PII Redaction

**Problem:** Invoices contain sensitive data (bank accounts, SSNs, addresses).

**Solution:** Use Microsoft Presidio for detection and redaction.

```python
# In ai/app/services/pii_redactor.py

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class PIIRedactor:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def redact_invoice(self, invoice_text: str) -> str:
        results = self.analyzer.analyze(
            text=invoice_text,
            entities=["US_SSN", "CREDIT_CARD", "PHONE_NUMBER", "EMAIL_ADDRESS"],
            language='en'
        )

        anonymized = self.anonymizer.anonymize(
            text=invoice_text,
            analyzer_results=results,
            operators={
                "US_SSN": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 5}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[REDACTED-CARD]"}),
            }
        )

        return anonymized.text
```text
---

## # 3.2 Row-Level Security (RLS)

**Problem:** Need to restrict access based on role and amount threshold.

**Solution:** Add RLS policies in D1.

```sql
-- In drizzle/migrations/xxxx_rls.sql

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

-- Policy: Only admins can approve invoices > $5k
CREATE POLICY "Admins can approve high-value invoices"
ON invoices FOR UPDATE
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.id = auth.uid()
    AND users.role = 'admin'
    AND (invoices.total_amount <= 5000 OR invoices.status != 'PENDING')
  )
);
```text
---

# # Phase 4: Integration (Week 4)

## # 4.1 Python AI Service

**Problem:** Cloudflare Workers can't run complex Python libraries (pdfplumber, presidio).

**Solution:** Split into two services:

```text
Cloudflare Workers          Python AI Service
┌─────────────────┐         ┌─────────────────┐
│ Hono API        │────gRPC──▶│ FastAPI         │
│ D1 DB           │         │ pdfplumber      │
│ R2 Storage      │         │ Presidio (PII)  │
└─────────────────┘         └─────────────────┘
```text
**Files to Create:**
- `ai/main.py` - FastAPI entry point
- `docker/Dockerfile.ai` - Container for AI service

---

# # Summary: Quick Wins

## # Can Do Today (30 min each)

| Task | Files to Create | Output |
| ------ | ----------------- | -------- |
| Math validation function | `worker/src/lib/critic.ts` | Detect math errors |
| Hard-coded math tests | `worker/src/tests/math.test.ts` | 5 test cases |
| PII redaction helper | `worker/src/lib/pii.ts` | Redact before logging |


## # This Week (1-2 days each)

| Task | Files to Create | Effort |
| ------ | ----------------- | -------- |
| PDF multi-page support | `ai/app/services/pdf_extractor.py` | 1 day |
| Critic Agent (math validation) | `ai/app/services/critic.py` | 1 day |
| DeepEval test suite | `ai/tests/test_evals.py` | 2 days |


## # Next Week

| Task | Files to Create | Effort |
| ------ | ----------------- | -------- |
| Playwright E2E tests | `worker/e2e/*.spec.ts` | 2 days |
| Python AI Docker | `ai/Dockerfile`, `docker-compose.yml` | 1 day |
| RLS policies | `drizzle/migrations/*_rls.sql` | 1 day |


---

# # Questions for Clarification

1. **PDF Handling:**
   - A) Offload to Python service (recommended)
   - B) Use Cloudflare Images OCR (paid)
   - C) Only single-page images for MVP

2. **LLM Provider:**
   - Stay with Cloudflare Workers AI (Llama)
   - Or add OpenAI GPT-4o for better accuracy

3. **Timeline:**
   - MVP (Quick Wins): This week
   - Beta (All phases): 4 weeks

   What's your target launch date?
