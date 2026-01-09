import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  runFraudDetection,
  getRiskIndicators,
  resolveRiskIndicator,
  type RiskAssessmentResult,
} from "../lib/fraud-detection";
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

export { riskRoutes };
