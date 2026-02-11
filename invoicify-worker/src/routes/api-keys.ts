/**
 * API Keys Route Module
 *
 * Complete API key management endpoints:
 * - Create, list, view, update, rotate, and revoke API keys
 * - Support for SERVICE_ACCOUNT (long-lived) and PAT (short-lived) keys
 * - Rate limiting configuration per key type
 * - IP whitelist validation
 * - Permission scoping
 * - Full audit logging for all operations
 * - Key only shown once on creation
 *
 * Key format: inv_live_XXXXXXXX (where X is random alphanumeric)
 * - SERVICE_ACCOUNT: 12 month expiry, 1000 req/min rate limit
 * - PAT: 90 day expiry, 100 req/min rate limit
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import { eq, and, desc, sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";
import {
  validateBearerToken,
  validateApiKey,
  type OrgRole,
} from "../lib/auth";
import { logger } from "../lib/logger";

// ============================================================================
// Types & Enums
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
 * Audit action types for API keys
 */
export const ApiKeyAuditAction = {
  CREATE: "CREATE",
  UPDATE: "UPDATE",
  ROTATE: "ROTATE",
  REVOKE: "REVOKE",
  VIEW: "VIEW",
} as const;

export type ApiKeyAuditAction = (typeof ApiKeyAuditAction)[keyof typeof ApiKeyAuditAction];

// Import tables from schema
const { apiKeys, apiKeyAuditLogs, organizations } = schema;

// ============================================================================
// Constants
// ============================================================================

/**
 * Default rate limits per key type (requests per minute)
 */
export const RATE_LIMITS = {
  [ApiKeyType.SERVICE_ACCOUNT]: 1000,
  [ApiKeyType.PAT]: 100,
} as const;

/**
 * Default expiry periods in days
 */
export const EXPIRY_PERIODS = {
  [ApiKeyType.SERVICE_ACCOUNT]: 365, // 12 months
  [ApiKeyType.PAT]: 90, // 90 days
} as const;

/**
 * Available permissions for API keys
 */
export const AVAILABLE_PERMISSIONS = [
  "invoices:read",
  "invoices:create",
  "invoices:write",
  "invoices:delete",
  "invoices:approve",
  "vendors:read",
  "vendors:create",
  "vendors:write",
  "vendors:delete",
  "reports:read",
  "reports:export",
  "settings:read",
  "settings:write",
  "webhooks:read",
  "webhooks:write",
  "webhooks:delete",
  "api-keys:read",
  "api-keys:write",
  "api-keys:delete",
  "*", // Full access (admin only)
] as const;

export type Permission = (typeof AVAILABLE_PERMISSIONS)[number];

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Generate a cryptographically secure random string
 */
function generateSecureRandom(length: number): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const randomValues = new Uint8Array(length);
  crypto.getRandomValues(randomValues);
  return Array.from(randomValues, (byte) => chars[byte % chars.length]).join("");
}

/**
 * Generate a new API key with the proper prefix format
 * Format: inv_live_XXXXXXXX (total 20 chars after prefix)
 */
function generateApiKey(): string {
  const prefix = "inv_live_";
  const randomPart = generateSecureRandom(20);
  return `${prefix}${randomPart}`;
}

/**
 * Hash API key using SHA-256 for secure storage
 */
async function hashApiKey(key: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(key);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Get the key prefix (first 8 chars after inv_live_)
 */
function getKeyPrefix(key: string): string {
  return key.slice(0, 12); // inv_live_XXXX (12 chars total visible prefix)
}

/**
 * Calculate expiry date based on key type
 */
function calculateExpiryDate(keyType: ApiKeyType): string {
  const days = EXPIRY_PERIODS[keyType];
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + days);
  return expiry.toISOString();
}

/**
 * Validate permissions array
 */
function validatePermissions(permissions: unknown): { valid: boolean; error?: string; permissions: string[] } {
  if (!Array.isArray(permissions)) {
    return { valid: false, error: "Permissions must be an array", permissions: [] };
  }

  const validPerms = permissions.filter((p) =>
    AVAILABLE_PERMISSIONS.includes(p as Permission)
  );

  if (validPerms.length === 0) {
    return { valid: false, error: "At least one valid permission is required", permissions: [] };
  }

  return { valid: true, permissions: validPerms };
}

/**
 * Validate IP whitelist
 */
function validateIpWhitelist(ipWhitelist: unknown): { valid: boolean; error?: string; ips: string[] | null } {
  if (ipWhitelist === undefined || ipWhitelist === null) {
    return { valid: true, ips: null };
  }

  if (!Array.isArray(ipWhitelist)) {
    return { valid: false, error: "IP whitelist must be an array", ips: null };
  }

  const validIps: string[] = [];
  const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\/(?:[0-9]|[1-2][0-9]|3[0-2]))?$/;

  for (const ip of ipWhitelist) {
    if (typeof ip !== "string") {
      return { valid: false, error: "Each IP must be a string", ips: null };
    }
    if (!ipRegex.test(ip)) {
      return { valid: false, error: `Invalid IP address: ${ip}`, ips: null };
    }
    validIps.push(ip);
  }

  return { valid: true, ips: validIps.length > 0 ? validIps : null };
}

/**
 * Validate API key name
 */
function validateKeyName(name: unknown): { valid: boolean; error?: string } {
  if (typeof name !== "string") {
    return { valid: false, error: "Name must be a string" };
  }

  const trimmed = name.trim();
  if (trimmed.length < 1) {
    return { valid: false, error: "Name cannot be empty" };
  }

  if (trimmed.length > 100) {
    return { valid: false, error: "Name must be less than 100 characters" };
  }

  return { valid: true };
}

/**
 * Check if user can manage API keys (ADMIN or OWNER role required)
 */
function canManageApiKeys(role: OrgRole): boolean {
  const roleHierarchy: Record<OrgRole, number> = {
    VIEWER: 1,
    USER: 2,
    APPROVER: 3,
    FINANCE: 4,
    ADMIN: 5,
    OWNER: 6,
  };
  return roleHierarchy[role] >= roleHierarchy.ADMIN;
}

/**
 * Require authentication helper
 */
async function requireAuth(
  c: { env: Env; req: { header: (name: string) => string | null; url: { pathname: string } } }
): Promise<{ success: true; userId: string; email: string; orgId: string; role: OrgRole; ipAddress?: string; userAgent?: string } | { success: false; error: string; status: number }> {
  const apiKey = c.req.header("x-api-key");
  const authHeader = c.req.header("authorization");

  let result;
  if (apiKey) {
    result = await validateApiKey(c.env, apiKey);
  } else {
    result = await validateBearerToken(c.env, authHeader);
  }

  if (!result.success) {
    return { success: false, error: result.error, status: result.status };
  }

  return {
    success: true,
    userId: result.user.id,
    email: result.user.email,
    orgId: result.user.organizationId,
    role: result.user.role as OrgRole,
    ipAddress: result.ipAddress,
    userAgent: result.userAgent,
  };
}

/**
 * Create audit log entry
 */
async function createAuditLog(
  env: Env,
  data: {
    apiKeyId: string;
    organizationId: string;
    action: ApiKeyAuditAction;
    performedBy: string;
    changes?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    ipAddress?: string;
    userAgent?: string;
  }
): Promise<void> {
  const db = getDb(env);

  await db.insert(apiKeyAuditLogs).values({
    id: uuidv4(),
    apiKeyId: data.apiKeyId,
    organizationId: data.organizationId,
    action: data.action,
    performedBy: data.performedBy,
    changes: data.changes ? JSON.stringify(data.changes) : null,
    metadata: data.metadata ? JSON.stringify(data.metadata) : null,
    ipAddress: data.ipAddress,
    userAgent: data.userAgent,
  });
}

// ============================================================================
// Route Definitions
// ============================================================================

const apiKeysRoutes = new Hono<{ Bindings: Env }>();

// ============ List Available Permissions ============
// GET /api-keys/permissions
apiKeysRoutes.get("/permissions", async (c) => {
  return c.json({
    data: {
      permissions: AVAILABLE_PERMISSIONS,
      rateLimits: RATE_LIMITS,
      expiryPeriods: EXPIRY_PERIODS,
    },
  });
});

// ============ Create API Key ============
// POST /api-keys
apiKeysRoutes.post("/", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json();

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can create API keys
  if (!canManageApiKeys(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to create API keys", code: "FORBIDDEN" },
      403
    );
  }

  // Validate name
  const { valid: nameValid, error: nameError } = validateKeyName(body.name);
  if (!nameValid) {
    return c.json({ error: nameError, code: "INVALID_NAME" }, 400);
  }

  // Validate key type
  const keyType = body.keyType === ApiKeyType.SERVICE_ACCOUNT
    ? ApiKeyType.SERVICE_ACCOUNT
    : ApiKeyType.PAT;

  // Validate permissions
  const { valid: permsValid, error: permsError, permissions } = validatePermissions(body.permissions);
  if (!permsValid) {
    return c.json({ error: permsError, code: "INVALID_PERMISSIONS" }, 400);
  }

  // Validate IP whitelist
  const { valid: ipValid, error: ipError, ips } = validateIpWhitelist(body.ipWhitelist);
  if (!ipValid) {
    return c.json({ error: ipError, code: "INVALID_IP_WHITELIST" }, 400);
  }

  // Generate new API key
  const rawKey = generateApiKey();
  const keyHash = await hashApiKey(rawKey);
  const keyPrefix = getKeyPrefix(rawKey);
  const expiresAt = calculateExpiryDate(keyType);
  const now = new Date().toISOString();

  const keyId = uuidv4();

  // Insert the new API key
  const [apiKey] = await db.insert(apiKeys).values({
    id: keyId,
    organizationId: auth.orgId,
    name: body.name.trim(),
    description: body.description || null,
    keyHash,
    keyPrefix,
    keyType,
    status: ApiKeyStatus.ACTIVE,
    permissions: JSON.stringify(permissions),
    ipWhitelist: ips ? JSON.stringify(ips) : null,
    rateLimitPerMinute: RATE_LIMITS[keyType],
    createdBy: auth.userId,
    expiresAt,
    createdAt: now,
    updatedAt: now,
  }).returning();

  // Create audit log
  await createAuditLog(c.env, {
    apiKeyId: keyId,
    organizationId: auth.orgId,
    action: ApiKeyAuditAction.CREATE,
    performedBy: auth.userId,
    changes: {
      name: body.name.trim(),
      keyType,
      permissions,
      ipWhitelist: ips,
    },
    metadata: {
      keyPrefix,
    },
    ipAddress: auth.ipAddress,
    userAgent: auth.userAgent,
  });

  logger.info("API key created", {
    action: "api_key_create",
    keyId,
    keyPrefix,
    organizationId: auth.orgId,
    createdBy: auth.userId,
    keyType,
  });

  // Return the key - this is the ONLY time the full key is shown
  return c.json({
    success: true,
    data: {
      id: apiKey.id,
      name: apiKey.name,
      description: apiKey.description,
      keyType: apiKey.keyType,
      status: apiKey.status,
      permissions,
      ipWhitelist: ips,
      rateLimitPerMinute: apiKey.rateLimitPerMinute,
      createdBy: apiKey.createdBy,
      expiresAt: apiKey.expiresAt,
      // Only shown once - never again!
      key: rawKey,
      // Key prefix for identification in logs/UI
      keyPrefix,
      createdAt: apiKey.createdAt,
    },
  }, 201);
});

// ============ List Organization API Keys ============
// GET /api-keys
apiKeysRoutes.get("/", async (c) => {
  const db = getDb(c.env);

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  const statusFilter = c.req.query("status") as ApiKeyStatus | undefined;
  const keyTypeFilter = c.req.query("keyType") as ApiKeyType | undefined;
  const search = c.req.query("search");

  let conditions = [eq(apiKeys.organizationId, auth.orgId)];

  if (statusFilter && Object.values(ApiKeyStatus).includes(statusFilter)) {
    conditions.push(eq(apiKeys.status, statusFilter));
  }

  if (keyTypeFilter && Object.values(ApiKeyType).includes(keyTypeFilter)) {
    conditions.push(eq(apiKeys.keyType, keyTypeFilter));
  }

  if (search) {
    conditions.push(
      sql`(${apiKeys.name} LIKE ${`%${search}%`} OR ${apiKeys.keyPrefix} LIKE ${`%${search}%`})`
    );
  }

  const keys = await db
    .select({
      id: apiKeys.id,
      name: apiKeys.name,
      description: apiKeys.description,
      keyType: apiKeys.keyType,
      status: apiKeys.status,
      permissions: apiKeys.permissions,
      rateLimitPerMinute: apiKeys.rateLimitPerMinute,
      lastUsedAt: apiKeys.lastUsedAt,
      lastUsedIp: apiKeys.lastUsedIp,
      expiresAt: apiKeys.expiresAt,
      rotatedAt: apiKeys.rotatedAt,
      revokedAt: apiKeys.revokedAt,
      createdAt: apiKeys.createdAt,
      updatedAt: apiKeys.updatedAt,
    })
    .from(apiKeys)
    .where(and(...conditions))
    .orderBy(desc(apiKeys.createdAt));

  // Count active keys for stats
  const [activeCountResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(apiKeys)
    .where(and(eq(apiKeys.organizationId, auth.orgId), eq(apiKeys.status, ApiKeyStatus.ACTIVE)));

  const [totalCountResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(apiKeys)
    .where(eq(apiKeys.organizationId, auth.orgId));

  return c.json({
    data: keys.map((key) => ({
      id: key.id,
      name: key.name,
      description: key.description,
      keyType: key.keyType,
      status: key.status,
      permissions: JSON.parse(key.permissions),
      rateLimitPerMinute: key.rateLimitPerMinute,
      lastUsedAt: key.lastUsedAt,
      lastUsedIp: key.lastUsedIp,
      expiresAt: key.expiresAt,
      rotatedAt: key.rotatedAt,
      revokedAt: key.revokedAt,
      createdAt: key.createdAt,
      updatedAt: key.updatedAt,
    })),
    count: keys.length,
    stats: {
      activeKeys: activeCountResult.count,
      totalKeys: totalCountResult.count,
    },
  });
});

// ============ Get Single API Key ============
// GET /api-keys/:id
apiKeysRoutes.get("/:id", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Get the API key
  const [apiKey] = await db
    .select({
      id: apiKeys.id,
      name: apiKeys.name,
      description: apiKeys.description,
      keyPrefix: apiKeys.keyPrefix,
      keyType: apiKeys.keyType,
      status: apiKeys.status,
      permissions: apiKeys.permissions,
      ipWhitelist: apiKeys.ipWhitelist,
      rateLimitPerMinute: apiKeys.rateLimitPerMinute,
      createdBy: apiKeys.createdBy,
      lastUsedAt: apiKeys.lastUsedAt,
      lastUsedIp: apiKeys.lastUsedIp,
      expiresAt: apiKeys.expiresAt,
      rotatedAt: apiKeys.rotatedAt,
      revokedAt: apiKeys.revokedAt,
      revokedBy: apiKeys.revokedBy,
      createdAt: apiKeys.createdAt,
      updatedAt: apiKeys.updatedAt,
    })
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!apiKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  // Create audit log for viewing key details
  await createAuditLog(c.env, {
    apiKeyId: keyId,
    organizationId: auth.orgId,
    action: ApiKeyAuditAction.VIEW,
    performedBy: auth.userId,
    ipAddress: auth.ipAddress,
    userAgent: auth.userAgent,
  });

  // Get recent audit log entries
  const auditLogs = await db
    .select({
      id: apiKeyAuditLogs.id,
      action: apiKeyAuditLogs.action,
      performedBy: apiKeyAuditLogs.performedBy,
      performedAt: apiKeyAuditLogs.performedAt,
      ipAddress: apiKeyAuditLogs.ipAddress,
    })
    .from(apiKeyAuditLogs)
    .where(eq(apiKeyAuditLogs.apiKeyId, keyId))
    .orderBy(desc(apiKeyAuditLogs.performedAt))
    .limit(10);

  return c.json({
    data: {
      id: apiKey.id,
      name: apiKey.name,
      description: apiKey.description,
      keyPrefix: apiKey.keyPrefix,
      keyType: apiKey.keyType,
      status: apiKey.status,
      permissions: JSON.parse(apiKey.permissions),
      ipWhitelist: apiKey.ipWhitelist ? JSON.parse(apiKey.ipWhitelist) : null,
      rateLimitPerMinute: apiKey.rateLimitPerMinute,
      createdBy: apiKey.createdBy,
      lastUsedAt: apiKey.lastUsedAt,
      lastUsedIp: apiKey.lastUsedIp,
      expiresAt: apiKey.expiresAt,
      rotatedAt: apiKey.rotatedAt,
      revokedAt: apiKey.revokedAt,
      revokedBy: apiKey.revokedBy,
      createdAt: apiKey.createdAt,
      updatedAt: apiKey.updatedAt,
    },
    auditLog: auditLogs.map((log) => ({
      id: log.id,
      action: log.action,
      performedBy: log.performedBy,
      performedAt: log.performedAt,
      ipAddress: log.ipAddress,
    })),
  });
});

// ============ Update API Key ============
// PATCH /api-keys/:id
apiKeysRoutes.patch("/:id", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");
  const body = await c.req.json();

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can update API keys
  if (!canManageApiKeys(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to update API keys", code: "FORBIDDEN" },
      403
    );
  }

  // Get the existing key
  const [existingKey] = await db
    .select()
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!existingKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  // Cannot update revoked keys
  if (existingKey.status === ApiKeyStatus.REVOKED) {
    return c.json({ error: "Cannot update revoked API key", code: "INVALID_STATUS" }, 400);
  }

  // Track changes for audit log
  const changes: Record<string, unknown> = {};
  const updates: Record<string, unknown> = { updatedAt: new Date().toISOString() };

  // Update name if provided
  if (body.name !== undefined) {
    const { valid: nameValid, error: nameError } = validateKeyName(body.name);
    if (!nameValid) {
      return c.json({ error: nameError, code: "INVALID_NAME" }, 400);
    }
    if (body.name.trim() !== existingKey.name) {
      changes.name = { from: existingKey.name, to: body.name.trim() };
      updates.name = body.name.trim();
    }
  }

  // Update description if provided
  if (body.description !== undefined) {
    const newDescription = body.description?.trim() || null;
    if (newDescription !== existingKey.description) {
      changes.description = { from: existingKey.description, to: newDescription };
      updates.description = newDescription;
    }
  }

  // Update permissions if provided
  if (body.permissions !== undefined) {
    const { valid: permsValid, error: permsError, permissions } = validatePermissions(body.permissions);
    if (!permsValid) {
      return c.json({ error: permsError, code: "INVALID_PERMISSIONS" }, 400);
    }
    const existingPerms = JSON.parse(existingKey.permissions);
    if (JSON.stringify(permissions.sort()) !== JSON.stringify(existingPerms.sort())) {
      changes.permissions = { from: existingPerms, to: permissions };
      updates.permissions = JSON.stringify(permissions);
    }
  }

  // Update IP whitelist if provided
  if (body.ipWhitelist !== undefined) {
    const { valid: ipValid, error: ipError, ips } = validateIpWhitelist(body.ipWhitelist);
    if (!ipValid) {
      return c.json({ error: ipError, code: "INVALID_IP_WHITELIST" }, 400);
    }
    const existingIps = existingKey.ipWhitelist ? JSON.parse(existingKey.ipWhitelist) : null;
    if (JSON.stringify(ips?.sort()) !== JSON.stringify(existingIps?.sort())) {
      changes.ipWhitelist = { from: existingIps, to: ips };
      updates.ipWhitelist = ips ? JSON.stringify(ips) : null;
    }
  }

  // Only update if there are actual changes
  if (Object.keys(changes).length === 0) {
    return c.json({
      success: true,
      data: {
        id: existingKey.id,
        name: existingKey.name,
        description: existingKey.description,
        keyType: existingKey.keyType,
        status: existingKey.status,
        permissions: JSON.parse(existingKey.permissions),
        ipWhitelist: existingKey.ipWhitelist ? JSON.parse(existingKey.ipWhitelist) : null,
        rateLimitPerMinute: existingKey.rateLimitPerMinute,
        expiresAt: existingKey.expiresAt,
        updatedAt: updates.updatedAt,
      },
      message: "No changes detected",
    });
  }

  const [updatedKey] = await db
    .update(apiKeys)
    .set(updates)
    .where(eq(apiKeys.id, keyId))
    .returning();

  // Create audit log
  await createAuditLog(c.env, {
    apiKeyId: keyId,
    organizationId: auth.orgId,
    action: ApiKeyAuditAction.UPDATE,
    performedBy: auth.userId,
    changes,
    ipAddress: auth.ipAddress,
    userAgent: auth.userAgent,
  });

  logger.info("API key updated", {
    action: "api_key_update",
    keyId,
    organizationId: auth.orgId,
    changes,
    updatedBy: auth.userId,
  });

  return c.json({
    success: true,
    data: {
      id: updatedKey.id,
      name: updatedKey.name,
      description: updatedKey.description,
      keyType: updatedKey.keyType,
      status: updatedKey.status,
      permissions: JSON.parse(updatedKey.permissions),
      ipWhitelist: updatedKey.ipWhitelist ? JSON.parse(updatedKey.ipWhitelist) : null,
      rateLimitPerMinute: updatedKey.rateLimitPerMinute,
      expiresAt: updatedKey.expiresAt,
      updatedAt: updatedKey.updatedAt,
    },
    changes,
  });
});

// ============ Revoke API Key ============
// DELETE /api-keys/:id
apiKeysRoutes.delete("/:id", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can revoke API keys
  if (!canManageApiKeys(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to revoke API keys", code: "FORBIDDEN" },
      403
    );
  }

  // Get the existing key
  const [existingKey] = await db
    .select()
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!existingKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  // Check if already revoked
  if (existingKey.status === ApiKeyStatus.REVOKED) {
    return c.json({ error: "API key is already revoked", code: "ALREADY_REVOKED" }, 400);
  }

  const now = new Date().toISOString();

  // Revoke the key
  await db
    .update(apiKeys)
    .set({
      status: ApiKeyStatus.REVOKED,
      revokedAt: now,
      revokedBy: auth.userId,
      updatedAt: now,
    })
    .where(eq(apiKeys.id, keyId));

  // Create audit log
  await createAuditLog(c.env, {
    apiKeyId: keyId,
    organizationId: auth.orgId,
    action: ApiKeyAuditAction.REVOKE,
    performedBy: auth.userId,
    changes: {
      status: { from: existingKey.status, to: ApiKeyStatus.REVOKED },
    },
    ipAddress: auth.ipAddress,
    userAgent: auth.userAgent,
  });

  logger.info("API key revoked", {
    action: "api_key_revoke",
    keyId,
    keyPrefix: existingKey.keyPrefix,
    organizationId: auth.orgId,
    revokedBy: auth.userId,
  });

  return c.json({
    success: true,
    message: "API key revoked successfully",
    data: {
      id: keyId,
      name: existingKey.name,
      status: ApiKeyStatus.REVOKED,
      revokedAt: now,
      revokedBy: auth.userId,
    },
  });
});

// ============ Rotate API Key ============
// POST /api-keys/:id/rotate
apiKeysRoutes.post("/:id/rotate", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Only ADMIN or OWNER can rotate API keys
  if (!canManageApiKeys(auth.role)) {
    return c.json(
      { error: "Insufficient permissions to rotate API keys", code: "FORBIDDEN" },
      403
    );
  }

  // Get the existing key
  const [existingKey] = await db
    .select()
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!existingKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  // Cannot rotate revoked keys
  if (existingKey.status === ApiKeyStatus.REVOKED) {
    return c.json({ error: "Cannot rotate revoked API key", code: "INVALID_STATUS" }, 400);
  }

  // Generate new API key
  const rawKey = generateApiKey();
  const newKeyHash = await hashApiKey(rawKey);
  const newKeyPrefix = getKeyPrefix(rawKey);
  const expiresAt = calculateExpiryDate(existingKey.keyType as ApiKeyType);
  const now = new Date().toISOString();

  // Update the key - keep old hash for audit trail
  await db
    .update(apiKeys)
    .set({
      keyHash: newKeyHash,
      keyPrefix: newKeyPrefix,
      previousKeyHash: existingKey.keyHash,
      expiresAt,
      rotatedAt: now,
      updatedAt: now,
    })
    .where(eq(apiKeys.id, keyId));

  // Create audit log
  await createAuditLog(c.env, {
    apiKeyId: keyId,
    organizationId: auth.orgId,
    action: ApiKeyAuditAction.ROTATE,
    performedBy: auth.userId,
    changes: {
      oldKeyPrefix: existingKey.keyPrefix,
      newKeyPrefix,
      expiresAt: { from: existingKey.expiresAt, to: expiresAt },
    },
    metadata: {
      keyPrefix: newKeyPrefix,
    },
    ipAddress: auth.ipAddress,
    userAgent: auth.userAgent,
  });

  logger.info("API key rotated", {
    action: "api_key_rotate",
    keyId,
    oldKeyPrefix: existingKey.keyPrefix,
    newKeyPrefix,
    organizationId: auth.orgId,
    rotatedBy: auth.userId,
  });

  // Return the new key - this is the ONLY time the full key is shown
  return c.json({
    success: true,
    data: {
      id: keyId,
      name: existingKey.name,
      keyType: existingKey.keyType,
      status: ApiKeyStatus.ACTIVE,
      permissions: JSON.parse(existingKey.permissions),
      rateLimitPerMinute: existingKey.rateLimitPerMinute,
      // New key - only shown once!
      key: rawKey,
      keyPrefix: newKeyPrefix,
      expiresAt,
      rotatedAt: now,
      previousKeyPrefix: existingKey.keyPrefix, // For reference
    },
    message: "API key rotated successfully. Save this key now - it will not be shown again.",
  });
});

// ============ Get API Key Audit Logs ============
// GET /api-keys/:id/audit-logs
apiKeysRoutes.get("/:id/audit-logs", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Verify key exists and belongs to organization
  const [existingKey] = await db
    .select({ id: apiKeys.id })
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!existingKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  // Get audit logs
  const logs = await db
    .select({
      id: apiKeyAuditLogs.id,
      action: apiKeyAuditLogs.action,
      performedBy: apiKeyAuditLogs.performedBy,
      performedAt: apiKeyAuditLogs.performedAt,
      changes: apiKeyAuditLogs.changes,
      ipAddress: apiKeyAuditLogs.ipAddress,
      userAgent: apiKeyAuditLogs.userAgent,
    })
    .from(apiKeyAuditLogs)
    .where(eq(apiKeyAuditLogs.apiKeyId, keyId))
    .orderBy(desc(apiKeyAuditLogs.performedAt))
    .limit(100);

  return c.json({
    data: logs.map((log) => ({
      id: log.id,
      action: log.action,
      performedBy: log.performedBy,
      performedAt: log.performedAt,
      changes: log.changes ? JSON.parse(log.changes) : null,
      ipAddress: log.ipAddress,
      userAgent: log.userAgent,
    })),
    count: logs.length,
  });
});

// ============ Get Available Permissions ============
// GET /api-keys/:id/permissions (also available at /api-keys/permissions)
apiKeysRoutes.get("/:id/permissions", async (c) => {
  const db = getDb(c.env);
  const keyId = c.req.param("id");

  // Check authorization
  const auth = await requireAuth(c);
  if (!auth.success) {
    return c.json({ error: auth.error, code: "UNAUTHORIZED" }, auth.status);
  }

  // Verify key exists and belongs to organization
  const [existingKey] = await db
    .select({
      id: apiKeys.id,
      permissions: apiKeys.permissions,
    })
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.organizationId, auth.orgId)))
    .limit(1);

  if (!existingKey) {
    return c.json({ error: "API key not found", code: "NOT_FOUND" }, 404);
  }

  return c.json({
    data: {
      keyId,
      currentPermissions: JSON.parse(existingKey.permissions),
      availablePermissions: AVAILABLE_PERMISSIONS,
      rateLimits: RATE_LIMITS,
      expiryPeriods: EXPIRY_PERIODS,
    },
  });
});

export { apiKeysRoutes };
