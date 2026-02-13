/**
 * Critic Agent Math Validation Tests
 *
 * Hard-coded tests for the Critic's mathematical validation.
 * These tests do NOT rely on LLMs - pure deterministic math.
 *
 * Run with: pnpm test -- src/tests/math.test.ts
 * Coverage: pnpm test --coverage -- src/tests/math.test.ts
 */

import { describe, it, expect } from "vitest";
import {
  validateExtraction,
  validateLineItemMath,
  validateLineItemSum,
  validateInvoiceDate,
  validateDueDate,
  findDuplicateLineItems,
  calculateCriticRiskScore,
  generateValidationReport,
  LineItemSchema,
  ExtractedInvoiceSchema,
  type ExtractedInvoice,
  type LineItem,
} from "../lib/critic";

// ============================================================================
// Test Fixtures
// ============================================================================

const VALID_INVOICE: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-001",
  invoiceDate: "2024-01-15",
  dueDate: "2024-02-15",
  totalAmount: 500.00,
  subtotal: 454.55,
  tax: 45.45,
  lineItems: [
    { description: "Widget A", quantity: 10, unitPrice: 25.00, amount: 250.00 },
    { description: "Widget B", quantity: 5, unitPrice: 50.00, amount: 250.00 },
  ],
  currency: "USD",
};

const INVOICE_MATH_ERROR: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-002",
  invoiceDate: "2024-01-15",
  totalAmount: 500.00, // Wrong: should be 250
  lineItems: [
    { description: "Widget A", quantity: 10, unitPrice: 25.00, amount: 250.00 },
  ],
};

const INVOICE_LINE_ITEM_MATH_ERROR: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-003",
  invoiceDate: "2024-01-15",
  totalAmount: 250.00,
  lineItems: [
    { description: "Widget A", quantity: 10, unitPrice: 25.00, amount: 200.00 }, // Wrong: should be 250
  ],
};

const INVOICE_FUTURE_DATE: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-004",
  invoiceDate: new Date(Date.now() + 86400000 * 7).toISOString().split("T")[0], // 7 days from now
  totalAmount: 100.00,
};

const INVOICE_DUE_DATE_ERROR: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-005",
  invoiceDate: "2024-02-15",
  dueDate: "2024-01-01", // Before invoice date
  totalAmount: 100.00,
};

const INVOICE_DUPLICATE_LINE_ITEMS: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-006",
  invoiceDate: "2024-01-15",
  totalAmount: 300.00,
  lineItems: [
    { description: "Widget A", quantity: 5, unitPrice: 25.00, amount: 125.00 },
    { description: "Widget B", quantity: 3, unitPrice: 25.00, amount: 75.00 },
    { description: "Widget A", quantity: 5, unitPrice: 25.00, amount: 125.00 }, // Duplicate of first
  ],
};

const INVOICE_TAX_MISMATCH: ExtractedInvoice = {
  vendorName: "Acme Corp",
  invoiceNumber: "INV-007",
  invoiceDate: "2024-01-15",
  totalAmount: 500.00, // Wrong: 454.55 + 45.45 = 500, so this is actually correct
  subtotal: 454.55,
  tax: 50.00, // Wrong: should be 45.45
};

// ============================================================================
// Core Math Validation Tests
// ============================================================================

describe("Line Item Math Validation", () => {
  it("should pass for correct line item math", () => {
    const item: LineItem = {
      description: "Widget A",
      quantity: 10,
      unitPrice: 25.00,
      amount: 250.00,
    };

    const result = validateLineItemMath(item);
    expect(result).toBeNull();
  });

  it("should detect incorrect line item math", () => {
    const item: LineItem = {
      description: "Widget A",
      quantity: 10,
      unitPrice: 25.00,
      amount: 200.00, // Wrong: should be 250
    };

    const result = validateLineItemMath(item);

    expect(result).not.toBeNull();
    expect(result?.type).toBe("MATH_ERROR");
    expect(result?.severity).toBe("CRITICAL");
    expect(result?.scoreContribution).toBe(25);
    expect(result?.field).toBe("lineItem");
  });

  it("should handle zero quantity gracefully", () => {
    const item: LineItem = {
      description: "Widget A",
      quantity: 0,
      unitPrice: 25.00,
      amount: 0,
    };

    const result = validateLineItemMath(item);
    expect(result).toBeNull();
  });

  it("should handle missing amount (partial data)", () => {
    const item: LineItem = {
      description: "Widget A",
      quantity: 10,
      unitPrice: 25.00,
      // amount is undefined
    };

    const result = validateLineItemMath(item);
    expect(result).toBeNull();
  });
});

describe("Line Item Sum Validation", () => {
  it("should pass when line items sum matches total", () => {
    const lineItems: LineItem[] = [
      { description: "A", quantity: 1, unitPrice: 100, amount: 100 },
      { description: "B", quantity: 1, unitPrice: 50, amount: 50 },
    ];

    const { signal, calculatedTotal } = validateLineItemSum(lineItems, 150);

    expect(signal).toBeNull();
    expect(calculatedTotal).toBe(150);
  });

  it("should detect sum mismatch", () => {
    const lineItems: LineItem[] = [
      { description: "A", amount: 100 },
      { description: "B", amount: 50 },
    ];

    const { signal, calculatedTotal } = validateLineItemSum(lineItems, 200); // Should be 150

    expect(signal).not.toBeNull();
    expect(signal?.type).toBe("MATH_ERROR");
    expect(signal?.severity).toBe("CRITICAL");
    expect(signal?.scoreContribution).toBe(50);
    expect(calculatedTotal).toBe(150);
  });

  it("should handle empty line items", () => {
    const lineItems: LineItem[] = [];

    const { signal, calculatedTotal } = validateLineItemSum(lineItems, 0);

    expect(signal).toBeNull();
    expect(calculatedTotal).toBe(0);
  });
});

// ============================================================================
// Date Validation Tests
// ============================================================================

describe("Date Validation", () => {
  it("should pass for past invoice date", () => {
    const result = validateInvoiceDate("2024-01-15");
    expect(result).toBeNull();
  });

  it("should detect future invoice date", () => {
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 7);
    const futureDateStr = futureDate.toISOString().split("T")[0];

    const result = validateInvoiceDate(futureDateStr);

    expect(result).not.toBeNull();
    expect(result?.type).toBe("DATE_ERROR");
    expect(result?.severity).toBe("WARNING");
    expect(result?.scoreContribution).toBe(20);
  });

  it("should validate due date is after invoice date", () => {
    const result = validateDueDate("2024-02-15", "2024-03-15");
    expect(result).toBeNull();
  });

  it("should detect due date before invoice date", () => {
    const result = validateDueDate("2024-02-15", "2024-01-01");

    expect(result).not.toBeNull();
    expect(result?.type).toBe("DATE_ERROR");
    expect(result?.severity).toBe("WARNING");
  });
});

// ============================================================================
// Duplicate Detection Tests
// ============================================================================

describe("Duplicate Line Item Detection", () => {
  it("should pass with unique line items", () => {
    const lineItems: LineItem[] = [
      { description: "Widget A", amount: 100 },
      { description: "Widget B", amount: 50 },
    ];

    const result = findDuplicateLineItems(lineItems);
    expect(result).toHaveLength(0);
  });

  it("should detect duplicate line items", () => {
    const lineItems: LineItem[] = [
      { description: "Widget A", amount: 100 },
      { description: "Widget B", amount: 50 },
      { description: "Widget A", amount: 100 }, // Duplicate
    ];

    const result = findDuplicateLineItems(lineItems);

    expect(result).toHaveLength(1);
    expect(result[0]?.type).toBe("DUPLICATE_LINE_ITEM");
    expect(result[0]?.severity).toBe("INFO");
  });

  it("should handle case-insensitive duplicate detection", () => {
    const lineItems: LineItem[] = [
      { description: "widget a", amount: 100 },
      { description: "WIDGET A", amount: 100 }, // Should match
    ];

    const result = findDuplicateLineItems(lineItems);
    expect(result).toHaveLength(1);
  });
});

// ============================================================================
// Full Validation Tests
// ============================================================================

describe("Full Invoice Validation", () => {
  it("should pass for valid invoice", () => {
    const result = validateExtraction(VALID_INVOICE);

    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
    expect(result.signals).toHaveLength(0);
  });

  it("should detect line item math errors", () => {
    const result = validateExtraction(INVOICE_LINE_ITEM_MATH_ERROR);

    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.signals.some(s => s.type === "MATH_ERROR")).toBe(true);
  });

  it("should detect total sum mismatch", () => {
    const result = validateExtraction(INVOICE_MATH_ERROR);

    expect(result.valid).toBe(false);
    expect(result.signals.some(s => s.type === "MATH_ERROR")).toBe(true);
  });

  it("should detect future invoice date", () => {
    const result = validateExtraction(INVOICE_FUTURE_DATE);

    expect(result.valid).toBe(false);
    expect(result.signals.some(s => s.type === "DATE_ERROR")).toBe(true);
  });

  it("should detect due date error", () => {
    const result = validateExtraction(INVOICE_DUE_DATE_ERROR);

    expect(result.valid).toBe(false);
    expect(result.signals.some(s => s.type === "DATE_ERROR")).toBe(true);
  });

  it("should detect duplicate line items", () => {
    const result = validateExtraction(INVOICE_DUPLICATE_LINE_ITEMS);

    expect(result.signals.some(s => s.type === "DUPLICATE_LINE_ITEM")).toBe(true);
  });

  it("should detect tax mismatch", () => {
    const result = validateExtraction(INVOICE_TAX_MISMATCH);

    expect(result.valid).toBe(false);
    expect(result.signals.some(s => s.type === "MATH_ERROR")).toBe(true);
  });

  it("should correct total calculation", () => {
    const result = validateExtraction(INVOICE_MATH_ERROR);

    expect(result.correctedTotal).toBeDefined();
    expect(result.correctedTotal).toBe(250);
  });
});

// ============================================================================
// Schema Validation Tests
// ============================================================================

describe("Schema Validation", () => {
  it("should parse valid line item", () => {
    const item = {
      description: "Widget A",
      quantity: 10,
      unitPrice: 25.00,
      amount: 250.00,
    };

    const parsed = LineItemSchema.parse(item);
    expect(parsed.description).toBe("Widget A");
    expect(parsed.quantity).toBe(10);
  });

  it("should reject negative quantity", () => {
    const item = {
      description: "Widget A",
      quantity: -10,
      unitPrice: 25.00,
      amount: 250.00,
    };

    expect(() => LineItemSchema.parse(item)).toThrow();
  });

  it("should parse valid invoice", () => {
    const parsed = ExtractedInvoiceSchema.parse(VALID_INVOICE);
    expect(parsed.vendorName).toBe("Acme Corp");
    expect(parsed.totalAmount).toBe(500);
    expect(parsed.lineItems).toHaveLength(2);
  });
});

// ============================================================================
// Risk Score Calculation Tests
// ============================================================================

describe("Risk Score Calculation", () => {
  it("should calculate zero risk for no signals", () => {
    const score = calculateCriticRiskScore([]);
    expect(score).toBe(0);
  });

  it("should calculate risk score from signals", () => {
    const signals = [
      { type: "MATH_ERROR" as const, severity: "CRITICAL" as const, description: "Error", scoreContribution: 50 },
      { type: "DATE_ERROR" as const, severity: "WARNING" as const, description: "Warning", scoreContribution: 20 },
    ];

    const score = calculateCriticRiskScore(signals);

    // Critical: 50 * 1.0 = 50, Warning: 20 * 0.5 = 10, Total = 60
    expect(score).toBe(60);
  });

  it("should cap risk score at 100", () => {
    const signals = [
      { type: "MATH_ERROR" as const, severity: "CRITICAL" as const, description: "Error", scoreContribution: 80 },
      { type: "MATH_ERROR" as const, severity: "CRITICAL" as const, description: "Error", scoreContribution: 80 },
    ];

    const score = calculateCriticRiskScore(signals);
    expect(score).toBe(100);
  });
});

// ============================================================================
// Report Generation Tests
// ============================================================================

describe("Validation Report Generation", () => {
  it("should generate success report", () => {
    const result = validateExtraction(VALID_INVOICE);
    const report = generateValidationReport(result);

    expect(report).toContain("Validation Passed");
  });

  it("should generate failure report", () => {
    const result = validateExtraction(INVOICE_MATH_ERROR);
    const report = generateValidationReport(result);

    expect(report).toContain("Validation Failed");
    expect(report).toContain("MATH_ERROR");
  });
});

// ============================================================================
// Edge Cases
// ============================================================================

describe("Edge Cases", () => {
  it("should handle invoice with no line items", () => {
    const invoice: ExtractedInvoice = {
      vendorName: "Acme Corp",
      invoiceNumber: "INV-NO-LINES",
      invoiceDate: "2024-01-15",
      totalAmount: 100.00,
    };

    const result = validateExtraction(invoice);
    expect(result.valid).toBe(true);
  });

  it("should handle missing optional fields", () => {
    const invoice: ExtractedInvoice = {
      totalAmount: 100.00,
    };

    const result = validateExtraction(invoice);

    expect(result.valid).toBe(false);
    expect(result.signals.some(s => s.type === "MISSING_DATA")).toBe(true);
  });

  it("should handle very large invoice amounts", () => {
    const invoice: ExtractedInvoice = {
      vendorName: "Big Corp",
      invoiceNumber: "INV-BIG",
      invoiceDate: "2024-01-15",
      totalAmount: 999999999.99,
      lineItems: [
        { description: "Big purchase", quantity: 1, unitPrice: 999999999.99, amount: 999999999.99 },
      ],
    };

    const result = validateExtraction(invoice);
    expect(result.valid).toBe(true);
  });

  it("should handle decimal precision edge cases", () => {
    const invoice: ExtractedInvoice = {
      vendorName: "Precise Corp",
      invoiceNumber: "INV-PRECISE",
      invoiceDate: "2024-01-15",
      totalAmount: 0.33, // 0.11 + 0.11 + 0.11 = 0.33 (exact in floating point)
      lineItems: [
        { description: "A", quantity: 1, unitPrice: 0.11, amount: 0.11 },
        { description: "B", quantity: 1, unitPrice: 0.11, amount: 0.11 },
        { description: "C", quantity: 1, unitPrice: 0.11, amount: 0.11 },
      ],
    };

    const result = validateExtraction(invoice);
    // Should pass with clean decimal math
    expect(result.signals.filter(s => s.type === "MATH_ERROR")).toHaveLength(0);
  });
});
