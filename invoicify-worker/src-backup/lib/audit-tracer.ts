/**
 * Audit Tracer Module
 *
 * Implements comprehensive audit trail per PRD requirement:
 * - Agent run audit trail for compliance
 * - Decision traceability
 * - Risk assessment history
 */

import { getDb, schema } from "../db";
import { eq, sql, and, desc, gte } from "drizzle-orm";
import type { Env } from "../db";

/**
 * Audit event types
 */
export const AuditEventType = {
  INVOICE_RECEIVED: "INVOICE_RECEIVED",
  INVOICE_EXTRACTED: "INVOICE_EXTRACTED",
  RISK_ASSESSED: "RISK_ASSESSED",
  APPROVAL_DECISION: "APPROVAL_DECISION",
  PAYMENT_SCHEDULED: "PAYMENT_SCHEDULED",
  PAYMENT_EXECUTED: "PAYMENT_EXECUTED",
  VENDOR_UPDATED: "VENDOR_UPDATED",
  SYSTEM_ACTION: "SYSTEM_ACTION",
  FEEDBACK_RECEIVED: "FEEDBACK_RECEIVED",
} as const;

export type AuditEventTypeType = (typeof AuditEventType)[keyof typeof AuditEventType];

/**
 * Audit event data
 */
export interface AuditEvent {
  traceId: string;
  spanId: string;
  eventType: AuditEventTypeType;
  entityType: "invoice" | "vendor" | "payment" | "approval";
  entityId: string;
  action: string;
  actor: "agent" | "human" | "system";
  details: Record<string, any>;
  riskScore?: number;
  riskSignals?: string[];
  success?: boolean;
  errorMessage?: string;
}

/**
 * Audit tracer class for compliance logging
 */
export class AuditTracer {
  private env: Env;
  private traceId: string;

  constructor(env: Env, traceId?: string) {
    this.env = env;
    this.traceId = traceId || crypto.randomUUID();
  }

  /**
   * Log an audit event
   */
  async log(event: Omit<AuditEvent, "traceId" | "spanId">): Promise<string> {
    const db = getDb(this.env);
    const eventId = crypto.randomUUID();
    const spanId = crypto.randomUUID();

    try {
      await db.insert(schema.auditLogs).values({
        id: eventId,
        action: event.eventType,
        entityType: event.entityType,
        entityId: event.entityId,
        performedBy: event.actor,
        performedAt: new Date().toISOString(),
        changes: JSON.stringify(event.details),
        metadata: JSON.stringify({
          riskScore: event.riskScore,
          riskSignals: event.riskSignals,
          traceId: this.traceId,
          spanId,
          success: event.success,
          errorMessage: event.errorMessage,
        }),
      });

      return eventId;
    } catch (error) {
      console.error("Audit log error:", error);
      return "";
    }
  }

  /**
   * Log invoice received
   */
  async logInvoiceReceived(
    invoiceId: string,
    vendorName: string,
    amount: number,
    fileName?: string
  ): Promise<string> {
    return this.log({
      eventType: AuditEventType.INVOICE_RECEIVED,
      entityType: "invoice",
      entityId: invoiceId,
      action: "received",
      actor: "system",
      details: {
        vendorName,
        amount,
        fileName,
      },
    });
  }

  /**
   * Log risk assessment
   */
  async logRiskAssessment(
    invoiceId: string,
    riskScore: number,
    riskLevel: string,
    signals: string[],
    action: string
  ): Promise<string> {
    return this.log({
      eventType: AuditEventType.RISK_ASSESSED,
      entityType: "invoice",
      entityId: invoiceId,
      action: "risk_assessed",
      actor: "agent",
      details: {
        riskLevel,
        action,
      },
      riskScore,
      riskSignals: signals,
    });
  }

  /**
   * Log approval decision
   */
  async logApprovalDecision(
    invoiceId: string,
    decision: string,
    approver: string,
    riskScore: number,
    reason?: string
  ): Promise<string> {
    return this.log({
      eventType: AuditEventType.APPROVAL_DECISION,
      entityType: "invoice",
      entityId: invoiceId,
      action: decision,
      actor: approver === "system" ? "agent" : "human",
      details: {
        reason,
      },
      riskScore,
      success: decision === "approved",
    });
  }

  /**
   * Log payment scheduled
   */
  async logPaymentScheduled(
    invoiceId: string,
    amount: number,
    scheduledDate: string,
    paymentTerms: number
  ): Promise<string> {
    return this.log({
      eventType: AuditEventType.PAYMENT_SCHEDULED,
      entityType: "payment",
      entityId: invoiceId,
      action: "schedule",
      actor: "agent",
      details: {
        amount,
        scheduledDate,
        paymentTerms,
      },
    });
  }

  /**
   * Log feedback received
   */
  async logFeedbackReceived(
    invoiceId: string,
    vendorId: string,
    decision: string,
    originalRiskScore: number
  ): Promise<string> {
    return this.log({
      eventType: AuditEventType.FEEDBACK_RECEIVED,
      entityType: "invoice",
      entityId: invoiceId,
      action: "feedback",
      actor: "human",
      details: {
        vendorId,
        decision,
        originalRiskScore,
      },
      riskScore: originalRiskScore,
    });
  }

  /**
   * Get trace ID
   */
  getTraceId(): string {
    return this.traceId;
  }

  /**
   * Create child tracer with same trace
   */
  child(): AuditTracer {
    return new AuditTracer(this.env, this.traceId);
  }
}

/**
 * Get audit trail for an invoice
 */
export async function getInvoiceAuditTrail(
  env: Env,
  invoiceId: string
): Promise<{
  events: Array<{
    action: string;
    performedAt: string;
    performedBy: string;
    details: Record<string, any>;
  }>;
}> {
  const db = getDb(env);

  const events = await db
    .select({
      action: schema.auditLogs.action,
      performedAt: schema.auditLogs.performedAt,
      performedBy: schema.auditLogs.performedBy,
      changes: schema.auditLogs.changes,
    })
    .from(schema.auditLogs)
    .where(eq(schema.auditLogs.entityId, invoiceId))
    .orderBy(schema.auditLogs.performedAt);

  return {
    events: events.map((e) => ({
      action: e.action || "",
      performedAt: e.performedAt || new Date().toISOString(),
      performedBy: e.performedBy || "unknown",
      details: e.changes ? JSON.parse(e.changes) : {},
    })),
  };
}

/**
 * Get audit statistics
 */
export async function getAuditStats(
  env: Env,
  startDate?: string
): Promise<{
  totalEvents: number;
  byType: Record<string, number>;
  byActor: Record<string, number>;
  recentActivity: Array<{ action: string; count: number }>;
}> {
  const db = getDb(env);

  const condition = startDate
    ? sql`${schema.auditLogs.performedAt} > '${startDate}'`
    : sql`1=1`;

  const events = await db
    .select({
      action: schema.auditLogs.action,
    })
    .from(schema.auditLogs)
    .where(condition);

  const byType: Record<string, number> = {};
  const byActor: Record<string, number> = {};

  for (const event of events) {
    byType[event.action] = (byType[event.action] || 0) + 1;
  }

  return {
    totalEvents: events.length,
    byType,
    byActor,
    recentActivity: Object.entries(byType).map(([action, count]) => ({
      action,
      count,
    })),
  };
}

/**
 * Create audit middleware for routes
 */
export function createAuditMiddleware(eventType: AuditEventTypeType) {
  return async function auditMiddleware(
    env: Env,
    invoiceId: string,
    details: Record<string, any>
  ): Promise<void> {
    const tracer = new AuditTracer(env);
    await tracer.log({
      eventType,
      entityType: "invoice",
      entityId: invoiceId,
      action: eventType.toLowerCase().replace("_", "-"),
      actor: "system",
      details,
    });
  };
}
