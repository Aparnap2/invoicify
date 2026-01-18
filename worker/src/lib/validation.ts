/**
 * Zod Validation Schemas for API Endpoints
 *
 * All API inputs should be validated using these schemas
 * before processing. This provides:
 * - Type safety at runtime
 * - Clear error messages
 * - Documentation of expected input formats
 */

import { z } from "zod";

// ============================================================================
// Common Schemas
// ============================================================================

/**
 * UUID validation
 */
export const uuidSchema = z.string().uuid();

/**
 * Currency code (ISO 4217)
 */
export const currencySchema = z.string().length(3).default("USD");

/**
 * Positive amount validation
 */
export const amountSchema = z.number().positive().multipleOf(0.01);

/**
 * Date string (ISO 8601)
 */
export const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

// ============================================================================
// Invoice Schemas
// ============================================================================

/**
 * Create invoice request
 */
export const createInvoiceSchema = z.object({
  vendorName: z.string().min(1).max(255),
  vendorId: uuidSchema.optional(),
  invoiceNumber: z.string().min(1).max(50).optional(),
  amount: amountSchema,
  currency: currencySchema.optional(),
  dueDate: dateSchema.optional(),
  issueDate: dateSchema.optional(),
  rawText: z.string().max(10000).optional(),
  lineItems: z.array(z.object({
    description: z.string().min(1).max(500),
    quantity: z.number().positive(),
    unitPrice: amountSchema,
    totalPrice: amountSchema,
  })).optional(),
});

/**
 * Update invoice status
 */
export const updateInvoiceStatusSchema = z.object({
  status: z.enum(["NEW", "EXTRACTED", "VALIDATED", "ASSESSED", "PENDING", "APPROVED", "REJECTED", "PAID"]),
});

/**
 * HITL Approval request
 */
export const approvalSchema = z.object({
  decision: z.enum(["approved", "rejected"]),
  approver: z.string().email().optional(),
  reason: z.string().max(1000).optional(),
  confidenceOverride: z.boolean().default(false),
});

// ============================================================================
// Workflow Schemas
// ============================================================================

/**
 * Start workflow request
 */
export const startWorkflowSchema = createInvoiceSchema.extend({
  priority: z.enum(["low", "normal", "high", "urgent"]).default("normal"),
  skipRiskAnalysis: z.boolean().default(false),
  autoApproveThreshold: amountSchema.optional(),
});

/**
 * Continue workflow after HITL
 */
export const continueWorkflowSchema = z.object({
  decision: z.enum(["approved", "rejected", "re-schedule"]),
  approver: z.string().min(1),
  reason: z.string().max(1000).optional(),
});

// ============================================================================
// Slack Schemas
// ============================================================================

/**
 * Slack interaction payload
 */
export const slackInteractionSchema = z.object({
  type: z.literal("block_actions"),
  user: z.object({
    id: z.string(),
    username: z.string().optional(),
  }).optional(),
  actions: z.array(z.object({
    action_id: z.string(),
    value: z.string().optional(),
    type: z.string(),
  })).optional(),
  response_url: z.string().url().optional(),
});

// ============================================================================
// Vendor Schemas
// ============================================================================

/**
 * Create vendor request
 */
export const createVendorSchema = z.object({
  name: z.string().min(1).max(255),
  category: z.string().min(1).max(100),
  contactEmail: z.string().email().optional(),
  paymentTerms: z.number().int().min(0).max(120).default(30),
  riskLevel: z.enum(["LOW", "MEDIUM", "HIGH"]).default("MEDIUM"),
  avgInvoiceAmount: amountSchema.optional(),
  contractTerms: z.string().max(5000).optional(),
});

/**
 * Update vendor request
 */
export const updateVendorSchema = createVendorSchema.partial();

// ============================================================================
// Risk Schemas
// ============================================================================

/**
 * Risk feedback submission
 */
export const riskFeedbackSchema = z.object({
  invoiceId: uuidSchema,
  actualRisk: z.enum(["LOW", "MEDIUM", "HIGH", "FRAUDULENT"]),
  wasCorrect: z.boolean(),
  notes: z.string().max(1000).optional(),
});

// ============================================================================
// Pagination Schemas
// ============================================================================

/**
 * Pagination parameters
 */
export const paginationSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(20),
});

/**
 * Pagination response
 */
export const paginationResponseSchema = <T extends z.ZodType>(dataSchema: T) =>
  z.object({
    data: z.array(dataSchema),
    pagination: z.object({
      page: z.number(),
      limit: z.number(),
      total: z.number(),
      totalPages: z.number(),
    }),
  });

// ============================================================================
// Query Schemas
// ============================================================================

/**
 * Date range query
 */
export const dateRangeSchema = z.object({
  startDate: dateSchema.optional(),
  endDate: dateSchema.optional(),
});

/**
 * Invoice list query
 */
export const invoiceListQuerySchema = paginationSchema.extend({
  status: z.enum(["NEW", "EXTRACTED", "VALIDATED", "ASSESSED", "PENDING", "APPROVED", "REJECTED", "PAID"]).optional(),
  vendorId: uuidSchema.optional(),
  minAmount: amountSchema.optional(),
  maxAmount: amountSchema.optional(),
  sortBy: z.enum(["createdAt", "amount", "dueDate"]).default("createdAt"),
  sortOrder: z.enum(["asc", "desc"]).default("desc"),
});

// ============================================================================
// Validation Helpers
// ============================================================================

/**
 * Validate request body against schema
 * Returns { success: true, data: T } or { success: false, errors: string[] }
 */
export function validateBody<T>(
  body: unknown,
  schema: z.ZodSchema<T>
): { success: true; data: T } | { success: false; errors: string[] } {
  const result = schema.safeParse(body);
  if (result.success) {
    return { success: true, data: result.data };
  }
  return {
    success: false,
    errors: result.error.errors.map(e => `${e.path.join(".")}: ${e.message}`),
  };
}

/**
 * Validate query params against schema
 */
export function validateQuery<T>(
  query: Record<string, unknown>,
  schema: z.ZodSchema<T>
): { success: true; data: T } | { success: false; errors: string[] } {
  const result = schema.safeParse(query);
  if (result.success) {
    return { success: true, data: result.data };
  }
  return {
    success: false,
    errors: result.error.errors.map(e => `${e.path.join(".")}: ${e.message}`),
  };
}

// ============================================================================
// Export all schemas for convenience
// ============================================================================

export const schemas = {
  uuid: uuidSchema,
  currency: currencySchema,
  amount: amountSchema,
  date: dateSchema,
  createInvoice: createInvoiceSchema,
  updateInvoiceStatus: updateInvoiceStatusSchema,
  approval: approvalSchema,
  startWorkflow: startWorkflowSchema,
  continueWorkflow: continueWorkflowSchema,
  slackInteraction: slackInteractionSchema,
  createVendor: createVendorSchema,
  updateVendor: updateVendorSchema,
  riskFeedback: riskFeedbackSchema,
  pagination: paginationSchema,
  dateRange: dateRangeSchema,
  invoiceListQuery: invoiceListQuerySchema,
};
