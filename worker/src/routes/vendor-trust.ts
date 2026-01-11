/**
 * Vendor Trust Routes
 *
 * Implements PRD Section E:
 * - Learn from approvals/rejections
 * - Update vendor trust scores
 * - View trust history and trends
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  updateVendorTrust,
  updateRiskWeights,
  getVendorTrustHistory,
  calculateOptimalThreshold,
  type ApprovalDecision,
} from "../lib/vendor-trust";
import { AuditTracer } from "../lib/audit-tracer";
import { eq, sql } from "drizzle-orm";
import type { Env } from "../db";

const vendorTrustRoutes = new Hono<{ Bindings: Env }>();

/**
 * Update vendor trust based on approval decision
 * POST /api/v1/vendor-trust/:vendorId/feedback
 */
vendorTrustRoutes.post("/:vendorId/feedback", async (c) => {
  const env = c.env;
  const vendorId = c.req.param("vendorId");
  const body = await c.req.json<{
    decision: ApprovalDecision;
    invoiceId: string;
    originalRiskScore: number;
    isNewVendor?: boolean;
  }>();

  const { decision, invoiceId, originalRiskScore, isNewVendor } = body;

  if (!decision || !invoiceId || originalRiskScore === undefined) {
    return c.json({ error: "Missing required fields" }, 400);
  }

  const result = await updateVendorTrust(env, vendorId, decision, originalRiskScore, isNewVendor || false);

  // Log audit event
  const tracer = new AuditTracer(env);
  await tracer.log({
    eventType: "FEEDBACK_RECEIVED" as any,
    entityType: "vendor",
    entityId: vendorId,
    action: `trust_${decision}`,
    actor: "human",
    details: {
      decision,
      invoiceId,
      originalRiskScore,
      newTrustScore: result.newTrustScore,
    },
    riskScore: originalRiskScore,
  });

  return c.json({
    success: true,
    data: {
      adjustment: result.adjustment,
      newTrustScore: result.newTrustScore,
      decision,
      vendorId,
    },
  });
});

/**
 * Get vendor trust details
 * GET /api/v1/vendor-trust/:vendorId
 */
vendorTrustRoutes.get("/:vendorId", async (c) => {
  const env = c.env;
  const vendorId = c.req.param("vendorId");
  const db = getDb(env);

  const [vendor] = await db
    .select({
      id: schema.vendors.id,
      name: schema.vendors.name,
      riskLevel: schema.vendors.riskLevel,
      totalInvoices: schema.vendors.totalInvoices,
      avgInvoiceAmount: schema.vendors.avgInvoiceAmount,
      createdAt: schema.vendors.createdAt,
      updatedAt: schema.vendors.updatedAt,
    })
    .from(schema.vendors)
    .where(eq(schema.vendors.id, vendorId))
    .limit(1);

  if (!vendor) {
    return c.json({ error: "Vendor not found" }, 404);
  }

  const trustHistory = await getVendorTrustHistory(env, vendorId);

  // Convert riskLevel to trust score
  const trustScore =
    vendor.riskLevel === "LOW"
      ? 0.9
      : vendor.riskLevel === "MEDIUM"
        ? 0.6
        : vendor.riskLevel === "HIGH"
          ? 0.3
          : 0.5;

  return c.json({
    vendorId,
    vendorName: vendor.name,
    riskLevel: vendor.riskLevel,
    trustScore,
    trustHistory,
    stats: {
      totalInvoices: vendor.totalInvoices,
      avgInvoiceAmount: vendor.avgInvoiceAmount,
      createdAt: vendor.createdAt,
      updatedAt: vendor.updatedAt,
    },
  });
});

/**
 * Get vendor trust history
 * GET /api/v1/vendor-trust/:vendorId/history
 */
vendorTrustRoutes.get("/:vendorId/history", async (c) => {
  const env = c.env;
  const vendorId = c.req.param("vendorId");

  const history = await getVendorTrustHistory(env, vendorId);

  return c.json({
    vendorId,
    ...history,
  });
});

/**
 * Update risk weights based on accumulated feedback
 * POST /api/v1/vendor-trust/weights/update
 */
vendorTrustRoutes.post("/weights/update", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    feedbackContexts: Array<{
      vendorId: string;
      invoiceId: string;
      originalRiskScore: number;
      originalConfidence: number;
      approvalDecision: ApprovalDecision;
      actualAmount: number;
      isDuplicate?: boolean;
    }>;
  }>();

  const result = await updateRiskWeights(env, body.feedbackContexts || []);

  return c.json({
    success: true,
    data: result,
  });
});

/**
 * Get optimal thresholds
 * GET /api/v1/vendor-trust/thresholds
 */
vendorTrustRoutes.get("/thresholds", async (c) => {
  const env = c.env;

  const thresholds = await calculateOptimalThreshold(env);

  return c.json({
    success: true,
    data: thresholds,
  });
});

/**
 * Get all vendors by trust level
 * GET /api/v1/vendor-trust/list
 */
vendorTrustRoutes.get("/list", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const levelFilter = c.req.query("level");

  let query = db
    .select({
      id: schema.vendors.id,
      name: schema.vendors.name,
      riskLevel: schema.vendors.riskLevel,
      totalInvoices: schema.vendors.totalInvoices,
      avgInvoiceAmount: schema.vendors.avgInvoiceAmount,
    })
    .from(schema.vendors);

  if (levelFilter) {
    query = query.where(eq(schema.vendors.riskLevel, levelFilter.toUpperCase())) as any;
  }

  const vendors = await query;

  // Convert risk levels to trust scores
  const vendorsWithTrust = vendors.map((v) => ({
    ...v,
    trustScore:
      v.riskLevel === "LOW"
        ? 0.9
        : v.riskLevel === "MEDIUM"
          ? 0.6
          : v.riskLevel === "HIGH"
            ? 0.3
            : 0.5,
  }));

  return c.json({
    count: vendors.length,
    vendors: vendorsWithTrust,
  });
});

export { vendorTrustRoutes };
