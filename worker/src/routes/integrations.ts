/**
 * Integrations Routes
 *
 * Core third-party integrations for invoicify:
 * - QuickBooks - Accounting sync
 * - Stripe - Payment processing
 * - Slack - Notifications & approvals
 * - Google Sheets - Report exports
 * - OAuth 2.0 authentication flows
 * - Sync queue processing with exponential backoff
 * - Field mapping transformations
 * - Webhook handling
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  eq,
  desc,
  asc,
  and,
  like,
  sql,
  or,
  gte,
  inArray,
  asc as ascField,
} from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";

// ============================================================================
// Integration Types
// ============================================================================

export const IntegrationType = {
  QUICKBOOKS: "quickbooks",
  STRIPE: "stripe",
  SLACK: "slack",
  GOOGLE_SHEETS: "google_sheets",
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

export const SyncAction = {
  CREATE: "CREATE",
  UPDATE: "UPDATE",
  DELETE: "DELETE",
} as const;

export type SyncAction = (typeof SyncAction)[keyof typeof SyncAction];

export const SyncStatus = {
  PENDING: "PENDING",
  PROCESSING: "PROCESSING",
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
  RETRYING: "RETRYING",
} as const;

export type SyncStatus = (typeof SyncStatus)[keyof typeof SyncStatus];

// ============================================================================
// OAuth Configurations
// ============================================================================

export const OAUTH_CONFIGS: Record<
  string,
  {
    authUrl: string;
    tokenUrl: string;
    scopes: string[];
    endpoints: Record<string, string>;
    clientIdEnv?: string;
    clientSecretEnv?: string;
  }
> = {
  quickbooks: {
    authUrl: "https://appcenter.intuit.com/connect/oauth2",
    tokenUrl: "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
    scopes: ["com.intuit.quickbooks.accounting"],
    endpoints: {
      base: "https://quickbooks.api.intuit.com/v3",
      company: "/company/{realmId}",
    },
    clientIdEnv: "QUICKBOOKS_CLIENT_ID",
    clientSecretEnv: "QUICKBOOKS_CLIENT_SECRET",
  },
  stripe: {
    authUrl: "https://connect.stripe.com/oauth/authorize",
    tokenUrl: "https://connect.stripe.com/oauth/token",
    scopes: ["read_write"],
    endpoints: {
      base: "https://api.stripe.com/v1",
    },
    clientIdEnv: "STRIPE_CLIENT_ID",
    clientSecretEnv: "STRIPE_CLIENT_SECRET",
  },
  slack: {
    authUrl: "https://slack.com/oauth/v2/authorize",
    tokenUrl: "https://slack.com/api/oauth.v2.access",
    scopes: ["chat:write", "channels:read", "users:read"],
    endpoints: {
      base: "https://slack.com/api",
    },
    clientIdEnv: "SLACK_CLIENT_ID",
    clientSecretEnv: "SLACK_CLIENT_SECRET",
  },
  google_sheets: {
    authUrl: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenUrl: "https://oauth2.googleapis.com/token",
    scopes: ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
    endpoints: {
      base: "https://sheets.googleapis.com/v4",
    },
    clientIdEnv: "GOOGLE_CLIENT_ID",
    clientSecretEnv: "GOOGLE_CLIENT_SECRET",
  },
};

// ============================================================================
// Field Mappings
// ============================================================================

export const FIELD_MAPPINGS: Record<
  string,
  {
    localToRemote: Record<string, string>;
    remoteToLocal: Record<string, string>;
  }
> = {
  quickbooks: {
    localToRemote: {
      vendorName: "VendorRef",
      invoiceNumber: "DocNumber",
      invoiceDate: "TxnDate",
      dueDate: "DueDate",
      totalAmount: "TotalAmt",
      subtotal: "SubTotal",
      taxAmount: "TaxAmount",
      currency: "CurrencyRef",
      lineItems: "Line",
    },
    remoteToLocal: {
      Id: "quickbooksId",
      DocNumber: "invoiceNumber",
      TxnDate: "invoiceDate",
      TotalAmt: "totalAmount",
      Balance: "balanceAmount",
    },
  },
  stripe: {
    localToRemote: {
      invoiceNumber: "number",
      totalAmount: "amount_due",
      currency: "currency",
      status: "status",
    },
    remoteToLocal: {
      id: "stripeId",
      number: "invoiceNumber",
      amount_due: "totalAmount",
      status: "status",
    },
  },
  google_sheets: {
    localToRemote: {
      vendorName: "Vendor",
      invoiceNumber: "Invoice Number",
      invoiceDate: "Date",
      dueDate: "Due Date",
      totalAmount: "Amount",
      currency: "Currency",
    },
    remoteToLocal: {
      "Invoice Number": "invoiceNumber",
      Date: "invoiceDate",
      Amount: "totalAmount",
      Vendor: "vendorName",
    },
  },
};

// ============================================================================
// Sync Queue Utilities
// ============================================================================

export function calculateRetryDelay(attempt: number, baseDelay: number = 1000): number {
  const maxDelay = 30000; // 30 seconds
  const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
  const jitter = 0.05 * delay; // 5% jitter
  return Math.floor(delay + jitter);
}

export function getSyncPriority(entityType: string): number {
  const priorities: Record<string, number> = {
    invoice: 1,
    payment: 2,
    vendor: 3,
    customer: 4,
    report: 5,
  };
  return priorities[entityType] || 10;
}

export function getBatchSize(provider: string): number {
  const limits: Record<string, number> = {
    quickbooks: 100,
    stripe: 100,
    slack: 50,
    google_sheets: 50,
  };
  return limits[provider] || 25;
}

// ============================================================================
// OAuth Utilities
// ============================================================================

export function generateOAuthState(): { state: string; expiresAt: number } {
  const state = crypto.randomUUID();
  const expiresAt = Date.now() + 10 * 60 * 1000; // 10 minutes
  return { state: `${state}.${expiresAt}`, expiresAt };
}

export function validateOAuthState(state: string): { valid: boolean; token?: string; expiresAt?: number; error?: string } {
  const parts = state.split(".");
  if (parts.length !== 2) {
    return { valid: false, error: "Invalid state format" };
  }

  const [token, expires] = parts;
  if (!/^[0-9a-f-]{36}$/.test(token)) {
    return { valid: false, error: "Invalid state token format" };
  }

  const expiresAt = parseInt(expires);
  if (isNaN(expiresAt)) {
    return { valid: false, error: "Invalid state expiration" };
  }

  if (expiresAt < Date.now()) {
    return { valid: false, error: "State expired" };
  }

  return { valid: true, token, expiresAt };
}

export function buildAuthUrl(
  provider: string,
  clientId: string,
  redirectUri: string,
  state: string,
  scopes: string
): string {
  const config = OAUTH_CONFIGS[provider];
  if (!config) {
    throw new Error(`Unknown provider: ${provider}`);
  }

  const url = new URL(config.authUrl);
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", scopes);
  url.searchParams.set("state", state);

  return url.toString();
}

// ============================================================================
// Data Transformation Utilities
// ============================================================================

export function transformData<T extends Record<string, unknown>>(
  data: T,
  mapping: Record<string, string>
): Record<string, unknown> {
  const transformed: Record<string, unknown> = {};

  for (const [localField, remoteField] of Object.entries(mapping)) {
    if (data[localField as keyof T] !== undefined) {
      transformed[remoteField] = data[localField as keyof T];
    }
  }

  return transformed;
}

export function validateRequiredFields(
  data: Record<string, unknown>,
  required: string[]
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  for (const field of required) {
    if (!data[field]) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  return { valid: errors.length === 0, errors };
}

// ============================================================================
// Webhook Utilities
// ============================================================================

export function validateWebhookSignature(
  payload: string,
  signature: string,
  secret: string
): { valid: boolean; error?: string } {
  if (!signature.startsWith("v0=")) {
    return { valid: false, error: "Invalid signature format" };
  }

  // In production, implement proper HMAC verification
  // const expectedSignature = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  // const [, actualSig] = signature.split('v0=');
  // return { valid: crypto.timingSafeEqual(Buffer.from(actualSig, 'hex'), Buffer.from(expectedSignature, 'hex')) };

  // Simplified validation for demo
  const parts = signature.split(",");
  if (parts.length !== 2) {
    return { valid: false, error: "Invalid signature format" };
  }

  const [ts, sig] = parts;
  if (!ts.startsWith("v0=") || !sig.startsWith("v1=")) {
    return { valid: false, error: "Invalid signature parts" };
  }

  return { valid: true };
}

export function handleWebhookEvent(eventType: string, payload: Record<string, unknown>): {
  action: string;
  processed: boolean;
} {
  const handlers: Record<string, () => { action: string; processed: boolean }> = {
    "invoice.synced": () => ({ action: "update_local", processed: true }),
    "invoice.deleted": () => ({ action: "remove_local", processed: true }),
    "payment.completed": () => ({ action: "mark_paid", processed: true }),
    "vendor.updated": () => ({ action: "sync_vendor", processed: true }),
  };

  const handler = handlers[eventType];
  if (!handler) {
    return { action: "unknown", processed: false };
  }

  return handler();
}

export function calculateWebhookBackoff(
  retryAfter: number | null,
  remaining: number,
  limit: number
): number {
  if (remaining === 0 && retryAfter) {
    return retryAfter * 1000;
  }

  const percentageUsed = remaining / limit;
  if (percentageUsed < 0.1) {
    return 1000;
  }

  return 100;
}

// ============================================================================
// Connection Management
// ============================================================================

export function isConnectionValid(
  status: string,
  lastVerifiedAt: string | null
): { valid: boolean; reason?: string; hoursSinceVerify?: number } {
  const VALID_STATUSES = ["CONNECTED", "ACTIVE"];

  if (!VALID_STATUSES.includes(status)) {
    return { valid: false, reason: "Invalid status" };
  }

  if (!lastVerifiedAt) {
    return { valid: false, reason: "Never verified" };
  }

  const lastVerified = new Date(lastVerifiedAt);
  const now = new Date();
  const hoursSinceVerify = (now.getTime() - lastVerified.getTime()) / (1000 * 60 * 60);

  if (hoursSinceVerify > 24) {
    return { valid: false, reason: "Connection stale" };
  }

  return { valid: true, hoursSinceVerify };
}

export function calculateSyncProgress(processed: number, total: number): number {
  if (total === 0) return 100;
  return Math.round((processed / total) * 100);
}

export function detectConflict(
  localVersion: number,
  remoteVersion: number
): { hasConflict: boolean; resolution: string; localVersion: number; remoteVersion: number } {
  if (localVersion === remoteVersion) {
    return { hasConflict: false, resolution: "none", localVersion, remoteVersion };
  }

  if (localVersion > remoteVersion) {
    return {
      hasConflict: true,
      resolution: "local_wins",
      localVersion,
      remoteVersion,
    };
  }

  return {
    hasConflict: true,
    resolution: "remote_wins",
    localVersion,
    remoteVersion,
  };
}

// ============================================================================
// API Response Formatters
// ============================================================================

export function formatConnectionStatus(connection: Record<string, unknown>): {
  success: boolean;
  data: {
    id: string;
    type: string;
    status: string;
    lastSyncAt?: string;
    lastVerifiedAt?: string;
    entitiesSynced: { invoices: number; vendors: number };
  };
} {
  return {
    success: true,
    data: {
      id: connection.id as string,
      type: connection.integration as string,
      status: connection.status as string,
      lastSyncAt: connection.lastSyncAt as string,
      lastVerifiedAt: connection.lastVerifiedAt as string,
      entitiesSynced: {
        invoices: (connection.invoicesSynced as number) || 0,
        vendors: (connection.vendorsSynced as number) || 0,
      },
    },
  };
}

export function formatSyncJob(job: Record<string, unknown>): {
  id: string;
  status: string;
  progress: number;
  startedAt: string;
  estimatedCompletion: string;
} {
  const processed = job.processed as number;
  const total = job.total as number;
  const estimatedSeconds = job.estimatedSeconds as number;

  return {
    id: job.id as string,
    status: job.status as string,
    progress: Math.round((processed / total) * 100),
    startedAt: job.startedAt as string,
    estimatedCompletion: new Date(Date.now() + estimatedSeconds * 1000).toISOString(),
  };
}

export function formatErrorResponse(
  code: string,
  message: string,
  provider?: string
): {
  success: boolean;
  error: {
    code: string;
    message: string;
    provider?: string;
    timestamp: string;
  };
} {
  return {
    success: false,
    error: {
      code,
      message,
      provider,
      timestamp: new Date().toISOString(),
    },
  };
}

// ============================================================================
// Rate Limiting
// ============================================================================

export function getApiCost(endpoint: string): number {
  const costs: Record<string, number> = {
    "/v3/company/{id}/query": 1,
    "/v3/company/{id}/invoice": 5,
    "/v3/company/{id}/invoice/{id}": 1,
    "/oauth2/v1/tokens/bearer": 1,
  };

  for (const [pattern, cost] of Object.entries(costs)) {
    const regex = new RegExp("^" + pattern.replace("{id}", "[^/]+").replace("{", "\\{") + "$");
    if (regex.test(endpoint)) return cost;
  }

  return 1;
}

export function calculateRemainingQuota(
  used: number,
  limit: number,
  windowMs: number
): { remaining: number; limit: number; resetAt: string } {
  return {
    remaining: Math.max(0, limit - used),
    limit,
    resetAt: new Date(Date.now() + windowMs).toISOString(),
  };
}

// ============================================================================
// Validation Helpers
// ============================================================================

function validateIntegrationType(type: string): type is IntegrationType {
  return Object.values(IntegrationType).includes(type as IntegrationType);
}

function validatePagination(
  page?: string,
  limit?: string
): { page: number; limit: number; error?: string } {
  const parsedPage = parseInt(page || "1");
  const parsedLimit = parseInt(limit || "20");

  if (isNaN(parsedPage) || parsedPage < 1) {
    return { page: 1, limit: parsedLimit, error: "Invalid page number" };
  }
  if (isNaN(parsedLimit) || parsedLimit < 1) {
    return { page: parsedPage, limit: 20, error: "Invalid limit" };
  }
  if (parsedLimit > 100) {
    return { page: parsedPage, limit: 100, error: "Limit capped at 100" };
  }

  return { page: parsedPage, limit: parsedLimit };
}

// ============================================================================
// Integrations Router
// ============================================================================

const integrationsRoutes = new Hono<{ Bindings: Env }>();

// GET /integrations - List all available and connected integrations
integrationsRoutes.get("/", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(formatErrorResponse("MISSING_ORG", "Organization ID is required"), 400);
  }

  // Get all available integration types
  const availableIntegrations = Object.values(IntegrationType);

  // Get connected integrations for the organization
  const connectedIntegrations = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.organizationId, organizationId))
    .orderBy(desc(schema.integrations.createdAt));

  // Build response with status for each integration
  const integrations = availableIntegrations.map((type) => {
    const connection = connectedIntegrations.find((c) => c.integrationType === type);
    return {
      type,
      status: connection?.status || IntegrationStatus.DISCONNECTED,
      connectedAt: connection?.connectedAt || null,
      lastSyncAt: connection?.lastSyncAt || null,
      lastVerifiedAt: connection?.lastVerifiedAt || null,
      error: connection?.lastError || null,
    };
  });

  return c.json({
    success: true,
    data: integrations,
    counts: {
      total: integrations.length,
      connected: integrations.filter((i) => i.status === IntegrationStatus.CONNECTED).length,
      disconnected: integrations.filter((i) => i.status === IntegrationStatus.DISCONNECTED).length,
      error: integrations.filter((i) => i.status === IntegrationStatus.ERROR).length,
    },
  });
});

// GET /integrations/:id - Get integration details
integrationsRoutes.get("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  // Get sync history
  const syncHistory = await db
    .select()
    .from(schema.syncHistory)
    .where(eq(schema.syncHistory.integrationId, id))
    .orderBy(desc(schema.syncHistory.startedAt))
    .limit(10);

  // Get field mappings
  const mappings = await db
    .select()
    .from(schema.fieldMappings)
    .where(eq(schema.fieldMappings.integrationId, id));

  return c.json({
    success: true,
    data: {
      ...integration,
      syncHistory,
      fieldMappings: mappings,
    },
  });
});

// POST /integrations/:id/connect - Start OAuth flow
integrationsRoutes.post("/:id/connect", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(formatErrorResponse("MISSING_ORG", "Organization ID is required"), 400);
  }

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  const type = integration.integrationType;
  const config = OAUTH_CONFIGS[type];

  if (!config) {
    return c.json(formatErrorResponse("INVALID_TYPE", `Unknown integration type: ${type}`), 400);
  }

  // Generate OAuth state
  const { state, expiresAt } = generateOAuthState();

  // Store state with expiration (in production, use Redis or database)
  await db
    .update(schema.integrations)
    .set({
      status: IntegrationStatus.CONNECTING,
      oauthState: state,
      oauthStateExpiresAt: new Date(expiresAt).toISOString(),
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.integrations.id, id));

  // Build authorization URL
  const clientId = getIntegrationClientEnv(c.env, type, "clientId");
  const redirectUri = `${c.env.APP_URL}/api/v1/integrations/${id}/callback`;
  const scopes = config.scopes.join(" ");
  const authUrl = buildAuthUrl(type, clientId, redirectUri, state, scopes);

  return c.json({
    success: true,
    data: {
      authUrl,
      state,
      expiresAt: new Date(expiresAt).toISOString(),
      redirectUri,
    },
  });
});

// GET /integrations/:id/callback - OAuth callback
integrationsRoutes.get("/:id/callback", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const code = c.req.query("code");
  const state = c.req.query("state");
  const error = c.req.query("error");

  if (error) {
    await db
      .update(schema.integrations)
      .set({
        status: IntegrationStatus.ERROR,
        lastError: `OAuth error: ${error}`,
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.integrations.id, id));

    return c.redirect(
      `${c.env.APP_URL}/integrations?error=${encodeURIComponent(`OAuth error: ${error}`)}`
    );
  }

  if (!code || !state) {
    return c.json(formatErrorResponse("INVALID_CALLBACK", "Missing code or state"), 400);
  }

  // Validate state
  const stateValidation = validateOAuthState(state);
  if (!stateValidation.valid) {
    return c.json(formatErrorResponse("INVALID_STATE", stateValidation.error || "Invalid state"), 400);
  }

  // Verify state matches stored state
  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration || integration.oauthState !== state) {
    return c.json(formatErrorResponse("STATE_MISMATCH", "State mismatch"), 400);
  }

  const type = integration.integrationType;
  const config = OAUTH_CONFIGS[type];

  if (!config) {
    return c.json(formatErrorResponse("INVALID_TYPE", `Unknown integration type: ${type}`), 400);
  }

  // Exchange code for tokens
  const clientId = getIntegrationClientEnv(c.env, type, "clientId");
  const clientSecret = getIntegrationClientEnv(c.env, type, "clientSecret");

  try {
    const tokenResponse = await exchangeCodeForTokens(code, clientId, clientSecret, config.tokenUrl);

    if (!tokenResponse) {
      throw new Error("Failed to exchange code for tokens");
    }

    // Store encrypted tokens
    const encryptedTokens = encryptTokens(tokenResponse);

    await db
      .update(schema.integrations)
      .set({
        status: IntegrationStatus.CONNECTED,
        accessToken: encryptedTokens.accessToken,
        refreshToken: encryptedTokens.refreshToken,
        tokenExpiresAt: new Date(tokenResponse.expiresAt).toISOString(),
        realmId: tokenResponse.realmId || null,
        oauthState: null,
        oauthStateExpiresAt: null,
        connectedAt: new Date().toISOString(),
        lastVerifiedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.integrations.id, id));

    return c.redirect(`${c.env.APP_URL}/integrations?success=${type}`);
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : "Unknown error";
    await db
      .update(schema.integrations)
      .set({
        status: IntegrationStatus.ERROR,
        lastError: errorMessage,
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.integrations.id, id));

    return c.json(formatErrorResponse("TOKEN_EXCHANGE_FAILED", errorMessage), 500);
  }
});

// POST /integrations/:id/disconnect - Disconnect integration
integrationsRoutes.post("/:id/disconnect", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  // Revoke tokens with provider (if applicable)
  if (integration.accessToken) {
    const type = integration.integrationType;
    const config = OAUTH_CONFIGS[type];

    if (config && integration.refreshToken) {
      await revokeToken(integration.refreshToken, config.tokenUrl).catch(() => {
        // Ignore revocation errors
      });
    }
  }

  // Clear stored credentials
  await db
    .update(schema.integrations)
    .set({
      status: IntegrationStatus.DISCONNECTED,
      accessToken: null,
      refreshToken: null,
      tokenExpiresAt: null,
      realmId: null,
      lastSyncAt: null,
      lastVerifiedAt: null,
      lastError: null,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.integrations.id, id));

  return c.json({
    success: true,
    message: "Integration disconnected successfully",
  });
});

// POST /integrations/:id/sync - Trigger sync
integrationsRoutes.post("/:id/sync", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json<{
    entityType?: string;
    entityIds?: string[];
    fullSync?: boolean;
  }>();

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  if (integration.status !== IntegrationStatus.CONNECTED) {
    return c.json(formatErrorResponse("NOT_CONNECTED", "Integration not connected"), 400);
  }

  // Create sync job
  const syncJobId = uuidv4();
  const now = new Date().toISOString();

  await db.insert(schema.syncJobs).values({
    id: syncJobId,
    integrationId: id,
    organizationId: integration.organizationId,
    status: SyncStatus.PENDING,
    entityType: body.entityType || "all",
    entityIds: body.entityIds ? JSON.stringify(body.entityIds) : null,
    fullSync: body.fullSync || false,
    startedAt: now,
    createdAt: now,
  });

  // Update integration status
  await db
    .update(schema.integrations)
    .set({
      status: IntegrationStatus.SYNCING,
      updatedAt: now,
    })
    .where(eq(schema.integrations.id, id));

  // Queue items for sync
  if (body.entityIds && body.entityIds.length > 0) {
    const batchSize = getBatchSize(integration.integrationType);

    for (const entityId of body.entityIds) {
      await db.insert(schema.integrationSyncQueue).values({
        id: uuidv4(),
        syncJobId,
        integrationId: id,
        entityType: body.entityType || "invoice",
        entityId,
        action: schema.IntegrationSyncQueueAction.CREATE,
        status: SyncStatus.PENDING,
        priority: getSyncPriority(body.entityType || "invoice"),
        scheduledAt: now,
        createdAt: now,
      });
    }
  }

  return c.json({
    success: true,
    data: {
      syncJobId,
      status: SyncStatus.PENDING,
      entityType: body.entityType || "all",
      entityCount: body.entityIds?.length || 0,
    },
  });
});

// GET /integrations/:id/sync/status - Get sync status
integrationsRoutes.get("/:id/sync/status", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  // Get recent sync jobs
  const syncJobs = await db
    .select()
    .from(schema.syncJobs)
    .where(eq(schema.syncJobs.integrationId, id))
    .orderBy(desc(schema.syncJobs.startedAt))
    .limit(10);

  // Get pending queue items
  const queueCounts = await db
    .select({
      pending: sql<number>`count(case when ${schema.integrationSyncQueue.status} = 'PENDING' then 1 end)`,
      processing: sql<number>`count(case when ${schema.integrationSyncQueue.status} = 'PROCESSING' then 1 end)`,
      completed: sql<number>`count(case when ${schema.integrationSyncQueue.status} = 'COMPLETED' then 1 end)`,
      failed: sql<number>`count(case when ${schema.integrationSyncQueue.status} = 'FAILED' then 1 end)`,
      retrying: sql<number>`count(case when ${schema.integrationSyncQueue.status} = 'RETRYING' then 1 end)`,
    })
    .from(schema.integrationSyncQueue)
    .where(eq(schema.integrationSyncQueue.integrationId, id));

  const latestJob = syncJobs[0];
  const progress = latestJob
    ? calculateSyncProgress(
        (latestJob.processedCount as number) || 0,
        (latestJob.totalCount as number) || 0
      )
    : 0;

  return c.json({
    success: true,
    data: {
      integrationStatus: integration.status,
      lastSyncAt: integration.lastSyncAt,
      currentJob: latestJob
        ? {
            id: latestJob.id,
            status: latestJob.status,
            progress,
            startedAt: latestJob.startedAt,
            completedAt: latestJob.completedAt,
          }
        : null,
      queue: queueCounts[0] || {
        pending: 0,
        processing: 0,
        completed: 0,
        failed: 0,
        retrying: 0,
      },
      recentJobs: syncJobs.map((job) => ({
        id: job.id,
        status: job.status,
        progress: calculateSyncProgress(
          (job.processedCount as number) || 0,
          (job.totalCount as number) || 0
        ),
        startedAt: job.startedAt,
        completedAt: job.completedAt,
      })),
    },
  });
});

// GET /integrations/:id/mappings - Get field mappings
integrationsRoutes.get("/:id/mappings", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  // Get stored mappings
  const mappings = await db
    .select()
    .from(schema.fieldMappings)
    .where(eq(schema.fieldMappings.integrationId, id));

  // Get default mappings for this integration type
  const defaultMappings = FIELD_MAPPINGS[integration.integrationType] || {
    localToRemote: {},
    remoteToLocal: {},
  };

  return c.json({
    success: true,
    data: {
      integrationType: integration.integrationType,
      defaultMappings,
      customMappings: mappings,
    },
  });
});

// PATCH /integrations/:id/mappings - Update field mappings
integrationsRoutes.patch("/:id/mappings", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json<{
    mappings: Array<{
      localField: string;
      remoteField: string;
      transform?: string;
      required?: boolean;
    }>;
  }>();

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  // Validate mappings
  const errors: string[] = [];
  for (const mapping of body.mappings) {
    if (!mapping.localField || !mapping.remoteField) {
      errors.push("Each mapping must have localField and remoteField");
    }
  }

  if (errors.length > 0) {
    return c.json(formatErrorResponse("INVALID_MAPPINGS", errors.join(", ")), 400);
  }

  // Delete existing mappings
  await db.delete(schema.fieldMappings).where(eq(schema.fieldMappings.integrationId, id));

  // Insert new mappings
  const now = new Date().toISOString();
  for (const mapping of body.mappings) {
    await db.insert(schema.fieldMappings).values({
      id: uuidv4(),
      integrationId: id,
      organizationId: integration.organizationId,
      localField: mapping.localField,
      remoteField: mapping.remoteField,
      transform: mapping.transform || null,
      required: mapping.required || false,
      createdAt: now,
      updatedAt: now,
    });
  }

  return c.json({
    success: true,
    message: "Field mappings updated successfully",
    data: {
      count: body.mappings.length,
    },
  });
});

// POST /integrations/:id/webhook - Handle provider webhooks
integrationsRoutes.post("/:id/webhook", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [integration] = await db
    .select()
    .from(schema.integrations)
    .where(eq(schema.integrations.id, id))
    .limit(1);

  if (!integration) {
    return c.json(formatErrorResponse("NOT_FOUND", "Integration not found"), 404);
  }

  const signature = c.req.header("X-Webhook-Signature") || "";
  const body = await c.req.text();

  // Validate signature
  const webhookSecret = integration.webhookSecret;
  if (webhookSecret) {
    const validation = validateWebhookSignature(body, signature, webhookSecret);
    if (!validation.valid) {
      return c.json(formatErrorResponse("INVALID_SIGNATURE", validation.error || "Invalid signature"), 401);
    }
  }

  // Parse event
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(body);
  } catch {
    return c.json(formatErrorResponse("INVALID_JSON", "Invalid JSON payload"), 400);
  }

  const eventType = payload.eventType as string || payload.type as string;
  if (!eventType) {
    return c.json(formatErrorResponse("MISSING_EVENT", "Missing event type"), 400);
  }

  // Handle event
  const result = handleWebhookEvent(eventType, payload);

  // Log webhook event
  await db.insert(schema.webhookEvents).values({
    id: uuidv4(),
    integrationId: id,
    organizationId: integration.organizationId,
    eventType,
    payload: JSON.stringify(payload),
    processed: result.processed,
    action: result.action,
    receivedAt: new Date().toISOString(),
  });

  if (result.processed) {
    return c.json({ success: true, action: result.action });
  }

  return c.json({ success: false, action: "ignored" });
});

// GET /integrations/:id/logs - Get integration audit logs
integrationsRoutes.get("/:id/logs", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const { page, limit, error: pageError } = validatePagination(c.req.query("page"), c.req.query("limit"));

  if (pageError) {
    return c.json({ error: pageError, code: "INVALID_PAGINATION" }, 400);
  }

  const offset = (page - 1) * limit;

  const logs = await db
    .select()
    .from(schema.integrationLogs)
    .where(eq(schema.integrationLogs.integrationId, id))
    .orderBy(desc(schema.integrationLogs.createdAt))
    .limit(limit)
    .offset(offset);

  const [totalResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(schema.integrationLogs)
    .where(eq(schema.integrationLogs.integrationId, id));

  return c.json({
    success: true,
    data: logs,
    pagination: {
      page,
      limit,
      total: totalResult.count || 0,
      totalPages: Math.ceil((totalResult.count || 0) / limit),
    },
  });
});

// ============================================================================
// Token Exchange Helper Functions
// ============================================================================

interface TokenResponse {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  realmId?: string;
}

async function exchangeCodeForTokens(
  code: string,
  clientId: string,
  clientSecret: string,
  tokenUrl: string
): Promise<TokenResponse | null> {
  const credentials = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
    }),
  });

  if (!response.ok) {
    console.error("Token exchange failed:", await response.text());
    return null;
  }

  const data = await response.json() as TokenResponse;
  return data;
}

async function refreshAccessToken(
  refreshToken: string,
  clientId: string,
  clientSecret: string,
  tokenUrl: string
): Promise<TokenResponse | null> {
  const credentials = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    }),
  });

  if (!response.ok) {
    console.error("Token refresh failed:", await response.text());
    return null;
  }

  const data = await response.json() as TokenResponse;
  return data;
}

async function revokeToken(refreshToken: string, tokenUrl: string): Promise<boolean> {
  try {
    const response = await fetch(tokenUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        token: refreshToken,
        token_type_hint: "refresh_token",
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

interface EncryptedTokens {
  accessToken: string;
  refreshToken: string;
}

function encryptTokens(tokens: TokenResponse): EncryptedTokens {
  // In production, use proper encryption like AES-256-GCM
  // This is a placeholder that encodes to base64
  return {
    accessToken: Buffer.from(tokens.accessToken).toString("base64"),
    refreshToken: Buffer.from(tokens.refreshToken).toString("base64"),
  };
}

function decryptTokens(encrypted: EncryptedTokens): { accessToken: string; refreshToken: string } {
  return {
    accessToken: Buffer.from(encrypted.accessToken, "base64").toString("utf-8"),
    refreshToken: Buffer.from(encrypted.refreshToken, "base64").toString("utf-8"),
  };
}

function getIntegrationClientEnv(
  env: Env,
  integrationType: string,
  keyType: "clientId" | "clientSecret"
): string {
  const config = OAUTH_CONFIGS[integrationType];
  if (!config) {
    throw new Error(`Unknown integration type: ${integrationType}`);
  }

  const envKey = keyType === "clientId" ? config.clientIdEnv : config.clientSecretEnv;
  if (!envKey) {
    throw new Error(`No environment variable configured for ${integrationType} ${keyType}`);
  }

  const value = env[envKey as keyof Env];
  if (!value) {
    throw new Error(`Missing environment variable: ${envKey}`);
  }

  return value;
}

// ============================================================================
// Sync Queue Processing (Background Worker)
// ============================================================================

export async function processSyncQueue(env: Env): Promise<{
  processed: number;
  success: number;
  failed: number;
  errors: string[];
}> {
  const db = getDb(env);

  const results = {
    processed: 0,
    success: 0,
    failed: 0,
    errors: [] as string[],
  };

  // Get pending items ordered by priority and scheduled time
  const pending = await db
    .select()
    .from(schema.integrationSyncQueue)
    .where(eq(schema.integrationSyncQueue.status, schema.IntegrationSyncQueueStatus.PENDING))
    .orderBy(asc(schema.integrationSyncQueue.priority), asc(schema.integrationSyncQueue.scheduledAt))
    .limit(50);

  for (const item of pending) {
    // Mark as processing
    await db
      .update(schema.integrationSyncQueue)
      .set({
        status: schema.IntegrationSyncQueueStatus.PROCESSING,
        attempts: (item.attempts || 0) + 1,
        startedAt: new Date().toISOString(),
      })
      .where(eq(schema.integrationSyncQueue.id, item.id));

    try {
      // Process based on entity type
      await processSyncItem(env, item);

      await db
        .update(schema.integrationSyncQueue)
        .set({
          status: schema.IntegrationSyncQueueStatus.COMPLETED,
          processedAt: new Date().toISOString(),
        })
        .where(eq(schema.integrationSyncQueue.id, item.id));

      results.success++;
    } catch (err) {
      const errorMsg = String(err);
      const attempt = (item.attempts || 0) + 1;
      const retryDelay = calculateRetryDelay(attempt);

      if (attempt >= 5) {
        // Max retries reached
        await db
          .update(schema.integrationSyncQueue)
          .set({
            status: schema.IntegrationSyncQueueStatus.FAILED,
            lastError: errorMsg,
          })
          .where(eq(schema.integrationSyncQueue.id, item.id));

        results.failed++;
        results.errors.push(`${item.entityId}: ${errorMsg}`);
      } else {
        // Schedule retry
        const retryAt = new Date(Date.now() + retryDelay).toISOString();
        await db
          .update(schema.integrationSyncQueue)
          .set({
            status: schema.IntegrationSyncQueueStatus.RETRYING,
            lastError: errorMsg,
            scheduledAt: retryAt,
          })
          .where(eq(schema.integrationSyncQueue.id, item.id));
      }
    }

    results.processed++;
  }

  return results;
}

async function processSyncItem(
  env: Env,
  item: typeof schema.integrationSyncQueue.$inferSelect
): Promise<void> {
  // Implementation would vary by entity type
  // This is a placeholder that simulates processing
  const delay = Math.random() * 100;
  await new Promise((resolve) => setTimeout(resolve, delay));

  // In production, this would call the appropriate API
  console.log(`Processing sync item: ${item.entityType} ${item.entityId} ${item.action}`);
}

// ============================================================================
// Admin Endpoints (for managing integrations globally)
// ============================================================================

// GET /integrations/admin/providers - List all available providers
integrationsRoutes.get("/admin/providers", async (c) => {
  const providers = Object.entries(OAUTH_CONFIGS).map(([key, config]) => ({
    id: key,
    name: key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
    authUrl: config.authUrl,
    scopes: config.scopes,
    endpoints: config.endpoints,
    configured: !!(config.clientIdEnv && process.env[config.clientIdEnv]),
  }));

  return c.json({
    success: true,
    data: providers,
  });
});

// POST /integrations/admin/sync-queue/process - Process sync queue (cron endpoint)
integrationsRoutes.post("/admin/sync-queue/process", async (c) => {
  const apiKey = c.req.header("X-API-Key");
  const adminKey = c.env.ADMIN_API_KEY;

  if (!adminKey || apiKey !== adminKey) {
    return c.json(formatErrorResponse("UNAUTHORIZED", "Invalid API key"), 401);
  }

  const results = await processSyncQueue(c.env);

  return c.json({
    success: true,
    ...results,
  });
});

export { integrationsRoutes };
