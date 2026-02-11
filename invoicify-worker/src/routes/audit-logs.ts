/**
 * Audit Logs Routes
 *
 * Comprehensive audit logging for enterprise compliance:
 * - Audit event types (user actions, system actions, security events)
 * - Audit log creation with validation and sanitization
 * - Query/filtering capabilities
 * - Export functionality (JSON, CSV, chunking)
 * - Retention policies
 * - Response formatting with pagination
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import { eq, desc, asc, and, gte, lte, like, sql, or } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";

// ============================================================================
// Audit Event Types
// ============================================================================

export const AUDIT_EVENT_TYPES = {
  USER_LOGIN: "USER_LOGIN",
  USER_LOGOUT: "USER_LOGOUT",
  INVOICE_CREATED: "INVOICE_CREATED",
  INVOICE_UPDATED: "INVOICE_UPDATED",
  INVOICE_DELETED: "INVOICE_DELETED",
  PAYMENT_PROCESSED: "PAYMENT_PROCESSED",
  INTEGRATION_CONNECTED: "INTEGRATION_CONNECTED",
  INTEGRATION_DISCONNECTED: "INTEGRATION_DISCONNECTED",
  SETTINGS_UPDATED: "SETTINGS_UPDATED",
  API_KEY_CREATED: "API_KEY_CREATED",
  API_KEY_REVOKED: "API_KEY_REVOKED",
  ROLE_CHANGED: "ROLE_CHANGED",
  PERMISSION_DENIED: "PERMISSION_DENIED",
} as const;

export type AuditEventType = (typeof AUDIT_EVENT_TYPES)[keyof typeof AUDIT_EVENT_TYPES];

export const SEVERITY_LEVELS = {
  INFO: "INFO",
  WARNING: "WARNING",
  ERROR: "ERROR",
  CRITICAL: "CRITICAL",
} as const;

export type SeverityLevel = (typeof SEVERITY_LEVELS)[keyof typeof SEVERITY_LEVELS];

export const SEVERITY_BY_EVENT_TYPE: Record<AuditEventType, SeverityLevel> = {
  [AUDIT_EVENT_TYPES.USER_LOGIN]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.USER_LOGOUT]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.INVOICE_CREATED]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.INVOICE_UPDATED]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.INVOICE_DELETED]: SEVERITY_LEVELS.WARNING,
  [AUDIT_EVENT_TYPES.PAYMENT_PROCESSED]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.INTEGRATION_CONNECTED]: SEVERITY_LEVELS.INFO,
  [AUDIT_EVENT_TYPES.INTEGRATION_DISCONNECTED]: SEVERITY_LEVELS.WARNING,
  [AUDIT_EVENT_TYPES.SETTINGS_UPDATED]: SEVERITY_LEVELS.WARNING,
  [AUDIT_EVENT_TYPES.API_KEY_CREATED]: SEVERITY_LEVELS.WARNING,
  [AUDIT_EVENT_TYPES.API_KEY_REVOKED]: SEVERITY_LEVELS.CRITICAL,
  [AUDIT_EVENT_TYPES.ROLE_CHANGED]: SEVERITY_LEVELS.WARNING,
  [AUDIT_EVENT_TYPES.PERMISSION_DENIED]: SEVERITY_LEVELS.ERROR,
};

// ============================================================================
// Retention Policies
// ============================================================================

export const RETENTION_BY_SEVERITY: Record<SeverityLevel, number> = {
  [SEVERITY_LEVELS.INFO]: 180, // 6 months
  [SEVERITY_LEVELS.WARNING]: 365, // 1 year
  [SEVERITY_LEVELS.ERROR]: 730, // 2 years
  [SEVERITY_LEVELS.CRITICAL]: 2555, // 7 years (compliance)
};

export const DEFAULT_RETENTION_DAYS = 365;
export const ARCHIVE_AFTER_DAYS = 90;
export const MAX_EXPORT_ROWS = 100000;

// ============================================================================
// Data Sanitization
// ============================================================================

const SENSITIVE_FIELDS = [
  "password",
  "token",
  "secret",
  "apiKey",
  "api_key",
  "accessToken",
  "refreshToken",
  "creditCard",
  "cvv",
  "ssn",
];

export function sanitizeSensitiveData(details: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...details };

  Object.keys(sanitized).forEach((key) => {
    const lowerKey = key.toLowerCase();
    if (SENSITIVE_FIELDS.some((field) => lowerKey.includes(field.toLowerCase()))) {
      sanitized[key] = "[REDACTED]";
    }
  });

  return sanitized;
}

export async function hashValue(value: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(value);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function maskIpAddress(ip: string): string {
  const ipv4Regex = /^(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}$/;
  const ipv4Match = ip.match(ipv4Regex);

  if (ipv4Match) {
    return `${ipv4Match[1]}.xxx.xxx`;
  }

  const ipv6Parts = ip.split(":");
  if (ipv6Parts.length >= 2) {
    return `${ipv6Parts[0]}:${ipv6Parts[1]}:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx`;
  }

  return "[REDACTED]";
}

export function normalizeUserAgent(userAgent: string): string {
  if (userAgent.length > 200) {
    return userAgent.substring(0, 197) + "...";
  }
  return userAgent.replace(/\s+/g, " ").trim();
}

// ============================================================================
// Audit Log Creation
// ============================================================================

export interface AuditActor {
  userId: string;
  email?: string;
  name?: string;
  role?: string;
}

export interface AuditResource {
  type: string;
  id: string;
  name?: string;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  organizationId: string;
  actor: AuditActor;
  action: AuditEventType;
  resource: AuditResource;
  details: Record<string, unknown>;
  ipAddress: string;
  userAgent: string;
  severity: SeverityLevel;
  correlationId?: string;
}

export function validateAuditLog(entry: Partial<AuditLogEntry>): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!entry.id) errors.push("id is required");
  if (!entry.timestamp) errors.push("timestamp is required");
  if (!entry.organizationId) errors.push("organizationId is required");
  if (!entry.actor?.userId) errors.push("actor.userId is required");
  if (!entry.action) errors.push("action is required");
  if (!entry.resource?.type) errors.push("resource.type is required");
  if (!entry.resource?.id) errors.push("resource.id is required");

  return {
    valid: errors.length === 0,
    errors,
  };
}

export function createAuditLog(
  organizationId: string,
  actor: AuditActor,
  action: AuditEventType,
  resource: AuditResource,
  details: Record<string, unknown> = {},
  ipAddress: string = "",
  userAgent: string = "",
  correlationId?: string
): AuditLogEntry {
  const id = `audit_${Date.now().toString(36)}_${crypto.randomUUID().replace(/-/g, "").substring(0, 8)}`;
  const timestamp = new Date().toISOString();
  const severity = SEVERITY_BY_EVENT_TYPE[action] || SEVERITY_LEVELS.INFO;

  // Sanitize sensitive data
  const sanitizedDetails = sanitizeSensitiveData(details);
  const maskedIp = maskIpAddress(ipAddress);
  const normalizedUa = normalizeUserAgent(userAgent);

  return Object.freeze({
    id,
    timestamp,
    organizationId,
    actor,
    action,
    resource,
    details: sanitizedDetails,
    ipAddress: maskedIp,
    userAgent: normalizedUa,
    severity,
    correlationId,
  });
}

export function generateLogId(): string {
  const timestamp = Date.now().toString(36);
  const randomPart = crypto.randomUUID().replace(/-/g, "").substring(0, 8);
  return `audit_${timestamp}_${randomPart}`;
}

// ============================================================================
// Query/Filtering
// ============================================================================

export interface AuditLogFilters {
  organizationId?: string;
  actorUserId?: string;
  action?: AuditEventType;
  severity?: SeverityLevel;
  startDate?: string;
  endDate?: string;
  resourceType?: string;
  resourceId?: string;
}

export interface PaginationParams {
  page?: number;
  pageSize?: number;
}

export function validatePagination(
  page?: string,
  limit?: string
): { page: number; limit: number; error?: string } {
  const parsedPage = parseInt(page || "1");
  const parsedLimit = parseInt(limit || "50");

  if (isNaN(parsedPage) || parsedPage < 1) {
    return { page: 1, limit: parsedLimit, error: "Invalid page number" };
  }
  if (isNaN(parsedLimit) || parsedLimit < 1) {
    return { page: parsedPage, limit: 50, error: "Invalid limit" };
  }
  if (parsedLimit > 100) {
    return { page: parsedPage, limit: 100, error: "Limit capped at 100" };
  }

  return { page: parsedPage, limit: parsedLimit };
}

export function paginate<T>(
  items: T[],
  page: number,
  pageSize: number
): { data: T[]; total: number; page: number; pageSize: number; totalPages: number } {
  const total = items.length;
  const totalPages = Math.ceil(total / pageSize);
  const offset = (page - 1) * pageSize;
  const data = items.slice(offset, offset + pageSize);

  return {
    data,
    total,
    page,
    pageSize,
    totalPages,
  };
}

// ============================================================================
// Export Functionality
// ============================================================================

export function exportToJson(logs: AuditLogEntry[]): string {
  return JSON.stringify(
    {
      exportDate: new Date().toISOString(),
      totalLogs: logs.length,
      logs,
    },
    null,
    2
  );
}

export function exportToCsv(logs: AuditLogEntry[], fields?: string[]): string {
  const headers = [
    "id",
    "timestamp",
    "organizationId",
    "actorUserId",
    "actorEmail",
    "actorName",
    "action",
    "resourceType",
    "resourceId",
    "resourceName",
    "severity",
    "ipAddress",
  ];

  const selectedHeaders = fields || headers;

  const rows = logs.map((log) =>
    selectedHeaders.map((header) => {
      if (header.includes(".")) {
        const [parent, child] = header.split(".");
        const parentObj = log[parent as keyof AuditLogEntry] as Record<string, unknown>;
        return parentObj?.[child]?.toString() || "";
      }
      const value = log[header as keyof AuditLogEntry];
      return value?.toString() || "";
    })
  );

  return [selectedHeaders.join(","), ...rows.map((row) => row.join(","))].join("\n");
}

export const JSON_CHUNK_SIZE = 1000;
export const CSV_CHUNK_SIZE = 500;

export function chunkLargeExport<T>(items: T[], chunkSize: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += chunkSize) {
    chunks.push(items.slice(i, i + chunkSize));
  }
  return chunks;
}

// ============================================================================
// Retention Policies
// ============================================================================

export function isWithinRetention(timestamp: string, retentionDays: number): boolean {
  const logDate = new Date(timestamp);
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - retentionDays);
  return logDate >= cutoffDate;
}

export function shouldArchive(timestamp: string, archiveAfterDays: number): boolean {
  const logDate = new Date(timestamp);
  const archiveDate = new Date();
  archiveDate.setDate(archiveDate.getDate() - archiveAfterDays);
  return logDate < archiveDate;
}

export function isExpired(timestamp: string, retentionDays: number): boolean {
  const logDate = new Date(timestamp).getTime();
  const expiryDate = Date.now() - retentionDays * 24 * 60 * 60 * 1000;
  return logDate < expiryDate;
}

export async function archiveLogs(
  logs: Array<{ id: string; timestamp: string }>,
  archiveAfterDays: number
): Promise<Array<{ id: string; timestamp: string; archivedAt: string; storageLocation: string }>> {
  const now = new Date().toISOString();
  const archiveDate = new Date();
  archiveDate.setDate(archiveDate.getDate() - archiveAfterDays);

  return logs
    .filter((log) => new Date(log.timestamp) < archiveDate)
    .map((log) => ({
      ...log,
      archivedAt: now,
      storageLocation: `s3://audit-archive/${log.id}.json.gz`,
    }));
}

// ============================================================================
// Response Formatting
// ============================================================================

export interface AuditLogResponse {
  id: string;
  timestamp: string;
  actor: {
    id: string;
    name: string | null;
    email: string | null;
  };
  action: string;
  resource: {
    type: string;
    id: string;
    name: string | null;
  };
  details: Record<string, unknown>;
  severity: string;
  ipAddress: string;
}

export function formatAuditLogResponse(log: AuditLogEntry): AuditLogResponse {
  return {
    id: log.id,
    timestamp: log.timestamp,
    actor: {
      id: log.actor.userId,
      name: log.actor.name || null,
      email: log.actor.email || null,
    },
    action: log.action,
    resource: {
      type: log.resource.type,
      id: log.resource.id,
      name: log.resource.name || null,
    },
    details: log.details,
    severity: log.severity,
    ipAddress: log.ipAddress,
  };
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
    hasNextPage: boolean;
    hasPreviousPage: boolean;
  };
}

export function createPaginatedResponse<T>(
  data: T[],
  page: number,
  pageSize: number
): PaginatedResponse<T> {
  const total = data.length;
  const totalPages = Math.ceil(total / pageSize);

  return {
    data: data.slice((page - 1) * pageSize, page * pageSize),
    pagination: {
      page,
      pageSize,
      total,
      totalPages,
      hasNextPage: page < totalPages,
      hasPreviousPage: page > 1,
    },
  };
}

export interface AuditLogListResponse {
  logs: Array<{
    id: string;
    timestamp: string;
    action: string;
    severity: string;
    actorName: string | null;
    resourceType: string;
  }>;
  filters: AuditLogFilters;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  appliedAt: string;
}

export function formatErrorResponse(
  code: string,
  message: string,
  details?: Record<string, unknown>
): {
  success: boolean;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
} {
  return {
    success: false,
    error: {
      code,
      message,
      ...(details && { details }),
    },
  };
}

// ============================================================================
// Audit Logs Router
// ============================================================================

const auditLogsRoutes = new Hono<{ Bindings: Env }>();

// GET /audit-logs - List audit logs with filtering
auditLogsRoutes.get("/", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(formatErrorResponse("MISSING_ORG", "Organization ID is required"), 400);
  }

  const { page, limit, error: pageError } = validatePagination(c.req.query("page"), c.req.query("limit"));

  if (pageError) {
    return c.json(formatErrorResponse("INVALID_PAGINATION", pageError), 400);
  }

  const action = c.req.query("action") as AuditEventType | undefined;
  const severity = c.req.query("severity") as SeverityLevel | undefined;
  const startDate = c.req.query("startDate");
  const endDate = c.req.query("endDate");
  const actorUserId = c.req.query("actorUserId");
  const resourceType = c.req.query("resourceType");

  // Build query conditions
  const conditions = [eq(schema.auditLogs.organizationId, organizationId)];

  if (action) {
    conditions.push(eq(schema.auditLogs.action, action));
  }

  if (severity) {
    conditions.push(eq(schema.auditLogs.severity, severity));
  }

  if (actorUserId) {
    conditions.push(eq(schema.auditLogs.actorUserId, actorUserId));
  }

  if (resourceType) {
    conditions.push(eq(schema.auditLogs.resourceType, resourceType));
  }

  if (startDate) {
    conditions.push(gte(schema.auditLogs.timestamp, startDate));
  }

  if (endDate) {
    conditions.push(lte(schema.auditLogs.timestamp, endDate));
  }

  // Get total count
  const [countResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(schema.auditLogs)
    .where(and(...conditions));

  const total = countResult.count || 0;
  const offset = (page - 1) * limit;

  // Get audit logs
  const logs = await db
    .select({
      id: schema.auditLogs.id,
      timestamp: schema.auditLogs.timestamp,
      action: schema.auditLogs.action,
      severity: schema.auditLogs.severity,
      actorUserId: schema.auditLogs.actorUserId,
      actorName: schema.auditLogs.actorName,
      resourceType: schema.auditLogs.resourceType,
      resourceId: schema.auditLogs.resourceId,
    })
    .from(schema.auditLogs)
    .where(and(...conditions))
    .orderBy(desc(schema.auditLogs.timestamp))
    .limit(limit)
    .offset(offset);

  const totalPages = Math.ceil(total / limit);

  return c.json({
    success: true,
    data: {
      logs: logs.map((log) => ({
        id: log.id,
        timestamp: log.timestamp,
        action: log.action,
        severity: log.severity,
        actorName: log.actorName,
        resourceType: log.resourceType,
      })),
      filters: {
        organizationId,
        action,
        severity,
        startDate,
        endDate,
        actorUserId,
        resourceType,
      },
      pagination: {
        page,
        pageSize: limit,
        total,
        totalPages,
        hasNextPage: page < totalPages,
        hasPreviousPage: page > 1,
      },
    },
  });
});

// GET /audit-logs/:id - Get single audit log
auditLogsRoutes.get("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [log] = await db
    .select({
      id: schema.auditLogs.id,
      timestamp: schema.auditLogs.timestamp,
      organizationId: schema.auditLogs.organizationId,
      actorUserId: schema.auditLogs.actorUserId,
      actorEmail: schema.auditLogs.actorEmail,
      actorName: schema.auditLogs.actorName,
      action: schema.auditLogs.action,
      resourceType: schema.auditLogs.resourceType,
      resourceId: schema.auditLogs.resourceId,
      resourceName: schema.auditLogs.resourceName,
      details: schema.auditLogs.details,
      severity: schema.auditLogs.severity,
      ipAddress: schema.auditLogs.ipAddress,
      userAgent: schema.auditLogs.userAgent,
    })
    .from(schema.auditLogs)
    .where(eq(schema.auditLogs.id, id))
    .limit(1);

  if (!log) {
    return c.json(formatErrorResponse("NOT_FOUND", "Audit log not found"), 404);
  }

  return c.json({
    success: true,
    data: {
      id: log.id,
      timestamp: log.timestamp,
      organizationId: log.organizationId,
      actor: {
        id: log.actorUserId,
        email: log.actorEmail,
        name: log.actorName,
      },
      action: log.action,
      resource: {
        type: log.resourceType,
        id: log.resourceId,
        name: log.resourceName,
      },
      details: log.details,
      severity: log.severity,
      ipAddress: log.ipAddress,
      userAgent: log.userAgent,
    },
  });
});

// POST /audit-logs - Create audit log entry
auditLogsRoutes.post("/", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json<{
    organizationId: string;
    actor: AuditActor;
    action: AuditEventType;
    resource: AuditResource;
    details?: Record<string, unknown>;
    ipAddress?: string;
    userAgent?: string;
    correlationId?: string;
  }>();

  // Validate required fields
  const validation = validateAuditLog({
    ...body,
    timestamp: new Date().toISOString(),
    id: generateLogId(),
  });

  if (!validation.valid) {
    return c.json(formatErrorResponse("VALIDATION_ERROR", validation.errors.join(", ")), 400);
  }

  const log = createAuditLog(
    body.organizationId,
    body.actor,
    body.action,
    body.resource,
    body.details || {},
    body.ipAddress || "",
    body.userAgent || "",
    body.correlationId
  );

  await db.insert(schema.auditLogs).values({
    id: log.id,
    timestamp: log.timestamp,
    organizationId: log.organizationId,
    actorUserId: log.actor.userId,
    actorEmail: log.actor.email || null,
    actorName: log.actor.name || null,
    actorRole: log.actor.role || null,
    action: log.action,
    resourceType: log.resource.type,
    resourceId: log.resource.id,
    resourceName: log.resource.name || null,
    details: JSON.stringify(log.details),
    severity: log.severity,
    ipAddress: log.ipAddress,
    userAgent: log.userAgent,
    correlationId: log.correlationId || null,
  });

  return c.json({
    success: true,
    data: {
      id: log.id,
      timestamp: log.timestamp,
      action: log.action,
      severity: log.severity,
    },
  });
});

// GET /audit-logs/export - Export audit logs
auditLogsRoutes.get("/export", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(formatErrorResponse("MISSING_ORG", "Organization ID is required"), 400);
  }

  const format = c.req.query("format") || "json";
  const startDate = c.req.query("startDate");
  const endDate = c.req.query("endDate");
  const fields = c.req.query("fields")?.split(",");

  if (!["json", "csv"].includes(format)) {
    return c.json(formatErrorResponse("INVALID_FORMAT", "Format must be json or csv"), 400);
  }

  // Build query conditions
  const conditions = [eq(schema.auditLogs.organizationId, organizationId)];

  if (startDate) {
    conditions.push(gte(schema.auditLogs.timestamp, startDate));
  }

  if (endDate) {
    conditions.push(lte(schema.auditLogs.timestamp, endDate));
  }

  // Get all matching logs (with limit for safety)
  const logs = await db
    .select({
      id: schema.auditLogs.id,
      timestamp: schema.auditLogs.timestamp,
      organizationId: schema.auditLogs.organizationId,
      actorUserId: schema.auditLogs.actorUserId,
      actorEmail: schema.auditLogs.actorEmail,
      actorName: schema.auditLogs.actorName,
      action: schema.auditLogs.action,
      resourceType: schema.auditLogs.resourceType,
      resourceId: schema.auditLogs.resourceId,
      resourceName: schema.auditLogs.resourceName,
      severity: schema.auditLogs.severity,
      ipAddress: schema.auditLogs.ipAddress,
    })
    .from(schema.auditLogs)
    .where(and(...conditions))
    .orderBy(desc(schema.auditLogs.timestamp))
    .limit(MAX_EXPORT_ROWS);

  const auditLogs: AuditLogEntry[] = logs.map((log) =>
    createAuditLog(
      log.organizationId,
      {
        userId: log.actorUserId,
        email: log.actorEmail || undefined,
        name: log.actorName || undefined,
      },
      log.action as AuditEventType,
      {
        type: log.resourceType,
        id: log.resourceId,
        name: log.resourceName || undefined,
      },
      {},
      log.ipAddress
    )
  );

  let exportData: string;
  let contentType: string;
  let fileExtension: string;

  if (format === "json") {
    exportData = exportToJson(auditLogs);
    contentType = "application/json";
    fileExtension = "json";
  } else {
    exportData = exportToCsv(auditLogs, fields);
    contentType = "text/csv";
    fileExtension = "csv";
  }

  const filename = `audit-logs-${organizationId}-${Date.now().toString(36)}.${fileExtension}`;

  return c.newResponse(exportData, 200, {
    "Content-Type": contentType,
    "Content-Disposition": `attachment; filename="${filename}"`,
  });
});

// GET /audit-logs/stats/summary - Get audit log summary
auditLogsRoutes.get("/stats/summary", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(formatErrorResponse("MISSING_ORG", "Organization ID is required"), 400);
  }

  const period = c.req.query("period") || "7d";
  const periodDays = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
  }[period] || 7;

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - periodDays);

  // Count by action
  const [actionCounts] = await db
    .select({
      action: schema.auditLogs.action,
      count: sql<number>`count(*)`,
    })
    .from(schema.auditLogs)
    .where(
      and(eq(schema.auditLogs.organizationId, organizationId), gte(schema.auditLogs.timestamp, startDate.toISOString()))
    )
    .groupBy(schema.auditLogs.action)
    .orderBy(desc(sql<number>`count(*)`));

  // Count by severity
  const [severityCounts] = await db
    .select({
      severity: schema.auditLogs.severity,
      count: sql<number>`count(*)`,
    })
    .from(schema.auditLogs)
    .where(
      and(eq(schema.auditLogs.organizationId, organizationId), gte(schema.auditLogs.timestamp, startDate.toISOString()))
    )
    .groupBy(schema.auditLogs.severity);

  // Total count
  const [totalCount] = await db
    .select({ count: sql<number>`count(*)` })
    .from(schema.auditLogs)
    .where(
      and(eq(schema.auditLogs.organizationId, organizationId), gte(schema.auditLogs.timestamp, startDate.toISOString()))
    );

  return c.json({
    success: true,
    data: {
      period,
      totalLogs: totalCount.count || 0,
      byAction: actionCounts,
      bySeverity: severityCounts,
    },
  });
});

// POST /audit-logs/archive - Archive old logs (admin)
auditLogsRoutes.post("/archive", async (c) => {
  const db = getDb(c.env);
  const adminKey = c.req.header("X-Admin-Key");

  if (adminKey !== c.env.ADMIN_API_KEY) {
    return c.json(formatErrorResponse("UNAUTHORIZED", "Invalid admin key"), 401);
  }

  // Find logs to archive (older than ARCHIVE_AFTER_DAYS)
  const archiveBefore = new Date();
  archiveBefore.setDate(archiveBefore.getDate() - ARCHIVE_AFTER_DAYS);

  const logsToArchive = await db
    .select({
      id: schema.auditLogs.id,
      timestamp: schema.auditLogs.timestamp,
    })
    .from(schema.auditLogs)
    .where(lte(schema.auditLogs.timestamp, archiveBefore.toISOString()))
    .limit(10000);

  if (logsToArchive.length === 0) {
    return c.json({
      success: true,
      data: {
        archivedCount: 0,
        message: "No logs to archive",
      },
    });
  }

  // In production, upload to S3 here
  const archived = await archiveLogs(logsToArchive, ARCHIVE_AFTER_DAYS);

  // Update status to archived
  const archivedIds = archived.map((log) => log.id);
  await db
    .update(schema.auditLogs)
    .set({
      archivedAt: new Date().toISOString(),
      storageLocation: archived[0]?.storageLocation || null,
    })
    .where(sql`${schema.auditLogs.id} in ${archivedIds}`);

  return c.json({
    success: true,
    data: {
      archivedCount: archived.length,
      storageLocation: archived[0]?.storageLocation || null,
    },
  });
});

export { auditLogsRoutes };
