/**
 * Trust Battery & Strategic Config Routes
 *
 * Manages:
 * - Trust levels per vendor
 * - Agent accuracy tracking
 * - Strategic configuration (SURVIVAL/GROWTH/OPTIMIZE)
 * - Calibration reports
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  getTrustBattery,
  getGlobalTrustStats,
  updateTrustBattery,
  recordAgentDecision,
  recordDecisionOutcome,
  canAutoApprove,
  getCalibrationReport,
  resetTrustBattery,
  getStrategicConfig,
  updateStrategicConfig,
  TrustLevel,
  type TrustBatteryState,
} from "../lib/trust-battery";
import { eq, desc } from "drizzle-orm";
import type { Env } from "../db";

const trustBatteryRoutes = new Hono<{ Bindings: Env }>();

/**
 * Get trust battery for a vendor
 * GET /api/v1/trust-battery/:vendorId
 */
trustBatteryRoutes.get("/:vendorId", async (c) => {
  const env = c.env;
  const vendorId = c.req.param("vendorId");

  const trust = await getTrustBattery(env, vendorId);

  return c.json({
    success: true,
    data: {
      vendorId: trust.vendorId,
      trustLevel: trust.trustLevel,
      levelName: trust.trustLevel === 1 ? "Probation" : trust.trustLevel === 2 ? "Standard" : "Core",
      consecutiveAccurate: trust.consecutiveAccurate,
      consecutiveErrors: trust.consecutiveErrors,
      accuracyRate: Math.round(trust.accuracyRate * 100) / 100,
      autoApproveThreshold: trust.autoApproveThreshold,
    },
  });
});

/**
 * Get global trust statistics
 * GET /api/v1/trust-battery/stats
 */
trustBatteryRoutes.get("/stats/global", async (c) => {
  const env = c.env;

  const stats = await getGlobalTrustStats(env);
  const calibration = await getCalibrationReport(env);

  return c.json({
    success: true,
    data: {
      ...stats,
      calibration,
    },
  });
});

/**
 * Check if invoice can be auto-approved
 * POST /api/v1/trust-battery/check-approve
 */
trustBatteryRoutes.post("/check-approve", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    vendorId: string;
    amount: number;
  }>();

  if (!body.vendorId || body.amount === undefined) {
    return c.json({ error: "vendorId and amount required" }, 400);
  }

  const result = await canAutoApprove(env, body.vendorId, body.amount);

  return c.json({
    success: true,
    data: result,
  });
});

/**
 * Record agent decision
 * POST /api/v1/trust-battery/record-decision
 */
trustBatteryRoutes.post("/record-decision", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    invoiceId: string;
    traceId: string;
    agentDecision: string;
    agentReasoning: string[];
    agentSignals: Array<{ type: string; severity: string; message: string }>;
  }>();

  if (!body.invoiceId || !body.traceId || !body.agentDecision) {
    return c.json({ error: "invoiceId, traceId, and agentDecision required" }, 400);
  }

  const decisionId = await recordAgentDecision(env, {
    invoiceId: body.invoiceId,
    traceId: body.traceId,
    agentDecision: body.agentDecision,
    agentReasoning: body.agentReasoning,
    agentSignals: body.agentSignals,
  });

  return c.json({
    success: true,
    data: { decisionId },
  });
});

/**
 * Record human feedback/outcome (for learning loop)
 * POST /api/v1/trust-battery/feedback
 */
trustBatteryRoutes.post("/feedback", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    invoiceId: string;
    traceId: string;
    humanDecision: "approved" | "rejected" | "delayed";
    humanReason?: string;
  }>();

  if (!body.invoiceId || !body.traceId || !body.humanDecision) {
    return c.json({ error: "invoiceId, traceId, and humanDecision required" }, 400);
  }

  await recordDecisionOutcome(env, body.invoiceId, body.traceId, body.humanDecision, body.humanReason);

  return c.json({
    success: true,
    message: "Feedback recorded and trust battery updated",
  });
});

/**
 * Get calibration report (Shadow Mode output)
 * GET /api/v1/trust-battery/calibration
 */
trustBatteryRoutes.get("/calibration", async (c) => {
  const env = c.env;

  const report = await getCalibrationReport(env);

  return c.json({
    success: true,
    data: report,
  });
});

/**
 * Reset trust battery for a vendor (Admin only)
 * POST /api/v1/trust-battery/:vendorId/reset
 */
trustBatteryRoutes.post("/:vendorId/reset", async (c) => {
  const env = c.env;
  const vendorId = c.req.param("vendorId");
  const body = await c.req.json<{
    newLevel?: 1 | 2 | 3;
  }>();

  await resetTrustBattery(env, vendorId, body.newLevel);

  return c.json({
    success: true,
    message: `Trust battery reset for vendor ${vendorId}`,
  });
});

/**
 * Get all vendors with trust levels
 * GET /api/v1/trust-battery/list
 */
trustBatteryRoutes.get("/list", async (c) => {
  const env = c.env;
  const db = getDb(env);

  const vendors = await db
    .select({
      vendorId: schema.trustBattery.vendorId,
      trustLevel: schema.trustBattery.trustLevel,
      consecutiveAccurate: schema.trustBattery.consecutiveAccurate,
      totalDecisions: schema.trustBattery.totalDecisions,
      accurateDecisions: schema.trustBattery.accurateDecisions,
    })
    .from(schema.trustBattery)
    .orderBy(desc(schema.trustBattery.consecutiveAccurate));

  // Calculate accuracy rates on the fly
  const vendorsWithRate = vendors.map(v => ({
    vendorId: v.vendorId,
    trustLevel: v.trustLevel,
    consecutiveAccurate: v.consecutiveAccurate,
    accuracyRate: (v.totalDecisions ?? 0) > 0
      ? (v.accurateDecisions ?? 0) / (v.totalDecisions ?? 1)
      : 0,
  }));

  return c.json({
    success: true,
    count: vendorsWithRate.length,
    vendors: vendorsWithRate,
  });
});

// ============================================================================
// STRATEGIC CONFIG ROUTES
// ============================================================================

const strategyRoutes = new Hono<{ Bindings: Env }>();

/**
 * Get strategic configuration
 * GET /api/v1/strategy
 */
strategyRoutes.get("/", async (c) => {
  const env = c.env;

  const config = await getStrategicConfig(env);

  return c.json({
    success: true,
    data: config,
  });
});

/**
 * Update strategic configuration
 * POST /api/v1/strategy
 */
strategyRoutes.post("/", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    strategyMode?: "SURVIVAL" | "GROWTH" | "OPTIMIZE";
    payrollDate?: string;
    payrollAmount?: number;
    safetyBuffer?: number;
    autoApproveThreshold?: number;
    hitlThreshold?: number;
  }>();

  await updateStrategicConfig(env, body);

  return c.json({
    success: true,
    message: "Strategic configuration updated",
  });
});

/**
 * Get budget categories
 * GET /api/v1/strategy/budgets
 */
strategyRoutes.get("/budgets", async (c) => {
  const env = c.env;
  const db = getDb(env);

  const budgets = await db
    .select()
    .from(schema.budgetCategories)
    .where(eq(schema.budgetCategories.isActive, true));

  return c.json({
    success: true,
    count: budgets.length,
    budgets,
  });
});

/**
 * Create/update budget category
 * POST /api/v1/strategy/budgets
 */
strategyRoutes.post("/budgets", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    category: string;
    monthlyLimit: number;
    softCapAlert?: boolean;
  }>();

  const db = getDb(env);
  const id = crypto.randomUUID();

  await db.insert(schema.budgetCategories).values({
    id,
    category: body.category,
    monthlyLimit: body.monthlyLimit,
    softCapAlert: body.softCapAlert ?? true,
    createdAt: new Date().toISOString(),
  });

  return c.json({
    success: true,
    data: { id, ...body },
  });
});

export { trustBatteryRoutes, strategyRoutes };
