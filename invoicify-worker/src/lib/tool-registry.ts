/**
 * Tool Registry - Agent Action Definitions
 *
 * Defines all tools/actions the agent can invoke with:
 * - Parameter schemas (Zod-like)
 * - Preconditions
 * - Postconditions
 * - Audit logging requirements
 */

import { getDb, schema } from "../db";
import type { Env } from "../db";
import { eq } from "drizzle-orm";

// ============================================================================
// TOOL DEFINITIONS
// ============================================================================

export type ToolName =
  | "approve_invoice"
  | "reject_invoice"
  | "delay_payment"
  | "schedule_payment"
  | "post_to_ledger"
  | "sync_to_quickbooks"
  | "create_vendor"
  | "update_vendor"
  | "flag_for_review"
  | "notify_founder";

export interface ToolDefinition {
  name: ToolName;
  description: string;
  parameters: Record<string, {
    type: "string" | "number" | "boolean";
    required: boolean;
    description: string;
  }>;
  preconditions: Array<{
    check: string;
    message: string;
  }>;
  postconditions: Array<{
    check: string;
    message: string;
  }>;
  auditEvent: string;
  autoApproveEligible: boolean;
}

export const TOOL_REGISTRY: Record<ToolName, ToolDefinition> = {
  approve_invoice: {
    name: "approve_invoice",
    description: "Auto-approve low-risk invoice for payment",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID to approve" },
      amount: { type: "number", required: true, description: "Payment amount" },
      vendorId: { type: "string", required: true, description: "Vendor ID" },
    },
    preconditions: [
      { check: "riskScore < 0.3", message: "Invoice risk must be below threshold" },
      { check: "trustLevel >= 2", message: "Vendor must be at Standard trust or higher" },
      { check: "amount <= autoApproveThreshold", message: "Amount must be within auto-approve limit" },
      { check: "invoice.status === 'VALIDATED'", message: "Invoice must be validated" },
    ],
    postconditions: [
      { check: "invoice.status === 'APPROVED'", message: "Invoice should be marked approved" },
      { check: "payment.scheduledDate is set", message: "Payment should be scheduled" },
    ],
    auditEvent: "INVOICE_AUTO_APPROVED",
    autoApproveEligible: true,
  },

  reject_invoice: {
    name: "reject_invoice",
    description: "Reject invoice with reason (fraud/duplicate/error)",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID to reject" },
      reason: { type: "string", required: true, description: "Rejection reason" },
      severity: { type: "string", required: true, description: "Severity: fraud | duplicate | error" },
    },
    preconditions: [
      { check: "invoice exists", message: "Invoice must exist" },
      { check: "reason is not empty", message: "Rejection reason required" },
    ],
    postconditions: [
      { check: "invoice.status === 'REJECTED'", message: "Invoice should be marked rejected" },
      { check: "rejectionReason recorded", message: "Rejection reason should be logged" },
    ],
    auditEvent: "INVOICE_REJECTED",
    autoApproveEligible: false,
  },

  delay_payment: {
    name: "delay_payment",
    description: "Reschedule payment to optimize cash flow",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID" },
      newDate: { type: "string", required: true, description: "New scheduled date (ISO)" },
      reason: { type: "string", required: true, description: "Reason for delay" },
    },
    preconditions: [
      { check: "invoice.dueDate > newDate OR runway < threshold", message: "Delay must have valid reason" },
      { check: "newDate <= invoice.dueDate + 30", message: "Delay cannot exceed 30 days" },
    ],
    postconditions: [
      { check: "payment.scheduledDate === newDate", message: "Payment should be rescheduled" },
      { check: "delayReason recorded", message: "Delay reason should be logged" },
    ],
    auditEvent: "PAYMENT_DELAYED",
    autoApproveEligible: false,
  },

  schedule_payment: {
    name: "schedule_payment",
    description: "Schedule invoice for payment on due date or optimal date",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID" },
      scheduledDate: { type: "string", required: true, description: "Payment date (ISO)" },
      amount: { type: "number", required: true, description: "Payment amount" },
    },
    preconditions: [
      { check: "invoice.status === 'APPROVED'", message: "Invoice must be approved" },
      { check: "scheduledDate <= invoice.dueDate", message: "Must be on or before due date" },
      { check: "cash >= amount + safetyBuffer", message: "Must have sufficient cash" },
    ],
    postconditions: [
      { check: "payment record created", message: "Payment record should be created" },
      { check: "payment.status === 'scheduled'", message: "Payment should be scheduled" },
    ],
    auditEvent: "PAYMENT_SCHEDULED",
    autoApproveEligible: true,
  },

  post_to_ledger: {
    name: "post_to_ledger",
    description: "Record approved invoice in internal ledger",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID" },
      glCode: { type: "string", required: true, description: "GL code for accounting" },
      notes: { type: "string", required: false, description: "Optional notes" },
    },
    preconditions: [
      { check: "invoice.status === 'APPROVED'", message: "Invoice must be approved" },
      { check: "glCode is valid", message: "GL code must be valid format" },
    ],
    postconditions: [
      { check: "ledgerEntry created", message: "Ledger entry should be created" },
      { check: "invoice.status === 'PENDING'", message: "Invoice should be pending payment" },
    ],
    auditEvent: "LEDGER_POSTED",
    autoApproveEligible: true,
  },

  sync_to_quickbooks: {
    name: "sync_to_quickbooks",
    description: "Sync invoice/payment to QuickBooks",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID" },
      entityType: { type: "string", required: true, description: "bill | payment | invoice" },
    },
    preconditions: [
      { check: "QuickBooks connected", message: "QuickBooks must be configured" },
      { check: "vendor has quickbooksId", message: "Vendor must have QB mapping" },
    ],
    postconditions: [
      { check: "syncQueue entry created", message: "Sync queue entry should be created" },
      { check: "invoice.quickbooksId set", message: "QuickBooks ID should be recorded" },
    ],
    auditEvent: "QUICKBOOKS_SYNC_QUEUED",
    autoApproveEligible: false,
  },

  create_vendor: {
    name: "create_vendor",
    description: "Create new vendor record",
    parameters: {
      name: { type: "string", required: true, description: "Vendor name" },
      email: { type: "string", required: false, description: "Vendor email" },
      taxId: { type: "string", required: false, description: "Tax ID" },
      address: { type: "string", required: false, description: "Vendor address" },
    },
    preconditions: [
      { check: "name is not empty", message: "Vendor name required" },
      { check: "no existing vendor with same name", message: "Vendor should not already exist" },
    ],
    postconditions: [
      { check: "vendor record created", message: "Vendor should be created" },
      { check: "trustBattery entry created", message: "Trust battery entry should be created" },
    ],
    auditEvent: "VENDOR_CREATED",
    autoApproveEligible: false,
  },

  update_vendor: {
    name: "update_vendor",
    description: "Update vendor information",
    parameters: {
      vendorId: { type: "string", required: true, description: "Vendor ID" },
      field: { type: "string", required: true, description: "Field to update" },
      value: { type: "string", required: true, description: "New value" },
    },
    preconditions: [
      { check: "vendor exists", message: "Vendor must exist" },
      { check: "field is updatable", message: "Field must be valid" },
    ],
    postconditions: [
      { check: "vendor.updatedAt updated", message: "Vendor should be updated" },
    ],
    auditEvent: "VENDOR_UPDATED",
    autoApproveEligible: false,
  },

  flag_for_review: {
    name: "flag_for_review",
    description: "Flag invoice for human review",
    parameters: {
      invoiceId: { type: "string", required: true, description: "Invoice ID" },
      reason: { type: "string", required: true, description: "Reason for review" },
      priority: { type: "string", required: true, description: "URGENT | NORMAL" },
    },
    preconditions: [
      { check: "invoice exists", message: "Invoice must exist" },
      { check: "reason is not empty", message: "Review reason required" },
    ],
    postconditions: [
      { check: "invoice.status === 'PENDING'", message: "Invoice should be pending" },
      { check: "approval request created", message: "Approval request should be created" },
    ],
    auditEvent: "INVOICE_FLAGGED_FOR_REVIEW",
    autoApproveEligible: false,
  },

  notify_founder: {
    name: "notify_founder",
    description: "Send notification to founder about critical items",
    parameters: {
      type: { type: "string", required: true, description: "alert_type" },
      message: { type: "string", required: true, description: "Notification message" },
      invoiceId: { type: "string", required: false, description: "Related invoice" },
    },
    preconditions: [
      { check: "type is valid", message: "Alert type must be valid" },
      { check: "message is not empty", message: "Message required" },
    ],
    postconditions: [
      { check: "notification queued", message: "Notification should be queued" },
    ],
    auditEvent: "FOUNDER_NOTIFIED",
    autoApproveEligible: false,
  },
};

// ============================================================================
// TOOL EXECUTION ENGINE
// ============================================================================

export interface ToolExecutionContext {
  env: Env;
  traceId: string;
  operator: "AGENT" | "HUMAN";
  operatorId?: string;
}

export interface ToolResult {
  success: boolean;
  toolName: ToolName;
  data?: Record<string, unknown>;
  error?: string;
  auditLogId?: string;
}

/**
 * Execute a tool with validation and audit logging
 */
export async function executeTool(
  context: ToolExecutionContext,
  toolName: ToolName,
  params: Record<string, unknown>
): Promise<ToolResult> {
  const db = getDb(context.env);
  const tool = TOOL_REGISTRY[toolName];

  if (!tool) {
    return { success: false, toolName, error: `Unknown tool: ${toolName}` };
  }

  // Validate parameters
  const missingParams = Object.entries(tool.parameters)
    .filter(([key, schema]) => schema.required && !params[key])
    .map(([key]) => key);

  if (missingParams.length > 0) {
    return { success: false, toolName, error: `Missing required params: ${missingParams.join(", ")}` };
  }

  // Create audit log entry
  const auditLogId = crypto.randomUUID();
  await db.insert(schema.auditLogs).values({
    id: auditLogId,
    action: tool.auditEvent,
    entityType: "TOOL_EXECUTION",
    entityId: params.invoiceId as string || params.vendorId as string || "system",
    performedBy: context.operator,
    performedAt: new Date().toISOString(),
    metadata: JSON.stringify({ toolName, params, traceId: context.traceId }),
  });

  // Execute tool-specific logic
  try {
    const result = await executeToolLogic(context, toolName, params);

    // Update audit log with success
    try {
      await db
        .update(schema.auditLogs)
        .set({
          changes: JSON.stringify({ success: true, result }),
        })
        .where(eq(schema.auditLogs.id, auditLogId));
    } catch (auditError) {
      console.error(`[tool-registry] Failed to update audit log for ${toolName}:`, auditError);
    }

    return { success: true, toolName, data: result as Record<string, unknown>, auditLogId };
  } catch (error) {
    // Update audit log with failure
    try {
      await db
        .update(schema.auditLogs)
        .set({
          changes: JSON.stringify({ success: false, error: (error as Error).message }),
        })
        .where(eq(schema.auditLogs.id, auditLogId));
    } catch (auditError) {
      console.error(`[tool-registry] Failed to update audit log for ${toolName}:`, auditError);
    }

    return { success: false, toolName, error: (error as Error).message, auditLogId };
  }
}

/**
 * Tool-specific execution logic
 */
async function executeToolLogic(
  context: ToolExecutionContext,
  toolName: ToolName,
  params: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const db = getDb(context.env);

  switch (toolName) {
    case "approve_invoice": {
      const invoiceId = params.invoiceId as string;
      const amount = params.amount as number;
      const vendorId = params.vendorId as string;

      // Update invoice status
      await db
        .update(schema.invoices)
        .set({
          status: "APPROVED" as const,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, invoiceId));

      // Create payment record
      const paymentId = crypto.randomUUID();
      const dueDate = (await db
        .select({ dueDate: schema.invoices.dueDate })
        .from(schema.invoices)
        .where(eq(schema.invoices.id, invoiceId))
        .limit(1))[0]?.dueDate;

      await db.insert(schema.payments).values({
        id: paymentId,
        invoiceId,
        scheduledDate: dueDate || new Date().toISOString().split("T")[0],
        amount,
        status: "scheduled",
        createdAt: new Date().toISOString(),
      });

      return { invoiceId, paymentId, status: "approved" };
    }

    case "reject_invoice": {
      const invoiceId = params.invoiceId as string;
      const reason = params.reason as string;
      const severity = params.severity as string;

      await db
        .update(schema.invoices)
        .set({
          status: "REJECTED" as const,
          rejectionReason: reason,
          rejectionSeverity: severity,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, invoiceId));

      return { invoiceId, reason, severity, status: "rejected" };
    }

    case "schedule_payment": {
      const invoiceId = params.invoiceId as string;
      const scheduledDate = params.scheduledDate as string;
      const amount = params.amount as number;

      const paymentId = crypto.randomUUID();
      await db.insert(schema.payments).values({
        id: paymentId,
        invoiceId,
        scheduledDate,
        amount,
        status: "scheduled",
        createdAt: new Date().toISOString(),
      });

      await db
        .update(schema.invoices)
        .set({ status: "PENDING" as const, updatedAt: new Date().toISOString() })
        .where(eq(schema.invoices.id, invoiceId));

      return { invoiceId, paymentId, scheduledDate, status: "scheduled" };
    }

    case "flag_for_review": {
      const invoiceId = params.invoiceId as string;
      const reason = params.reason as string;
      const priority = params.priority as "URGENT" | "NORMAL";

      await db
        .update(schema.invoices)
        .set({ status: "PENDING" as const, updatedAt: new Date().toISOString() })
        .where(eq(schema.invoices.id, invoiceId));

      const approvalId = crypto.randomUUID();
      await db.insert(schema.approvals).values({
        id: approvalId,
        invoiceId,
        approverEmail: "founder", // Would be dynamic in production
        status: "PENDING" as const,
        comments: reason,
        createdAt: new Date().toISOString(),
      });

      return { invoiceId, approvalId, priority, status: "pending_review" };
    }

    case "post_to_ledger": {
      const invoiceId = params.invoiceId as string;
      const glCode = params.glCode as string;
      const notes = params.notes as string | undefined;

      await db
        .update(schema.invoices)
        .set({ status: "PENDING" as const, updatedAt: new Date().toISOString() })
        .where(eq(schema.invoices.id, invoiceId));

      return { invoiceId, glCode, notes, status: "posted" };
    }

    case "delay_payment":
    case "sync_to_quickbooks":
    case "create_vendor":
    case "update_vendor":
    case "notify_founder":
      throw new Error(`Tool ${toolName} is not yet implemented`);

    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
}

/**
 * Get all available tools
 */
export function getAvailableTools(): ToolDefinition[] {
  return Object.values(TOOL_REGISTRY);
}

/**
 * Get tool by name
 */
export function getTool(name: ToolName): ToolDefinition | undefined {
  return TOOL_REGISTRY[name];
}

/**
 * Check if tool is auto-approve eligible
 */
export function canAutoApproveWithTool(toolName: ToolName): boolean {
  return TOOL_REGISTRY[toolName]?.autoApproveEligible ?? false;
}
