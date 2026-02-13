import { sqliteTable, text, real, integer, primaryKey } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

// ============================================================================
// Enums
// ============================================================================

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
 * Plan type enum values
 */
export const PlanType = {
  FREE: "free",
  STARTER: "starter",
  PROFESSIONAL: "professional",
  ENTERPRISE: "enterprise",
} as const;

export type PlanType = (typeof PlanType)[keyof typeof PlanType];

// ============================================================================
// Organizations (Multi-tenant)
// ============================================================================

/**
 * Organizations table
 */
export const organizations = sqliteTable("organizations", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull().unique(),
  logoUrl: text("logo_url"),
  email: text("email"),
  settings: text("settings"), // JSON string for organization settings
  plan: text("plan").default(PlanType.FREE),
  stripeCustomerId: text("stripe_customer_id"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Organization members table
 */
export const organizationUsers = sqliteTable("organization_users", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull(),
  email: text("email").notNull(),
  role: text("role").notNull().default("USER"),
  invitedAt: text("invited_at").default(sql`CURRENT_TIMESTAMP`),
  joinedAt: text("joined_at"),
  lastActiveAt: text("last_active_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Invitations table
 */
export const invitations = sqliteTable("invitations", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  email: text("email").notNull(),
  role: text("role").notNull().default("USER"),
  token: text("token").notNull().unique(),
  status: text("status").default("PENDING"),
  invitedBy: text("invited_by").notNull(),
  expiresAt: text("expires_at").notNull(),
  acceptedAt: text("accepted_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

// ============================================================================
// Main Tables
// ============================================================================

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
 * Comprehensive audit logs for enterprise compliance
 */
export const auditLogs = sqliteTable("audit_logs", {
  id: text("id").primaryKey(),
  timestamp: text("timestamp").notNull().default(sql`CURRENT_TIMESTAMP`),
  organizationId: text("organization_id").notNull(),

  // Actor information
  actorUserId: text("actor_user_id").notNull(),
  actorEmail: text("actor_email"),
  actorName: text("actor_name"),
  actorRole: text("actor_role"),

  // Action details
  action: text("action").notNull(),
  resourceType: text("resource_type").notNull(),
  resourceId: text("resource_id").notNull(),
  resourceName: text("resource_name"),

  // Additional details
  details: text("details"), // JSON string
  severity: text("severity").notNull().default("INFO"),

  // Request metadata
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  correlationId: text("correlation_id"),

  // Retention
  archivedAt: text("archived_at"),
  storageLocation: text("storage_location"),

  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
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

// ============================================================================
// Billing & Subscription Tables
// ============================================================================

export const SubscriptionStatus = {
  ACTIVE: "active",
  PAST_DUE: "past_due",
  CANCELED: "canceled",
  UNPAID: "unpaid",
  TRIALING: "trialing",
  INCOMPLETE: "incomplete",
  INCOMPLETE_EXPIRED: "incomplete_expired",
  PAUSED: "paused",
} as const;

export type SubscriptionStatusType = (typeof SubscriptionStatus)[keyof typeof SubscriptionStatus];

/**
 * Stripe customers table - maps Stripe customer IDs to organizations
 */
export const stripeCustomers = sqliteTable("stripe_customers", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  stripeCustomerId: text("stripe_customer_id").notNull().unique(),
  email: text("email").notNull(),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Subscriptions table - tracks active subscriptions
 */
export const subscriptions = sqliteTable("subscriptions", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  stripeSubscriptionId: text("stripe_subscription_id").notNull().unique(),
  stripePriceId: text("stripe_price_id").notNull(),
  plan: text("plan").notNull().default("free"),
  status: text("status").notNull().default(SubscriptionStatus.ACTIVE),
  currentPeriodStart: text("current_period_start").notNull(),
  currentPeriodEnd: text("current_period_end").notNull(),
  cancelAtPeriodEnd: integer("cancel_at_period_end", { mode: "boolean" }).default(false),
  trialStart: text("trial_start"),
  trialEnd: text("trial_end"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

/**
 * Billing invoices table - tracks invoices processed for usage billing
 */
export const billingInvoices = sqliteTable("billing_invoices", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  stripeInvoiceId: text("stripe_invoice_id").unique(),
  amount: real("amount").notNull().default(0),
  currency: text("currency").default("USD"),
  status: text("status").notNull().default("pending"),
  periodStart: text("period_start").notNull(),
  periodEnd: text("period_end").notNull(),
  invoicesCount: integer("invoices_processed").default(0),
  overageAmount: real("overage_amount").default(0),
  paidAt: text("paid_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Usage tracking table - tracks monthly usage for overage calculations
 */
export const usageTracking = sqliteTable("usage_tracking", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  month: text("month").notNull(), // Format: YYYY-MM
  invoicesProcessed: integer("invoices_processed").default(0),
  storageUsed: real("storage_used").default(0), // MB
  usersCount: integer("users_count").default(0),
  lastUpdatedAt: text("last_updated_at").default(sql`CURRENT_TIMESTAMP`),
});

// ============================================================================
// API Keys Table
// ============================================================================

/**
 * API key type enum
 */
export const ApiKeyType = {
  SERVICE_ACCOUNT: "SERVICE_ACCOUNT",
  PAT: "PAT",
} as const;

export type ApiKeyType = (typeof ApiKeyType)[keyof typeof ApiKeyType];

/**
 * API key status enum
 */
export const ApiKeyStatus = {
  ACTIVE: "ACTIVE",
  REVOKED: "REVOKED",
  EXPIRED: "EXPIRED",
} as const;

export type ApiKeyStatus = (typeof ApiKeyStatus)[keyof typeof ApiKeyStatus];

/**
 * API Keys table for service account and personal access token management
 */
export const apiKeys = sqliteTable("api_keys", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  description: text("description"),
  keyHash: text("key_hash").notNull().unique(), // SHA-256 hash of the key
  keyPrefix: text("key_prefix").notNull(), // First 8 chars for identification (e.g., inv_live_xxxx)
  keyType: text("key_type").notNull().default(ApiKeyType.PAT),
  status: text("status").notNull().default(ApiKeyStatus.ACTIVE),
  permissions: text("permissions").notNull(), // JSON array of permission strings
  ipWhitelist: text("ip_whitelist"), // JSON array of allowed IPs (nullable)
  rateLimitPerMinute: integer("rate_limit_per_minute").notNull().default(100), // 100 for PAT, 1000 for SERVICE_ACCOUNT
  createdBy: text("created_by").notNull(), // User ID who created the key
  lastUsedAt: text("last_used_at"),
  lastUsedIp: text("last_used_ip"),
  expiresAt: text("expires_at").notNull(), // 90 days for PAT, 12 months for SERVICE_ACCOUNT
  rotatedAt: text("rotated_at"), // When key was last rotated
  previousKeyHash: text("previous_key_hash"), // For key rotation tracking
  revokedAt: text("revoked_at"),
  revokedBy: text("revoked_by"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * API Key Audit Log table - tracks all API key operations
 */
export const apiKeyAuditLogs = sqliteTable("api_key_audit_logs", {
  id: text("id").primaryKey(),
  apiKeyId: text("api_key_id")
    .notNull()
    .references(() => apiKeys.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  action: text("action").notNull(), // CREATE, UPDATE, ROTATE, REVOKE, VIEW
  performedBy: text("performed_by").notNull(), // User ID
  performedAt: text("performed_at").default(sql`CURRENT_TIMESTAMP`),
  changes: text("changes"), // JSON object with before/after values
  metadata: text("metadata"), // Additional context (IP, user agent, etc.)
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
});

// ============================================================================
// Integration Types Enum
// ============================================================================

export const IntegrationType = {
  QUICKBOOKS: "quickbooks",
  XERO: "xero",
  STRIPE: "stripe",
  SLACK: "slack",
  GOOGLE_SHEETS: "google_sheets",
  ZAPIER: "zapier",
  SALESFORCE: "salesforce",
  NETSUITE: "netsuite",
} as const;

export type IntegrationType = (typeof IntegrationType)[keyof typeof IntegrationType];

export const IntegrationStatus = {
  DISCONNECTED: "DISCONNECTED",
  CONNECTING: "CONNECTING",
  CONNECTED: "CONNECTED",
  ERROR: "ERROR",
  SYNCING: "SYNCING",
} as const;

export type IntegrationStatus = (typeof IntegrationStatus)[keyof typeof IntegrationStatus];

// ============================================================================
// Integrations Table
// ============================================================================

export const integrations = sqliteTable("integrations", {
  id: text("id").primaryKey(),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  integrationType: text("integration_type").notNull(),
  status: text("status").default(IntegrationStatus.DISCONNECTED),
  accessToken: text("access_token"), // Encrypted
  refreshToken: text("refresh_token"), // Encrypted
  tokenExpiresAt: text("token_expires_at"),
  realmId: text("realm_id"), // For QuickBooks/Xero tenant ID
  oauthState: text("oauth_state"),
  oauthStateExpiresAt: text("oauth_state_expires_at"),
  webhookSecret: text("webhook_secret"),
  lastSyncAt: text("last_sync_at"),
  lastVerifiedAt: text("last_verified_at"),
  lastError: text("last_error"),
  settings: text("settings"), // JSON settings
  connectedAt: text("connected_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

// ============================================================================
// Field Mappings Table
// ============================================================================

export const fieldMappings = sqliteTable("field_mappings", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  entityType: text("entity_type").default("invoice"),
  localField: text("local_field").notNull(),
  remoteField: text("remote_field").notNull(),
  transform: text("transform"), // Transformation function name
  required: integer("required", { mode: "boolean" }).default(false),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

// ============================================================================
// Sync Jobs Table
// ============================================================================

export const syncJobs = sqliteTable("sync_jobs", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  status: text("status").default("PENDING"),
  entityType: text("entity_type"),
  entityIds: text("entity_ids"), // JSON array
  fullSync: integer("full_sync", { mode: "boolean" }).default(false),
  totalCount: integer("total_count").default(0),
  processedCount: integer("processed_count").default(0),
  successCount: integer("success_count").default(0),
  failedCount: integer("failed_count").default(0),
  errorMessage: text("error_message"),
  startedAt: text("started_at"),
  completedAt: text("completed_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

// ============================================================================
// Integration Sync Queue Table
// ============================================================================

export const IntegrationSyncQueueStatus = {
  PENDING: "PENDING",
  PROCESSING: "PROCESSING",
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
  RETRYING: "RETRYING",
} as const;

export const IntegrationSyncQueueAction = {
  CREATE: "CREATE",
  UPDATE: "UPDATE",
  DELETE: "DELETE",
} as const;

export const integrationSyncQueue = sqliteTable("integration_sync_queue", {
  id: text("id").primaryKey(),
  syncJobId: text("sync_job_id")
    .notNull()
    .references(() => syncJobs.id, { onDelete: "cascade" }),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  action: text("action").default(IntegrationSyncQueueAction.CREATE),
  status: text("status").default(IntegrationSyncQueueStatus.PENDING),
  priority: integer("priority").default(10),
  attempts: integer("attempts").default(0),
  maxAttempts: integer("max_attempts").default(5),
  lastError: text("last_error"),
  scheduledAt: text("scheduled_at").default(sql`CURRENT_TIMESTAMP`),
  startedAt: text("started_at"),
  processedAt: text("processed_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

// ============================================================================
// Sync History Table
// ============================================================================

export const syncHistory = sqliteTable("sync_history", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  syncType: text("sync_type").notNull(), // full, incremental, manual
  status: text("status").notNull(),
  entityType: text("entity_type"),
  totalProcessed: integer("total_processed").default(0),
  successCount: integer("success_count").default(0),
  failedCount: integer("failed_count").default(0),
  duration: integer("duration_ms"),
  startedAt: text("started_at").notNull(),
  completedAt: text("completed_at"),
  errorSummary: text("error_summary"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

// ============================================================================
// Webhook Events Table
// ============================================================================

export const webhookEvents = sqliteTable("webhook_events", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  eventType: text("event_type").notNull(),
  payload: text("payload").notNull(), // JSON payload
  processed: integer("processed", { mode: "boolean" }).default(false),
  action: text("action"),
  error: text("error"),
  retryCount: integer("retry_count").default(0),
  receivedAt: text("received_at").default(sql`CURRENT_TIMESTAMP`),
  processedAt: text("processed_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

// ============================================================================
// Integration Logs Table
// ============================================================================

export const integrationLogs = sqliteTable("integration_logs", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  organizationId: text("organization_id")
    .notNull()
    .references(() => organizations.id, { onDelete: "cascade" }),
  level: text("level").default("INFO"), // DEBUG, INFO, WARN, ERROR
  action: text("action").notNull(),
  message: text("message").notNull(),
  details: text("details"), // JSON additional details
  requestId: text("request_id"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

// ============================================================================
// OAuth States Table (for validation)
// ============================================================================

export const oauthStates = sqliteTable("oauth_states", {
  id: text("id").primaryKey(),
  integrationId: text("integration_id")
    .notNull()
    .references(() => integrations.id, { onDelete: "cascade" }),
  state: text("state").notNull().unique(),
  expiresAt: text("expires_at").notNull(),
  used: integer("used", { mode: "boolean" }).default(false),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});
