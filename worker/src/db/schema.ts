import { sqliteTable, text, real, integer, primaryKey } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

/**
 * Invoice status enum values
 */
export const InvoiceStatus = {
  NEW: "NEW",
  EXTRACTED: "EXTRACTED",
  VALIDATED: "VALIDATED",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
  PENDING: "PENDING",
  PAID: "PAID",
  FAILED: "FAILED",
} as const;

export type InvoiceStatusType = (typeof InvoiceStatus)[keyof typeof InvoiceStatus];

/**
 * Risk level enum values
 */
export const RiskLevel = {
  LOW: "LOW",
  MEDIUM: "MEDIUM",
  HIGH: "HIGH",
  CRITICAL: "CRITICAL",
} as const;

export type RiskLevelType = (typeof RiskLevel)[keyof typeof RiskLevel];

/**
 * Approval status enum values
 */
export const ApprovalStatus = {
  PENDING: "PENDING",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
} as const;

export type ApprovalStatusType = (typeof ApprovalStatus)[keyof typeof ApprovalStatus];

/**
 * Main invoices table
 */
export const invoices = sqliteTable("invoices", {
  id: text("id").primaryKey(),
  vendorName: text("vendor_name").notNull(),
  vendorId: text("vendor_id"),
  invoiceNumber: text("invoice_number").notNull(),
  totalAmount: real("total_amount").notNull().default(0),
  currency: text("currency").default("USD"),
  status: text("status").default(InvoiceStatus.NEW),
  dueDate: text("due_date"),
  invoiceDate: text("invoice_date"),
  rawContent: text("raw_content"),
  extractedData: text("extracted_data"),
  confidenceScore: real("confidence_score"),
  riskScore: real("risk_score"),
  riskLevel: text("risk_level"),
  fileUrl: text("file_url"),
  fileName: text("file_name"),
  mimeType: text("mime_type"),
  quickbooksId: text("quickbooks_id"),
  quickbooksSyncedAt: text("quickbooks_synced_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Line items for invoices
 */
export const lineItems = sqliteTable("line_items", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  description: text("description").notNull(),
  quantity: real("quantity").notNull().default(1),
  unitPrice: real("unit_price").notNull().default(0),
  amount: real("amount").notNull().default(0),
  glCode: text("gl_code"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Vendors table
 */
export const vendors = sqliteTable("vendors", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  taxId: text("tax_id"),
  email: text("email"),
  phone: text("phone"),
  address: text("address"),
  bankAccount: text("bank_account"),
  bankRouting: text("bank_routing"),
  isVerified: integer("is_verified", { mode: "boolean" }).default(false),
  riskLevel: text("risk_level"),
  avgInvoiceAmount: real("avg_invoice_amount"),
  totalInvoices: integer("total_invoices").default(0),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Approvals table
 */
export const approvals = sqliteTable("approvals", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  approverEmail: text("approver_email").notNull(),
  approverName: text("approver_name"),
  status: text("status").notNull().default(ApprovalStatus.PENDING),
  comments: text("comments"),
  amountThreshold: real("amount_threshold"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Audit logs for compliance
 */
export const auditLogs = sqliteTable("audit_logs", {
  id: text("id").primaryKey(),
  action: text("action").notNull(),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  performedBy: text("performed_by"),
  performedAt: text("performed_at").default(sql`CURRENT_TIMESTAMP`),
  changes: text("changes"),
  metadata: text("metadata"),
  ipAddress: text("ip_address"),
});

/**
 * Duplicate detection records
 */
export const duplicateChecks = sqliteTable("duplicate_checks", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  checksum: text("checksum").notNull(),
  duplicateOfId: text("duplicate_of_id"),
  isDuplicate: integer("is_duplicate", { mode: "boolean" }).default(false),
  confidence: real("confidence"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Risk indicators for fraud detection
 */
export const riskIndicators = sqliteTable("risk_indicators", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  indicatorType: text("indicator_type").notNull(),
  severity: text("severity").notNull(),
  description: text("description").notNull(),
  scoreContribution: real("score_contribution").notNull().default(0),
  resolved: integer("resolved", { mode: "boolean" }).default(false),
  resolvedAt: text("resolved_at"),
  resolvedBy: text("resolved_by"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * QuickBooks sync queue
 */
export const syncQueue = sqliteTable("sync_queue", {
  id: text("id").primaryKey(),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  action: text("action").notNull().default("CREATE"),
  status: text("status").default("PENDING"),
  attempts: integer("attempts").default(0),
  lastError: text("last_error"),
  scheduledAt: text("scheduled_at").default(sql`CURRENT_TIMESTAMP`),
  processedAt: text("processed_at"),
});

/**
 * Payment tracking
 */
export const payments = sqliteTable("payments", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  scheduledDate: text("scheduled_date").notNull(),
  amount: real("amount").notNull().default(0),
  status: text("status").notNull().default("scheduled"),
  executedAt: text("executed_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Trust Battery - Agent Autonomy Tracking
 *
 * Tracks agent accuracy over time to determine autonomy level.
 * Level 1: Review All (0-50 consecutive accurate)
 * Level 2: Review Exceptions (50-100 consecutive accurate)
 * Level 3: Auto-Approve (100+ consecutive accurate)
 */
export const trustBattery = sqliteTable("trust_battery", {
  id: text("id").primaryKey(),
  vendorId: text("vendor_id").notNull(), // Per-vendor trust
  consecutiveAccurate: integer("consecutive_accurate").default(0), // Correct auto-decisions
  consecutiveErrors: integer("consecutive_errors").default(0), // Corrections needed
  totalDecisions: integer("total_decisions").default(0),
  accurateDecisions: integer("accurate_decisions").default(0),
  lastDecisionAt: text("last_decision_at").default(sql`CURRENT_TIMESTAMP`),
  trustLevel: integer("trust_level").default(3), // 1=Probation, 2=Standard, 3=Core
  autoApproveThreshold: real("auto_approve_threshold").default(500), // Max $ for auto-approve
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Agent Decision Log - For Learning Loop
 *
 * Records every decision made by the agent for audit and learning.
 */
export const agentDecisions = sqliteTable("agent_decisions", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id")
    .notNull()
    .references(() => invoices.id, { onDelete: "cascade" }),
  traceId: text("trace_id").notNull(), // For correlating with audit logs
  node: text("node").notNull(), // Which node made the decision
  decision: text("decision").notNull(), // AUTO_APPROVE, HITL, BLOCK, etc.
  confidence: real("confidence"),
  reasoning: text("reasoning"), // JSON string of reasoning chain
  signals: text("signals"), // JSON string of decision signals
  humanIntervention: integer("human_intervention", { mode: "boolean" }).default(false),
  humanDecision: text("human_decision"), // What human actually decided
  humanReason: text("human_reason"), // Human's reason for override
  outcomeVerified: integer("outcome_verified", { mode: "boolean" }).default(false),
  outcomeCorrect: integer("outcome_correct", { mode: "boolean" }), // Did agent guess right?
  feedbackReceived: integer("feedback_received", { mode: "boolean" }).default(false),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  verifiedAt: text("verified_at"),
});

/**
 * Strategic Configuration - Company Financial Settings
 */
export const strategicConfig = sqliteTable("strategic_config", {
  id: text("id").primaryKey().default("default"),
  strategyMode: text("strategy_mode").default("OPTIMIZE"), // SURVIVAL, GROWTH, OPTIMIZE
  payrollDate: text("payroll_date"), // Day of month (e.g., "15" or "28")
  payrollAmount: real("payroll_amount").default(0),
  safetyBuffer: real("safety_buffer").default(10000), // Min cash to maintain
  autoApproveThreshold: real("auto_approve_threshold").default(500),
  hitlThreshold: real("hitl_threshold").default(0.6), // Risk score threshold for HITL
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Budget Categories - Spending Limits
 */
export const budgetCategories = sqliteTable("budget_categories", {
  id: text("id").primaryKey(),
  category: text("category").notNull(),
  monthlyLimit: real("monthly_limit").notNull(),
  softCapAlert: integer("soft_cap_alert", { mode: "boolean" }).default(true),
  isActive: integer("is_active", { mode: "boolean" }).default(true),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});
