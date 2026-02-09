/**
 * Critic Agent - Math Validation Module
 *
 * Performs hard validation on extracted invoice data to catch LLM extraction errors.
 * This is the "second pair of eyes" that doesn't rely on LLMs for arithmetic.
 *
 * Run with: pnpm test -- src/tests/math.test.ts
 */

import { z } from "zod";

/**
 * Line item schema for validation
 */
export const LineItemSchema = z.object({
  description: z.string().optional(),
  quantity: z.number().positive().optional(),
  unitPrice: z.number().nonnegative().optional(),
  amount: z.number().nonnegative().optional(),
});

export type LineItem = z.infer<typeof LineItemSchema>;

/**
 * Extracted invoice data schema
 */
export const ExtractedInvoiceSchema = z.object({
  vendorName: z.string().optional(),
  invoiceNumber: z.string().optional(),
  invoiceDate: z.string().optional(), // ISO date string YYYY-MM-DD
  dueDate: z.string().optional(),
  totalAmount: z.number().nonnegative(),
  subtotal: z.number().nonnegative().optional(),
  tax: z.number().nonnegative().optional(),
  lineItems: z.array(LineItemSchema).optional(),
  currency: z.string().optional(),
});

export type ExtractedInvoice = z.infer<typeof ExtractedInvoiceSchema>;

/**
 * Validation signal for risk scoring
 */
export interface ValidationSignal {
  type: "MATH_ERROR" | "DATE_ERROR" | "DUPLICATE_LINE_ITEM" | "MISSING_DATA" | "VALIDATION_PASS";
  severity: "CRITICAL" | "WARNING" | "INFO";
  description: string;
  scoreContribution: number; // Points to add to risk score
  field?: string;
  expected?: string;
  actual?: string;
}

/**
 * Critic validation result
 */
export interface CriticResult {
  valid: boolean;
  errors: string[];
  signals: ValidationSignal[];
  correctedTotal?: number;
}

/**
 * Validate line item math: quantity * unit_price should equal amount
 */
export function validateLineItemMath(item: LineItem): ValidationSignal | null {
  const qty = item.quantity ?? 0;
  const unitPrice = item.unitPrice ?? 0;
  const declaredAmount = item.amount ?? 0;
  const calculatedAmount = Number((qty * unitPrice).toFixed(2));

  if (qty > 0 && unitPrice > 0 && declaredAmount > 0) {
    const difference = Math.abs(calculatedAmount - declaredAmount);

    if (difference > 0.01) {
      return {
        type: "MATH_ERROR",
        severity: "CRITICAL",
        description: `Line item math error: ${qty} x $${unitPrice.toFixed(2)} = $${calculatedAmount.toFixed(2)}, but declared as $${declaredAmount.toFixed(2)}`,
        scoreContribution: 25,
        field: "lineItem",
        expected: calculatedAmount.toFixed(2),
        actual: declaredAmount.toFixed(2),
      };
    }
  }

  return null;
}

/**
 * Validate that line items sum to declared total
 */
export function validateLineItemSum(
  lineItems: LineItem[],
  declaredTotal: number
): { signal: ValidationSignal | null; calculatedTotal: number } {
  let calculatedTotal = 0;

  for (const item of lineItems) {
    const amount = item.amount ?? (item.quantity ?? 0) * (item.unitPrice ?? 0);
    calculatedTotal += Number(amount.toFixed(2));
  }

  const difference = Math.abs(calculatedTotal - declaredTotal);

  if (difference > 0.02) {
    return {
      signal: {
        type: "MATH_ERROR",
        severity: "CRITICAL",
        description: `Total mismatch: Line items sum to $${calculatedTotal.toFixed(2)}, but total is $${declaredTotal.toFixed(2)} (diff: $${difference.toFixed(2)})`,
        scoreContribution: 50,
        field: "totalAmount",
        expected: calculatedTotal.toFixed(2),
        actual: declaredTotal.toFixed(2),
      },
      calculatedTotal,
    };
  }

  return { signal: null, calculatedTotal };
}

/**
 * Validate invoice date is not in the future
 */
export function validateInvoiceDate(invoiceDate: string): ValidationSignal | null {
  const invoice = new Date(invoiceDate);
  const today = new Date();
  today.setHours(23, 59, 59, 999); // End of today

  if (invoice > today) {
    return {
      type: "DATE_ERROR",
      severity: "WARNING",
      description: `Invoice date ${invoiceDate} is in the future`,
      scoreContribution: 20,
      field: "invoiceDate",
      expected: "today or earlier",
      actual: invoiceDate,
    };
  }

  return null;
}

/**
 * Validate due date is after invoice date
 */
export function validateDueDate(invoiceDate: string, dueDate: string): ValidationSignal | null {
  if (!invoiceDate || !dueDate) return null;

  const invoice = new Date(invoiceDate);
  const due = new Date(dueDate);

  if (due < invoice) {
    return {
      type: "DATE_ERROR",
      severity: "WARNING",
      description: `Due date ${dueDate} is before invoice date ${invoiceDate}`,
      scoreContribution: 15,
      field: "dueDate",
      expected: `after ${invoiceDate}`,
      actual: dueDate,
    };
  }

  return null;
}

/**
 * Check for duplicate line items (same description + amount)
 */
export function findDuplicateLineItems(lineItems: LineItem[]): ValidationSignal[] {
  const signals: ValidationSignal[] = [];
  const seen = new Map<string, number>();

  for (let i = 0; i < lineItems.length; i++) {
    const item = lineItems[i];
    if (!item.description) continue;

    const key = `${item.description.toLowerCase()}-${item.amount ?? 0}`;

    if (seen.has(key)) {
      const prevIndex = seen.get(key)!;
      signals.push({
        type: "DUPLICATE_LINE_ITEM",
        severity: "INFO",
        description: `Duplicate line item: "${item.description}" appears at positions ${prevIndex + 1} and ${i + 1}`,
        scoreContribution: 5,
        field: "lineItems",
      });
    } else {
      seen.set(key, i);
    }
  }

  return signals;
}

/**
 * Validate that all required fields are present
 */
function validateRequiredFields(data: ExtractedInvoice): ValidationSignal[] {
  const signals: ValidationSignal[] = [];
  const requiredFields = ["vendorName", "invoiceNumber", "invoiceDate", "totalAmount"] as const;

  for (const field of requiredFields) {
    const value = data[field as keyof ExtractedInvoice];
    if (!value || (typeof value === "string" && value.trim() === "")) {
      signals.push({
        type: "MISSING_DATA",
        severity: "CRITICAL",
        description: `Missing required field: ${field}`,
        scoreContribution: 30,
        field,
      });
    }
  }

  return signals;
}

/**
 * Critic Agent: Validate extracted invoice data
 *
 * This is the "Critic" in the Analyst-Critic pattern:
 * - Analyst Agent: Extracts data using LLM vision
 * - Critic Agent: Validates math and business rules (deterministic)
 *
 * @param data - Extracted invoice data from Analyst
 * @returns Validation result with signals for risk scoring
 */
export function validateExtraction(data: ExtractedInvoice): CriticResult {
  const errors: string[] = [];
  const signals: ValidationSignal[] = [];

  // 1. Check required fields
  const missingFieldSignals = validateRequiredFields(data);
  signals.push(...missingFieldSignals);
  if (missingFieldSignals.length > 0) {
    errors.push("Missing required fields in extracted data");
  }

  // 2. Validate invoice date
  if (data.invoiceDate) {
    const dateSignal = validateInvoiceDate(data.invoiceDate);
    if (dateSignal) {
      signals.push(dateSignal);
      errors.push("Invoice date is in the future");
    }
  }

  // 3. Validate due date vs invoice date
  if (data.invoiceDate && data.dueDate) {
    const dueDateSignal = validateDueDate(data.invoiceDate, data.dueDate);
    if (dueDateSignal) {
      signals.push(dueDateSignal);
      errors.push("Due date is before invoice date");
    }
  }

  // 4. Validate line item math
  if (data.lineItems && data.lineItems.length > 0) {
    for (let i = 0; i < data.lineItems.length; i++) {
      const item = data.lineItems[i];
      const lineSignal = validateLineItemMath(item);
      if (lineSignal) {
        lineSignal.description = `[Line ${i + 1}] ${lineSignal.description}`;
        signals.push(lineSignal);
        errors.push(`Math error in line item ${i + 1}`);
      }

      // Check for negative values
      if ((item.quantity ?? 0) < 0 || (item.unitPrice ?? 0) < 0 || (item.amount ?? 0) < 0) {
        signals.push({
          type: "MATH_ERROR",
          severity: "CRITICAL",
          description: `[Line ${i + 1}] Negative value detected in line item`,
          scoreContribution: 30,
          field: "lineItems",
        });
      }
    }

    // 5. Validate line item sum matches total
    const sumValidation = validateLineItemSum(data.lineItems, data.totalAmount);
    if (sumValidation.signal) {
      signals.push(sumValidation.signal);
      errors.push("Line items sum does not match declared total");
    }

    // 6. Check for duplicate line items
    const duplicateSignals = findDuplicateLineItems(data.lineItems);
    signals.push(...duplicateSignals);
  }

  // 7. Validate subtotal + tax = total (if both provided)
  if (data.subtotal !== undefined && data.tax !== undefined) {
    const expectedTotal = Number((data.subtotal + data.tax).toFixed(2));
    const actualTotal = data.totalAmount;
    const difference = Math.abs(expectedTotal - actualTotal);

    if (difference > 0.02) {
      signals.push({
        type: "MATH_ERROR",
        severity: "WARNING",
        description: `Subtotal + tax ($${expectedTotal.toFixed(2)}) != total ($${actualTotal.toFixed(2)})`,
        scoreContribution: 35,
        field: "totalAmount",
        expected: expectedTotal.toFixed(2),
        actual: actualTotal.toFixed(2),
      });
      errors.push("Subtotal + tax does not match total");
    }
  }

  // Determine overall validity
  const hasCriticalErrors = signals.some(s => s.severity === "CRITICAL");
  const valid = !hasCriticalErrors && errors.length === 0;

  // Calculate corrected total if needed
  let correctedTotal: number | undefined;
  if (data.lineItems && data.lineItems.length > 0) {
    correctedTotal = data.lineItems.reduce((sum, item) => {
      const amount = item.amount ?? (item.quantity ?? 0) * (item.unitPrice ?? 0);
      return sum + Number(amount.toFixed(2));
    }, 0);
  }

  return {
    valid,
    errors,
    signals: signals.sort((a, b) => b.scoreContribution - a.scoreContribution),
    correctedTotal: valid ? undefined : correctedTotal,
  };
}

/**
 * Calculate risk contribution from Critic signals
 */
export function calculateCriticRiskScore(signals: ValidationSignal[]): number {
  // Sum of CRITICAL signals, weighted by severity
  const severityWeights = {
    CRITICAL: 1.0,
    WARNING: 0.5,
    INFO: 0.25,
  };

  const totalScore = signals.reduce((sum, signal) => {
    const weight = severityWeights[signal.severity];
    return sum + (signal.scoreContribution * weight);
  }, 0);

  // Cap at 100
  return Math.min(100, totalScore);
}

/**
 * Generate a human-readable validation report
 */
export function generateValidationReport(result: CriticResult): string {
  const lines: string[] = [];

  if (result.valid) {
    lines.push("✅ **Validation Passed**");
    lines.push("");
    lines.push("All mathematical and business rule checks passed.");
  } else {
    lines.push("❌ **Validation Failed**");
    lines.push("");
    lines.push("Issues found:");
    lines.push("");

    const byType = result.signals.reduce((acc, signal) => {
      if (!acc[signal.type]) acc[signal.type] = [];
      acc[signal.type].push(signal);
      return acc;
    }, {} as Record<string, ValidationSignal[]>);

    for (const [type, typeSignals] of Object.entries(byType)) {
      lines.push(`**${type}**`);
      for (const signal of typeSignals) {
        lines.push(`- [${signal.severity}] ${signal.description}`);
      }
      lines.push("");
    }

    if (result.correctedTotal !== undefined) {
      lines.push(`_Calculated total: $${result.correctedTotal.toFixed(2)}_`);
    }
  }

  return lines.join("\n");
}
