import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  runFraudDetection,
  getRiskIndicators,
  resolveRiskIndicator,
  type RiskAssessmentResult,
} from "../lib/fraud-detection";
import {
  calculateRisk,
  routeAction,
  assessInvoiceRisk,
  WEIGHT_AMOUNT,
  WEIGHT_DUPLICATE,
  WEIGHT_VENDOR_TRUST,
  WEIGHT_RUNWAY,
  WEIGHT_NEW_VENDOR,
} from "../lib/risk-scoring";
import { updateVendorTrust, updateRiskWeights } from "../lib/vendor-trust";
import { AuditTracer, getInvoiceAuditTrail } from "../lib/audit-tracer";
import { eq, sql, desc, and, gte } from "drizzle-orm";
import type { Env } from "../db";

const riskRoutes = new Hono<{ Bindings: Env }>();

/**
 * Run fraud detection for an invoice
 * POST /api/v1/risk/:invoiceId/analyze
 */
riskRoutes.post("/:invoiceId/analyze", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const result = await runFraudDetection(env, invoiceId);

  if (!result) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  return c.json({
    success: true,
    data: result,
  });
});

/**
 * Get risk assessment for an invoice
 * GET /api/v1/risk/:invoiceId
 */
riskRoutes.get("/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  const indicators = await getRiskIndicators(env, invoiceId);

  return c.json({
    invoiceId,
    riskScore: invoice.riskScore,
    riskLevel: invoice.riskLevel,
    indicators,
  });
});

/**
 * Get all risk indicators for an invoice
 * GET /api/v1/risk/:invoiceId/indicators
 */
riskRoutes.get("/:invoiceId/indicators", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const indicators = await getRiskIndicators(env, invoiceId);

  return c.json({
    invoiceId,
    indicators,
    count: indicators.length,
  });
});

/**
 * Resolve a risk indicator
 * POST /api/v1/risk/indicators/:indicatorId/resolve
 */
riskRoutes.post("/indicators/:indicatorId/resolve", async (c) => {
  const env = c.env;
  const indicatorId = c.req.param("indicatorId");
  const body = await c.req.json();

  if (!body.resolvedBy) {
    return c.json({ error: "resolvedBy is required" }, 400);
  }

  const success = await resolveRiskIndicator(env, indicatorId, body.resolvedBy);

  if (!success) {
    return c.json({ error: "Indicator not found" }, 404);
  }

  return c.json({ success: true, message: "Indicator resolved" });
});

/**
 * Get high-risk invoices requiring attention
 * GET /api/v1/risk/high-risk
 */
riskRoutes.get("/list/high-risk", async (c) => {
  const db = getDb(c.env);
  const thresholdValue = parseInt(c.req.query("threshold") || "50");

  const invoices = await db
    .select({
      id: schema.invoices.id,
      vendorName: schema.invoices.vendorName,
      invoiceNumber: schema.invoices.invoiceNumber,
      totalAmount: schema.invoices.totalAmount,
      currency: schema.invoices.currency,
      status: schema.invoices.status,
      riskScore: schema.invoices.riskScore,
      riskLevel: schema.invoices.riskLevel,
      dueDate: schema.invoices.dueDate,
      createdAt: schema.invoices.createdAt,
    })
    .from(schema.invoices)
    .where(sql`${schema.invoices.riskScore} >= ${thresholdValue}`)
    .orderBy(sql`${schema.invoices.riskScore} DESC`)
    .limit(100);

  return c.json({
    threshold: thresholdValue,
    count: invoices.length,
    invoices,
  });
});

/**
 * Get risk statistics
 * GET /api/v1/risk/stats
 */
riskRoutes.get("/stats/overview", async (c) => {
  const db = getDb(c.env);

  const byLevel = await db
    .select({
      level: schema.invoices.riskLevel,
      count: sql<number>`count(*)`,
      totalAmount: sql<number>`coalesce(sum(${schema.invoices.totalAmount}), 0)`,
    })
    .from(schema.invoices)
    .groupBy(schema.invoices.riskLevel);

  const [avgRiskScore] = await db
    .select({
      avg: sql<number>`coalesce(avg(${schema.invoices.riskScore}), 0)`,
    })
    .from(schema.invoices);

  const [criticalCount] = await db
    .select({
      count: sql<number>`count(case when ${schema.invoices.riskLevel} = 'CRITICAL' then 1 end)`,
    })
    .from(schema.invoices);

  return c.json({
    byRiskLevel: byLevel,
    averageRiskScore: avgRiskScore.avg,
    criticalCount: criticalCount.count,
  });
});

/**
 * Calculate risk using PRD formula
 * POST /api/v1/risk/calculate
 *
 * PRD Formula: 0.30*amount_deviation + 0.25*duplicate_similarity + 0.20*(1-vendor_trust) + 0.15*runway_pressure + 0.10*is_new_vendor
 */
riskRoutes.post("/calculate", async (c) => {
  const body = await c.req.json<{
    amountDeviation: number;
    duplicateSimilarity: number;
    vendorTrust: number;
    runwayPressure: number;
    isNewVendor: number;
  }>();

  const { amountDeviation, duplicateSimilarity, vendorTrust, runwayPressure, isNewVendor } = body;

  // Validate inputs
  if (
    amountDeviation === undefined ||
    duplicateSimilarity === undefined ||
    vendorTrust === undefined ||
    runwayPressure === undefined ||
    isNewVendor === undefined
  ) {
    return c.json(
      {
        error: "Missing required fields",
        required: ["amountDeviation", "duplicateSimilarity", "vendorTrust", "runwayPressure", "isNewVendor"],
      },
      400
    );
  }

  const assessment = calculateRisk({
    amountDeviation,
    duplicateSimilarity,
    vendorTrust,
    runwayPressure,
    isNewVendor,
  });

  const action = routeAction(assessment.score, assessment.confidence);

  return c.json({
    success: true,
    data: {
      ...assessment,
      action,
      formula: {
        weights: {
          amountDeviation: WEIGHT_AMOUNT,
          duplicateSimilarity: WEIGHT_DUPLICATE,
          vendorTrust: WEIGHT_VENDOR_TRUST,
          runwayPressure: WEIGHT_RUNWAY,
          isNewVendor: WEIGHT_NEW_VENDOR,
        },
        formula: "0.30*amount + 0.25*duplicate + 0.20*(1-trust) + 0.15*runway + 0.10*new_vendor",
      },
    },
  });
});

/**
 * Get PRD risk weights
 * GET /api/v1/risk/weights
 */
riskRoutes.get("/weights", async (c) => {
  return c.json({
    weights: {
      amountDeviation: WEIGHT_AMOUNT,
      duplicateSimilarity: WEIGHT_DUPLICATE,
      vendorTrust: WEIGHT_VENDOR_TRUST,
      runwayPressure: WEIGHT_RUNWAY,
      isNewVendor: WEIGHT_NEW_VENDOR,
    },
    thresholds: {
      autoApprove: 0.3,
      hitl: 0.6,
      escalate: 0.6,
      confidenceRequired: 0.8,
    },
  });
});

/**
 * Full invoice risk assessment using PRD formula
 * POST /api/v1/risk/:invoiceId/assess
 */
riskRoutes.post("/:invoiceId/assess", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  const result = await assessInvoiceRisk(env, invoiceId);

  if (!result) {
    return c.json({ error: "Failed to assess risk" }, 500);
  }

  // Log audit event
  const tracer = new AuditTracer(env);
  const action = routeAction(result.score, result.confidence);
  await tracer.logRiskAssessment(
    invoiceId,
    result.score,
    result.level,
    result.signals,
    action
  );

  return c.json({
    success: true,
    data: {
      ...result,
      action,
    },
  });
});

/**
 * Submit feedback for learning loop
 * POST /api/v1/risk/feedback
 *
 * PRD Section E: Learn from approvals/rejections
 */
riskRoutes.post("/feedback", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    vendorId: string;
    invoiceId: string;
    originalRiskScore: number;
    originalConfidence: number;
    decision: "approved" | "rejected" | "delayed";
    isDuplicate?: boolean;
  }>();

  const { vendorId, invoiceId, originalRiskScore, originalConfidence, decision, isDuplicate } = body;

  if (!vendorId || !invoiceId || originalRiskScore === undefined || !decision) {
    return c.json({ error: "Missing required fields" }, 400);
  }

  // Update vendor trust
  const trustResult = await updateVendorTrust(env, vendorId, decision, originalRiskScore, false);

  // Log audit event
  const tracer = new AuditTracer(env);
  await tracer.logFeedbackReceived(invoiceId, vendorId, decision, originalRiskScore);

  return c.json({
    success: true,
    data: {
      vendorTrustAdjustment: trustResult.adjustment,
      newTrustScore: trustResult.newTrustScore,
      decision,
      originalRiskScore,
    },
  });
});

/**
 * Get audit trail for an invoice
 * GET /api/v1/risk/:invoiceId/audit
 */
riskRoutes.get("/:invoiceId/audit", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const auditTrail = await getInvoiceAuditTrail(env, invoiceId);

  return c.json({
    invoiceId,
    ...auditTrail,
  });
});

export { riskRoutes };
