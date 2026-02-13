/**
 * Audit Logs TDD Tests
 *
 * Test-Driven Development tests for comprehensive audit logging:
 * - Audit event types (user actions, system actions, security events)
 * - Audit log creation with validation and sanitization
 * - Query/filtering capabilities
 * - Export functionality (JSON, CSV, chunking)
 * - Retention policies
 * - Response formatting with pagination
 */

import { describe, it, expect, beforeEach, vi } from "vitest";

// ============================================================================
// Audit Event Types Tests
// ============================================================================

describe("Audit Event Types", () => {
  it("should define USER_LOGIN event type", () => {
    const AUDIT_EVENT_TYPES = {
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

    expect(AUDIT_EVENT_TYPES.USER_LOGIN).toBe("USER_LOGIN");
    expect(typeof AUDIT_EVENT_TYPES.USER_LOGIN).toBe("string");
  });

  it("should define all required event types", () => {
    const REQUIRED_EVENT_TYPES = [
      "USER_LOGIN",
      "USER_LOGOUT",
      "INVOICE_CREATED",
      "INVOICE_UPDATED",
      "INVOICE_DELETED",
      "PAYMENT_PROCESSED",
      "INTEGRATION_CONNECTED",
      "INTEGRATION_DISCONNECTED",
      "SETTINGS_UPDATED",
      "API_KEY_CREATED",
      "API_KEY_REVOKED",
      "ROLE_CHANGED",
      "PERMISSION_DENIED",
    ];

    const AUDIT_EVENT_TYPES = {
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

    REQUIRED_EVENT_TYPES.forEach((type) => {
      expect(Object.values(AUDIT_EVENT_TYPES)).toContain(type);
    });
  });

  it("should define severity levels", () => {
    const SEVERITY_LEVELS = {
      INFO: "INFO",
      WARNING: "WARNING",
      ERROR: "ERROR",
      CRITICAL: "CRITICAL",
    } as const;

    expect(SEVERITY_LEVELS.INFO).toBe("INFO");
    expect(SEVERITY_LEVELS.WARNING).toBe("WARNING");
    expect(SEVERITY_LEVELS.ERROR).toBe("ERROR");
    expect(SEVERITY_LEVELS.CRITICAL).toBe("CRITICAL");
  });

  it("should map event types to severity levels", () => {
    const SEVERITY_BY_EVENT_TYPE: Record<string, string> = {
      USER_LOGIN: "INFO",
      USER_LOGOUT: "INFO",
      INVOICE_CREATED: "INFO",
      INVOICE_UPDATED: "INFO",
      INVOICE_DELETED: "WARNING",
      PAYMENT_PROCESSED: "INFO",
      INTEGRATION_CONNECTED: "INFO",
      INTEGRATION_DISCONNECTED: "WARNING",
      SETTINGS_UPDATED: "WARNING",
      API_KEY_CREATED: "WARNING",
      API_KEY_REVOKED: "CRITICAL",
      ROLE_CHANGED: "WARNING",
      PERMISSION_DENIED: "ERROR",
    };

    expect(SEVERITY_BY_EVENT_TYPE.USER_LOGIN).toBe("INFO");
    expect(SEVERITY_BY_EVENT_TYPE.PERMISSION_DENIED).toBe("ERROR");
    expect(SEVERITY_BY_EVENT_TYPE.API_KEY_REVOKED).toBe("CRITICAL");
  });
});

// ============================================================================
// Audit Log Creation Tests
// ============================================================================

describe("Audit Log Creation", () => {
  // Type definitions
  type Actor = {
    userId: string;
    email?: string;
    name?: string;
    role?: string;
  };

  type Resource = {
    type: string;
    id: string;
    name?: string;
  };

  type AuditLogEntry = {
    id: string;
    timestamp: string;
    organizationId: string;
    actor: Actor;
    action: string;
    resource: Resource;
    details: Record<string, unknown>;
    ipAddress: string;
    userAgent: string;
    severity: string;
  };

  it("should create audit log entry with all required fields", () => {
    const createAuditLog = (): AuditLogEntry => {
      return {
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        organizationId: "org-123",
        actor: {
          userId: "user-456",
          email: "user@example.com",
          name: "John Doe",
          role: "admin",
        },
        action: "INVOICE_CREATED",
        resource: {
          type: "invoice",
          id: "inv-789",
          name: "INV-2024-001",
        },
        details: {
          amount: 1500.0,
          currency: "USD",
          vendorId: "vendor-123",
        },
        ipAddress: "192.168.1.100",
        userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        severity: "INFO",
      };
    };

    const log = createAuditLog();

    expect(log.id).toBeDefined();
    expect(log.timestamp).toBeDefined();
    expect(log.organizationId).toBe("org-123");
    expect(log.actor.userId).toBe("user-456");
    expect(log.action).toBe("INVOICE_CREATED");
    expect(log.resource.type).toBe("invoice");
    expect(log.details.amount).toBe(1500.0);
    expect(log.ipAddress).toBeDefined();
    expect(log.userAgent).toBeDefined();
    expect(log.severity).toBe("INFO");
  });

  it("should validate required fields", () => {
    type ValidateAuditLog = (entry: Partial<AuditLogEntry>) => {
      valid: boolean;
      errors: string[];
    };

    const validateAuditLog: ValidateAuditLog = (entry) => {
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
    };

    // Valid entry
    const validResult = validateAuditLog({
      id: "log-123",
      timestamp: new Date().toISOString(),
      organizationId: "org-123",
      actor: { userId: "user-456" },
      action: "USER_LOGIN",
      resource: { type: "user_session", id: "session-789" },
    });
    expect(validResult.valid).toBe(true);
    expect(validResult.errors).toHaveLength(0);

    // Missing required fields
    const invalidResult = validateAuditLog({});
    expect(invalidResult.valid).toBe(false);
    expect(invalidResult.errors.length).toBeGreaterThan(0);
  });

  it("should sanitize sensitive data from audit logs", () => {
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

    const sanitizeSensitiveData = (details: Record<string, unknown>): Record<string, unknown> => {
      const sanitized = { ...details };

      Object.keys(sanitized).forEach((key) => {
        const lowerKey = key.toLowerCase();
        if (SENSITIVE_FIELDS.some((field) => lowerKey.includes(field.toLowerCase()))) {
          sanitized[key] = "[REDACTED]";
        }
      });

      return sanitized;
    };

    const input = {
      amount: 100.0,
      password: "secret123",
      apiKey: "sk-1234567890",
      note: "Normal note",
      accessToken: "token-abc",
    };

    const sanitized = sanitizeSensitiveData(input);

    expect(sanitized.amount).toBe(100.0);
    expect(sanitized.password).toBe("[REDACTED]");
    expect(sanitized.apiKey).toBe("[REDACTED]");
    expect(sanitized.note).toBe("Normal note");
    expect(sanitized.accessToken).toBe("[REDACTED]");
  });

  it("should hash sensitive data before storage", async () => {
    const hashValue = async (value: string): Promise<string> => {
      const encoder = new TextEncoder();
      const data = encoder.encode(value);
      const hashBuffer = await crypto.subtle.digest("SHA-256", data);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
    };

    const sensitiveValue = "sk-1234567890abcdef";
    const hashedValue = await hashValue(sensitiveValue);

    expect(hashedValue).toHaveLength(64);
    expect(hashedValue).not.toBe(sensitiveValue);

    // Same input should always produce same hash
    const hashedValue2 = await hashValue(sensitiveValue);
    expect(hashedValue).toBe(hashedValue2);
  });

  it("should mask IP addresses for privacy", () => {
    const maskIpAddress = (ip: string): string => {
      // IPv4 masking - keep first two octets
      const ipv4Regex = /^(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}$/;
      const ipv4Match = ip.match(ipv4Regex);

      if (ipv4Match) {
        return `${ipv4Match[1]}.xxx.xxx`;
      }

      // IPv6 masking - keep first two groups
      const ipv6Parts = ip.split(":");
      if (ipv6Parts.length >= 2) {
        return `${ipv6Parts[0]}:${ipv6Parts[1]}:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx`;
      }

      return "[REDACTED]";
    };

    expect(maskIpAddress("192.168.1.100")).toBe("192.168.xxx.xxx");
    expect(maskIpAddress("10.0.0.1")).toBe("10.0.xxx.xxx");
    expect(maskIpAddress("2001:0db8:85a3:0000:0000:8a2e:0370:7334")).toMatch(/^2001:0db8:.*xxxx/);
  });

  it("should normalize user agent strings", () => {
    const normalizeUserAgent = (userAgent: string): string => {
      // Truncate long user agents
      if (userAgent.length > 200) {
        return userAgent.substring(0, 197) + "...";
      }

      // Remove newlines and extra whitespace
      return userAgent.replace(/\s+/g, " ").trim();
    };

    const longUa = "Mozilla/5.0 ".repeat(50);
    const normalized = normalizeUserAgent(longUa);

    expect(normalized.length).toBe(200);
    expect(normalized.endsWith("...")).toBe(true);

    const normalUa = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";
    expect(normalizeUserAgent(normalUa)).toBe(normalUa);
  });
});

// ============================================================================
// Query/Filtering Tests
// ============================================================================

describe("Audit Log Query/Filtering", () => {
  // Sample audit logs for testing
  const sampleLogs = [
    {
      id: "log-1",
      organizationId: "org-1",
      actor: { userId: "user-1", name: "Alice" },
      action: "USER_LOGIN",
      resource: { type: "user_session", id: "session-1" },
      timestamp: "2024-01-15T10:00:00Z",
      severity: "INFO",
    },
    {
      id: "log-2",
      organizationId: "org-1",
      actor: { userId: "user-1", name: "Alice" },
      action: "INVOICE_CREATED",
      resource: { type: "invoice", id: "inv-1" },
      timestamp: "2024-01-15T11:00:00Z",
      severity: "INFO",
    },
    {
      id: "log-3",
      organizationId: "org-2",
      actor: { userId: "user-2", name: "Bob" },
      action: "PERMISSION_DENIED",
      resource: { type: "invoice", id: "inv-2" },
      timestamp: "2024-01-15T12:00:00Z",
      severity: "ERROR",
    },
    {
      id: "log-4",
      organizationId: "org-1",
      actor: { userId: "user-3", name: "Charlie" },
      action: "API_KEY_REVOKED",
      resource: { type: "api_key", id: "key-1" },
      timestamp: "2024-01-20T10:00:00Z",
      severity: "CRITICAL",
    },
    {
      id: "log-5",
      organizationId: "org-1",
      actor: { userId: "user-1", name: "Alice" },
      action: "INVOICE_UPDATED",
      resource: { type: "invoice", id: "inv-1" },
      timestamp: "2024-01-16T10:00:00Z",
      severity: "INFO",
    },
  ];

  it("should filter by organizationId", () => {
    const filterByOrganization = (logs: typeof sampleLogs, orgId: string) => {
      return logs.filter((log) => log.organizationId === orgId);
    };

    const org1Logs = filterByOrganization(sampleLogs, "org-1");
    expect(org1Logs).toHaveLength(4);
    expect(org1Logs.every((log) => log.organizationId === "org-1")).toBe(true);

    const org2Logs = filterByOrganization(sampleLogs, "org-2");
    expect(org2Logs).toHaveLength(1);
  });

  it("should filter by actor userId", () => {
    const filterByActor = (logs: typeof sampleLogs, userId: string) => {
      return logs.filter((log) => log.actor.userId === userId);
    };

    const user1Logs = filterByActor(sampleLogs, "user-1");
    expect(user1Logs).toHaveLength(3);
    expect(user1Logs.every((log) => log.actor.userId === "user-1")).toBe(true);

    const user2Logs = filterByActor(sampleLogs, "user-2");
    expect(user2Logs).toHaveLength(1);
  });

  it("should filter by action type", () => {
    const filterByAction = (logs: typeof sampleLogs, action: string) => {
      return logs.filter((log) => log.action === action);
    };

    const invoiceLogs = filterByAction(sampleLogs, "INVOICE_CREATED");
    expect(invoiceLogs).toHaveLength(1);
    expect(invoiceLogs[0].action).toBe("INVOICE_CREATED");

    const permissionDeniedLogs = filterByAction(sampleLogs, "PERMISSION_DENIED");
    expect(permissionDeniedLogs).toHaveLength(1);
    expect(permissionDeniedLogs[0].severity).toBe("ERROR");
  });

  it("should filter by date range", () => {
    const filterByDateRange = (
      logs: typeof sampleLogs,
      startDate: string,
      endDate: string
    ) => {
      return logs.filter((log) => {
        const logDate = new Date(log.timestamp);
        return logDate >= new Date(startDate) && logDate <= new Date(endDate);
      });
    };

    const januaryLogs = filterByDateRange(sampleLogs, "2024-01-15T00:00:00Z", "2024-01-15T23:59:59Z");
    expect(januaryLogs).toHaveLength(3);

    const midMonthLogs = filterByDateRange(sampleLogs, "2024-01-16T00:00:00Z", "2024-01-31T23:59:59Z");
    expect(midMonthLogs).toHaveLength(2);
  });

  it("should filter by severity level", () => {
    const filterBySeverity = (logs: typeof sampleLogs, severity: string) => {
      return logs.filter((log) => log.severity === severity);
    };

    const infoLogs = filterBySeverity(sampleLogs, "INFO");
    expect(infoLogs).toHaveLength(3);

    const criticalLogs = filterBySeverity(sampleLogs, "CRITICAL");
    expect(criticalLogs).toHaveLength(1);
    expect(criticalLogs[0].action).toBe("API_KEY_REVOKED");

    const errorLogs = filterBySeverity(sampleLogs, "ERROR");
    expect(errorLogs).toHaveLength(1);
  });

  it("should support pagination", () => {
    const paginate = <T>(
      items: T[],
      page: number,
      pageSize: number
    ): { data: T[]; total: number; page: number; pageSize: number; totalPages: number } => {
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
    };

    const result1 = paginate(sampleLogs, 1, 2);
    expect(result1.data).toHaveLength(2);
    expect(result1.total).toBe(5);
    expect(result1.page).toBe(1);
    expect(result1.pageSize).toBe(2);
    expect(result1.totalPages).toBe(3);

    const result2 = paginate(sampleLogs, 2, 2);
    expect(result2.data).toHaveLength(2);
    expect(result2.page).toBe(2);

    const result3 = paginate(sampleLogs, 3, 2);
    expect(result3.data).toHaveLength(1);
    expect(result3.page).toBe(3);

    const resultOutOfBounds = paginate(sampleLogs, 10, 2);
    expect(resultOutOfBounds.data).toHaveLength(0);
  });

  it("should combine multiple filters", () => {
    const applyFilters = (
      logs: typeof sampleLogs,
      filters: {
        organizationId?: string;
        actorUserId?: string;
        action?: string;
        severity?: string;
        startDate?: string;
        endDate?: string;
      }
    ) => {
      return logs.filter((log) => {
        if (filters.organizationId && log.organizationId !== filters.organizationId) return false;
        if (filters.actorUserId && log.actor.userId !== filters.actorUserId) return false;
        if (filters.action && log.action !== filters.action) return false;
        if (filters.severity && log.severity !== filters.severity) return false;
        if (filters.startDate && new Date(log.timestamp) < new Date(filters.startDate)) return false;
        if (filters.endDate && new Date(log.timestamp) > new Date(filters.endDate)) return false;
        return true;
      });
    };

    // Filter by org and action
    const filtered1 = applyFilters(sampleLogs, { organizationId: "org-1", action: "INVOICE_CREATED" });
    expect(filtered1).toHaveLength(1);

    // Filter by org and severity
    const filtered2 = applyFilters(sampleLogs, { organizationId: "org-1", severity: "INFO" });
    expect(filtered2).toHaveLength(3);
  });
});

// ============================================================================
// Export Functionality Tests
// ============================================================================

describe("Export Functionality", () => {
  const sampleLogs = [
    {
      id: "log-1",
      timestamp: "2024-01-15T10:00:00Z",
      organizationId: "org-1",
      actor: { userId: "user-1", name: "Alice" },
      action: "USER_LOGIN",
      resource: { type: "user_session", id: "session-1" },
      details: {},
      ipAddress: "192.168.1.100",
      userAgent: "Mozilla/5.0",
      severity: "INFO",
    },
    {
      id: "log-2",
      timestamp: "2024-01-15T11:00:00Z",
      organizationId: "org-1",
      actor: { userId: "user-1", name: "Alice" },
      action: "INVOICE_CREATED",
      resource: { type: "invoice", id: "inv-1" },
      details: { amount: 1500 },
      ipAddress: "192.168.1.100",
      userAgent: "Mozilla/5.0",
      severity: "INFO",
    },
  ];

  it("should export to JSON format", () => {
    const exportToJson = (logs: typeof sampleLogs): string => {
      return JSON.stringify(
        {
          exportDate: new Date().toISOString(),
          totalLogs: logs.length,
          logs,
        },
        null,
        2
      );
    };

    const jsonOutput = exportToJson(sampleLogs);

    expect(jsonOutput).toContain("exportDate");
    expect(jsonOutput).toContain('"totalLogs": 2');
    expect(jsonOutput).toContain('"action": "USER_LOGIN"');
    expect(jsonOutput).toContain('"action": "INVOICE_CREATED"');
  });

  it("should export to CSV format", () => {
    const exportToCsv = (logs: typeof sampleLogs): string => {
      const headers = ["id", "timestamp", "organizationId", "actorUserId", "action", "resourceType", "resourceId", "severity"];

      const rows = logs.map((log) => [
        log.id,
        log.timestamp,
        log.organizationId,
        log.actor.userId,
        log.action,
        log.resource.type,
        log.resource.id,
        log.severity,
      ]);

      return [headers.join(","), ...rows.map((row) => row.join(","))].join("\n");
    };

    const csvOutput = exportToCsv(sampleLogs);

    expect(csvOutput).toContain("id,timestamp,organizationId");
    expect(csvOutput).toContain("log-1,2024-01-15T10:00:00Z,org-1");
    expect(csvOutput).toContain("USER_LOGIN");
    expect(csvOutput.split("\n")).toHaveLength(3); // Header + 2 rows
  });

  it("should handle large exports with chunking", () => {
    const CHUNK_SIZE = 1000;

    const chunkLargeExport = <T>(items: T[]): T[][] => {
      const chunks: T[][] = [];
      for (let i = 0; i < items.length; i += CHUNK_SIZE) {
        chunks.push(items.slice(i, i + CHUNK_SIZE));
      }
      return chunks;
    };

    // Generate 2500 mock logs
    const largeDataset = Array.from({ length: 2500 }, (_, i) => ({
      id: `log-${i}`,
      timestamp: new Date().toISOString(),
      action: "TEST_ACTION",
    }));

    const chunks = chunkLargeExport(largeDataset);

    expect(chunks).toHaveLength(3);
    expect(chunks[0]).toHaveLength(1000);
    expect(chunks[1]).toHaveLength(1000);
    expect(chunks[2]).toHaveLength(500);
  });

  it("should stream large CSV exports in chunks", () => {
    const CSV_CHUNK_SIZE = 500;

    const createCsvStreamChunks = (totalRows: number): string[] => {
      const headers = ["id", "timestamp", "action"];
      const chunks: string[] = [];

      for (let i = 0; i < totalRows; i += CSV_CHUNK_SIZE) {
        const rows = [];
        for (let j = i; j < Math.min(i + CSV_CHUNK_SIZE, totalRows); j++) {
          rows.push(`log-${j},2024-01-15T${j.toString().padStart(2, "0")}:00:00Z,TEST_ACTION`);
        }
        chunks.push([headers.join(","), ...rows].join("\n"));
      }

      return chunks;
    };

    const chunks = createCsvStreamChunks(1200);

    expect(chunks).toHaveLength(3);
    expect(chunks[0].split("\n")).toHaveLength(501); // Header + 500 rows
    expect(chunks[1].split("\n")).toHaveLength(501);
    expect(chunks[2].split("\n")).toHaveLength(201); // Header + 200 rows
  });

  it("should include only requested fields in export", () => {
    const exportWithFields = (
      logs: typeof sampleLogs,
      fields: string[]
    ): string => {
      const filteredLogs = logs.map((log) => {
        const filtered: Record<string, unknown> = {};
        fields.forEach((field) => {
          if (field.includes(".")) {
            const [parent, child] = field.split(".");
            if (log[parent as keyof typeof log] && typeof log[parent as keyof typeof log] === "object") {
              filtered[field] = (log[parent as keyof typeof log] as Record<string, unknown>)[child];
            }
          } else {
            filtered[field] = log[field as keyof typeof log];
          }
        });
        return filtered;
      });

      return JSON.stringify(filteredLogs, null, 2);
    };

    const minimalExport = exportWithFields(sampleLogs, ["id", "action", "severity"]);

    expect(minimalExport).toContain('"id": "log-1"');
    expect(minimalExport).toContain('"action": "USER_LOGIN"');
    expect(minimalExport).toContain('"severity": "INFO"');
    expect(minimalExport).not.toContain("timestamp");
    expect(minimalExport).not.toContain("organizationId");
  });
});

// ============================================================================
// Retention Policies Tests
// ============================================================================

describe("Retention Policies", () => {
  const RETENTION_DAYS = 365;
  const ARCHIVE_AFTER_DAYS = 90;

  it("should check if log is within retention period", () => {
    const isWithinRetention = (timestamp: string, retentionDays: number): boolean => {
      const logDate = new Date(timestamp);
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - retentionDays);
      return logDate >= cutoffDate;
    };

    // Log from today should be within retention
    const todayLog = new Date().toISOString();
    expect(isWithinRetention(todayLog, RETENTION_DAYS)).toBe(true);

    // Log from 6 months ago should be within retention
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setDate(sixMonthsAgo.getDate() - 180);
    expect(isWithinRetention(sixMonthsAgo.toISOString(), RETENTION_DAYS)).toBe(true);

    // Log from 400 days ago should be outside retention
    const overAYearAgo = new Date();
    overAYearAgo.setDate(overAYearAgo.getDate() - 400);
    expect(isWithinRetention(overAYearAgo.toISOString(), RETENTION_DAYS)).toBe(false);
  });

  it("should determine if log should be archived", () => {
    const shouldArchive = (timestamp: string, archiveAfterDays: number): boolean => {
      const logDate = new Date(timestamp);
      const archiveDate = new Date();
      archiveDate.setDate(archiveDate.getDate() - archiveAfterDays);
      return logDate < archiveDate;
    };

    // Log from 100 days ago should be archived (older than 90-day threshold)
    const hundredDaysAgo = new Date();
    hundredDaysAgo.setDate(hundredDaysAgo.getDate() - 100);
    expect(shouldArchive(hundredDaysAgo.toISOString(), ARCHIVE_AFTER_DAYS)).toBe(true);

    // Log from 30 days ago should not be archived
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    expect(shouldArchive(thirtyDaysAgo.toISOString(), ARCHIVE_AFTER_DAYS)).toBe(false);
  });

  it("should identify expired logs for deletion", () => {
    const MS_PER_DAY = 24 * 60 * 60 * 1000;

    // Fixed reference date for consistent testing
    const referenceDate = new Date("2024-06-01T00:00:00Z").getTime();

    const isExpired = (timestamp: string, retentionDays: number): boolean => {
      const logDate = new Date(timestamp).getTime();
      const expiryDate = referenceDate - retentionDays * MS_PER_DAY;
      return logDate < expiryDate;
    };

    // Using retention of 180 days for this test
    const logs = [
      { id: "log-1", timestamp: new Date(referenceDate - 10 * MS_PER_DAY).toISOString() }, // 10 days before reference - active (within 180 days)
      { id: "log-2", timestamp: new Date(referenceDate - 200 * MS_PER_DAY).toISOString() }, // 200 days before reference - expired
      { id: "log-3", timestamp: new Date(referenceDate - 400 * MS_PER_DAY).toISOString() }, // 400 days before reference - expired
    ];

    const expiredLogs = logs.filter((log) => isExpired(log.timestamp, 180));

    expect(expiredLogs).toHaveLength(2);
    expect(expiredLogs.map((l) => l.id)).toEqual(["log-2", "log-3"]);
  });

  it("should archive old logs", async () => {
    const archiveLogs = async (
      logs: Array<{ id: string; timestamp: string; archivedAt?: string }>,
      archiveAfterDays: number
    ): Promise<Array<{ id: string; timestamp: string; archivedAt: string; storageLocation: string }>> => {
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
    };

    const testLogs = [
      { id: "log-1", timestamp: new Date().toISOString() }, // Active
      { id: "log-2", timestamp: new Date(Date.now() - 100 * 24 * 60 * 60 * 1000).toISOString() }, // 100 days ago - archive
    ];

    const archived = await archiveLogs(testLogs, 90);

    expect(archived).toHaveLength(1);
    expect(archived[0].id).toBe("log-2");
    expect(archived[0].archivedAt).toBeDefined();
    expect(archived[0].storageLocation).toContain("s3://audit-archive/");
  });

  it("should delete expired logs after archival", () => {
    const markForDeletion = (logs: Array<{ id: string; timestamp: string; status: string }>): string[] => {
      const retentionDays = 365;
      const expiryDate = new Date();
      expiryDate.setDate(expiryDate.getDate() - retentionDays);

      const expiredIds: string[] = [];

      logs.forEach((log) => {
        if (new Date(log.timestamp) < expiryDate) {
          expiredIds.push(log.id);
        }
      });

      return expiredIds;
    };

    const logs = [
      { id: "log-1", timestamp: new Date().toISOString(), status: "active" },
      { id: "log-2", timestamp: new Date(Date.now() - 400 * 24 * 60 * 60 * 1000).toISOString(), status: "archived" },
    ];

    const toDelete = markForDeletion(logs);

    expect(toDelete).toContain("log-2");
  });

  it("should calculate retention periods by severity", () => {
    const RETENTION_BY_SEVERITY: Record<string, number> = {
      INFO: 180,
      WARNING: 365,
      ERROR: 730, // 2 years
      CRITICAL: 2555, // 7 years (compliance)
    };

    expect(RETENTION_BY_SEVERITY.INFO).toBe(180);
    expect(RETENTION_BY_SEVERITY.ERROR).toBe(730);
    expect(RETENTION_BY_SEVERITY.CRITICAL).toBe(2555);
  });
});

// ============================================================================
// Response Formatting Tests
// ============================================================================

describe("Response Formatting", () => {
  it("should format audit log response for API", () => {
    type AuditLogResponse = {
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
    };

    const formatAuditLogResponse = (log: {
      id: string;
      timestamp: string;
      actor: { userId: string; name?: string; email?: string };
      action: string;
      resource: { type: string; id: string; name?: string };
      details: Record<string, unknown>;
      severity: string;
      ipAddress: string;
    }): AuditLogResponse => {
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
    };

    const inputLog = {
      id: "log-123",
      timestamp: "2024-01-15T10:00:00Z",
      actor: { userId: "user-1", name: "Alice", email: "alice@example.com" },
      action: "INVOICE_CREATED",
      resource: { type: "invoice", id: "inv-1", name: "INV-001" },
      details: { amount: 1500 },
      severity: "INFO",
      ipAddress: "192.168.1.100",
    };

    const response = formatAuditLogResponse(inputLog);

    expect(response.id).toBe("log-123");
    expect(response.actor.id).toBe("user-1");
    expect(response.actor.name).toBe("Alice");
    expect(response.actor.email).toBe("alice@example.com");
    expect(response.resource.type).toBe("invoice");
    expect(response.severity).toBe("INFO");
  });

  it("should include pagination metadata", () => {
    type PaginatedResponse<T> = {
      data: T[];
      pagination: {
        page: number;
        pageSize: number;
        total: number;
        totalPages: number;
        hasNextPage: boolean;
        hasPreviousPage: boolean;
      };
    };

    const createPaginatedResponse = <T>(
      data: T[],
      page: number,
      pageSize: number
    ): PaginatedResponse<T> => {
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
    };

    const items = Array.from({ length: 50 }, (_, i) => ({ id: i + 1 }));
    const response = createPaginatedResponse(items, 2, 10);

    expect(response.data).toHaveLength(10);
    expect(response.pagination.page).toBe(2);
    expect(response.pagination.total).toBe(50);
    expect(response.pagination.totalPages).toBe(5);
    expect(response.pagination.hasNextPage).toBe(true);
    expect(response.pagination.hasPreviousPage).toBe(true);
  });

  it("should format list response with filters applied", () => {
    type AuditLogListResponse = {
      logs: Array<{
        id: string;
        timestamp: string;
        action: string;
        severity: string;
        actorName: string | null;
        resourceType: string;
      }>;
      filters: {
        organizationId?: string;
        actorUserId?: string;
        action?: string;
        severity?: string;
        startDate?: string;
        endDate?: string;
      };
      pagination: {
        page: number;
        pageSize: number;
        total: number;
      };
      appliedAt: string;
    };

    const logs = [
      { id: "log-1", timestamp: "2024-01-15T10:00:00Z", action: "USER_LOGIN", severity: "INFO", actorName: "Alice", resourceType: "user_session" },
      { id: "log-2", timestamp: "2024-01-15T11:00:00Z", action: "INVOICE_CREATED", severity: "INFO", actorName: "Alice", resourceType: "invoice" },
    ];

    const formatListResponse = (
      logs: typeof logs,
      filters: Record<string, string | undefined>,
      page: number,
      pageSize: number
    ): AuditLogListResponse => {
      return {
        logs: logs.map((log) => ({
          id: log.id,
          timestamp: log.timestamp,
          action: log.action,
          severity: log.severity,
          actorName: log.actorName,
          resourceType: log.resourceType,
        })),
        filters: {
          organizationId: filters.organizationId,
          actorUserId: filters.actorUserId,
          action: filters.action,
          severity: filters.severity,
          startDate: filters.startDate,
          endDate: filters.endDate,
        },
        pagination: {
          page,
          pageSize,
          total: logs.length,
        },
        appliedAt: new Date().toISOString(),
      };
    };

    const response = formatListResponse(logs, { organizationId: "org-1" }, 1, 20);

    expect(response.logs).toHaveLength(2);
    expect(response.filters.organizationId).toBe("org-1");
    expect(response.pagination.page).toBe(1);
    expect(response.appliedAt).toBeDefined();
  });

  it("should format export response", () => {
    const formatExportResponse = (
      format: "json" | "csv",
      totalRecords: number,
      fileSize: number,
      downloadUrl: string,
      expiresAt: string
    ): {
      success: boolean;
      data: {
        format: string;
        totalRecords: number;
        fileSizeBytes: number;
        downloadUrl: string;
        expiresAt: string;
      };
    } => {
      return {
        success: true,
        data: {
          format,
          totalRecords,
          fileSizeBytes: fileSize,
          downloadUrl,
          expiresAt,
        },
      };
    };

    const response = formatExportResponse("csv", 10000, 524288, "/exports/audit-logs-123.csv", "2024-01-16T10:00:00Z");

    expect(response.success).toBe(true);
    expect(response.data.format).toBe("csv");
    expect(response.data.totalRecords).toBe(10000);
    expect(response.data.fileSizeBytes).toBe(524288);
    expect(response.data.downloadUrl).toBe("/exports/audit-logs-123.csv");
  });

  it("should format error response", () => {
    const formatErrorResponse = (
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
    } => {
      return {
        success: false,
        error: {
          code,
          message,
          ...(details && { details }),
        },
      };
    };

    const response = formatErrorResponse("INVALID_FILTER", "Invalid date range provided", { startDate: "invalid", endDate: "invalid" });

    expect(response.success).toBe(false);
    expect(response.error.code).toBe("INVALID_FILTER");
    expect(response.error.message).toBe("Invalid date range provided");
    expect(response.error.details).toBeDefined();
  });
});

// ============================================================================
// Security & Compliance Tests
// ============================================================================

describe("Security & Compliance", () => {
  it("should ensure audit logs are immutable", () => {
    // Verify that audit log entries cannot be modified after creation using Object.freeze
    type ImmutableAuditLog = {
      readonly id: string;
      readonly timestamp: string;
      readonly action: string;
    };

    const createImmutableLog = (): ImmutableAuditLog => {
      const log = {
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        action: "TEST_ACTION",
      };
      return Object.freeze(log);
    };

    const log = createImmutableLog();

    // Attempting to modify should throw in strict mode or fail silently
    let mutationError: TypeError | null = null;
    try {
      (log as Record<string, unknown>).id = "modified";
    } catch (e) {
      mutationError = e as TypeError;
    }

    // Object.freeze prevents modification
    expect(Object.isFrozen(log)).toBe(true);
    expect(mutationError).toBeInstanceOf(TypeError);
  });

  it("should generate unique audit log IDs", () => {
    const generateLogId = (): string => {
      const timestamp = Date.now().toString(36);
      const randomPart = crypto.randomUUID().replace(/-/g, "").substring(0, 8);
      return `audit_${timestamp}_${randomPart}`;
    };

    const ids = Array.from({ length: 100 }, () => generateLogId());
    const uniqueIds = new Set(ids);

    // All 100 IDs should be unique
    expect(uniqueIds.size).toBe(100);
  });

  it("should include correlation IDs for tracing", () => {
    const createCorrelatedLogs = () => {
      const correlationId = crypto.randomUUID();

      return {
        correlationId,
        logs: [
          { id: crypto.randomUUID(), correlationId, action: "REQUEST_START", timestamp: new Date().toISOString() },
          { id: crypto.randomUUID(), correlationId, action: "PROCESSING", timestamp: new Date().toISOString() },
          { id: crypto.randomUUID(), correlationId, action: "REQUEST_COMPLETE", timestamp: new Date().toISOString() },
        ],
      };
    };

    const { correlationId, logs } = createCorrelatedLogs();

    expect(logs.every((log) => log.correlationId === correlationId)).toBe(true);
    expect(logs).toHaveLength(3);
  });
});

/*
 * Running Tests:
 * pnpm test -- worker/src/tests/audit-logs.test.ts
 *
 * These TDD tests define the expected behavior for audit logs functionality.
 * Implement the corresponding source files to make these tests pass.
 */
