/**
 * Trust Battery Module - Agent Autonomy & Accuracy Tracking
 *
 * Manages the "Trust Battery" concept for gradual agent autonomy:
 * - Tracks per-vendor decision accuracy
 * - Calculates trust levels based on consecutive accurate decisions
 * - Provides autonomy thresholds based on trust level
 * - Supports feedback loop for learning from human corrections
 */

import { getDb, schema } from "../db";
import { eq, and, desc, sql } from "drizzle-orm";
import type { Env } from "../db";

// ============================================================================
// TRUST BATTERY LEVELS
// ============================================================================

export const TrustLevel = {
  PROBATION: 1 as const,    // 0-50 consecutive accurate: Review all
  STANDARD: 2 as const,     // 50-100 consecutive accurate: Review exceptions
  CORE: 3 as const,         // 100+ consecutive accurate: Auto-approve
} as const;

export type TrustLevelType = (typeof TrustLevel)[keyof typeof TrustLevel];

// Thresholds for trust level transitions
const THRESHOLD_PROBATION_TO_STANDARD = 50;
const THRESHOLD_STANDARD_TO_CORE = 100;

// Default auto-approve thresholds per level
export const TRUST_THRESHOLDS = {
  [TrustLevel.PROBATION]: 0,      // $0 - review everything
  [TrustLevel.STANDARD]: 500,     // $500 - approve under $500
  [TrustLevel.CORE]: 5000,        // $5000 - approve under $5000
};

// ============================================================================
// TYPES
// ============================================================================

export interface TrustBatteryState {
  vendorId: string;
  trustLevel: TrustLevelType;
  consecutiveAccurate: number;
  consecutiveErrors: number;
  totalDecisions: number;
  accurateDecisions: number;
  accuracyRate: number;
  autoApproveThreshold: number;
}

export interface DecisionOutcome {
  invoiceId: string;
  traceId: string;
  agentDecision: string; // AUTO_APPROVE, HITL, BLOCK, RE-SCHEDULE
  agentReasoning: string[];
  agentSignals: Array<{ type: string; severity: string; message: string }>;
  humanDecision?: string; // What human actually did
  humanReason?: string;   // Human's reason if different
  wasCorrect?: boolean;   // Did agent get it right?
}

// ============================================================================
// CORE FUNCTIONS
// ============================================================================

/**
 * Get or create trust battery for a vendor
 */
export async function getTrustBattery(env: Env, vendorId: string): Promise<TrustBatteryState> {
  const db = getDb(env);

  const [record] = await db
    .select()
    .from(schema.trustBattery)
    .where(eq(schema.trustBattery.vendorId, vendorId))
    .limit(1);

  if (!record) {
    // Create new trust battery for vendor
    const newId = crypto.randomUUID();
    await db.insert(schema.trustBattery).values({
      id: newId,
      vendorId,
      consecutiveAccurate: 0,
      consecutiveErrors: 0,
      totalDecisions: 0,
      accurateDecisions: 0,
      trustLevel: TrustLevel.PROBATION,
      autoApproveThreshold: TRUST_THRESHOLDS[TrustLevel.PROBATION],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    return {
      vendorId,
      trustLevel: TrustLevel.PROBATION,
      consecutiveAccurate: 0,
      consecutiveErrors: 0,
      totalDecisions: 0,
      accurateDecisions: 0,
      accuracyRate: 0,
      autoApproveThreshold: TRUST_THRESHOLDS[TrustLevel.PROBATION],
    };
  }

  return {
    vendorId: record.vendorId,
    trustLevel: (record.trustLevel ?? 1) as TrustLevelType,
    consecutiveAccurate: record.consecutiveAccurate ?? 0,
    consecutiveErrors: record.consecutiveErrors ?? 0,
    totalDecisions: record.totalDecisions ?? 0,
    accurateDecisions: record.accurateDecisions ?? 0,
    accuracyRate: (record.totalDecisions ?? 0) > 0
      ? (record.accurateDecisions ?? 0) / (record.totalDecisions ?? 1)
      : 0,
    autoApproveThreshold: record.autoApproveThreshold ?? TRUST_THRESHOLDS[(record.trustLevel ?? 1) as TrustLevelType],
  };
}

/**
 * Get global trust stats across all vendors
 */
export async function getGlobalTrustStats(env: Env): Promise<{
  totalVendors: number;
  avgAccuracy: number;
  levelDistribution: { probation: number; standard: number; core: number };
}> {
  const db = getDb(env);

  const [stats] = await db
    .select({
      total: sql<number>`count(distinct ${schema.trustBattery.vendorId})`,
      probation: sql<number>`sum(case when ${schema.trustBattery.trustLevel} = 1 then 1 else 0 end)`,
      standard: sql<number>`sum(case when ${schema.trustBattery.trustLevel} = 2 then 1 else 0 end)`,
      core: sql<number>`sum(case when ${schema.trustBattery.trustLevel} = 3 then 1 else 0 end)`,
    })
    .from(schema.trustBattery);

  // Calculate average accuracy from all records
  const allRecords = await db
    .select({
      total: schema.trustBattery.totalDecisions,
      accurate: schema.trustBattery.accurateDecisions,
    })
    .from(schema.trustBattery);

  let tDecisions = 0;
  let tAccurate = 0;
  for (const r of allRecords) {
    tDecisions += r.total ?? 0;
    tAccurate += r.accurate ?? 0;
  }
  const avgAccuracy = tDecisions > 0 ? tAccurate / tDecisions : 0;

  return {
    totalVendors: Number(stats.total) || 0,
    avgAccuracy,
    levelDistribution: {
      probation: Number(stats.probation) || 0,
      standard: Number(stats.standard) || 0,
      core: Number(stats.core) || 0,
    },
  };
}

/**
 * Record an agent decision
 */
export async function recordAgentDecision(
  env: Env,
  decision: DecisionOutcome
): Promise<string> {
  const db = getDb(env);
  const decisionId = crypto.randomUUID();

  await db.insert(schema.agentDecisions).values({
    id: decisionId,
    invoiceId: decision.invoiceId,
    traceId: decision.traceId,
    node: "CRITIC", // Critic node makes the final decision
    decision: decision.agentDecision,
    confidence: 0.85, // Default from Critic node
    reasoning: JSON.stringify(decision.agentReasoning),
    signals: JSON.stringify(decision.agentSignals),
    humanIntervention: !!decision.humanDecision,
    humanDecision: decision.humanDecision,
    humanReason: decision.humanReason,
    outcomeCorrect: decision.wasCorrect,
    createdAt: new Date().toISOString(),
  });

  return decisionId;
}

/**
 * Update trust battery with feedback/outcome
 */
export async function updateTrustBattery(
  env: Env,
  vendorId: string,
  outcome: "accurate" | "error"
): Promise<TrustBatteryState> {
  const db = getDb(env);

  const [record] = await db
    .select()
    .from(schema.trustBattery)
    .where(eq(schema.trustBattery.vendorId, vendorId))
    .limit(1);

  if (!record) {
    // Create new if doesn't exist
    return getTrustBattery(env, vendorId);
  }

  const isAccurate = outcome === "accurate";
  const currentAccurate = record.consecutiveAccurate ?? 0;
  const currentErrors = record.consecutiveErrors ?? 0;
  const currentTrust = record.trustLevel ?? 1;

  const newConsecutiveAccurate = isAccurate
    ? currentAccurate + 1
    : 0;
  const newConsecutiveErrors = isAccurate
    ? 0
    : currentErrors + 1;

  // Calculate new trust level
  let newTrustLevel = currentTrust as number;
  if (newConsecutiveAccurate >= THRESHOLD_STANDARD_TO_CORE && currentTrust !== 3) {
    newTrustLevel = 3; // Promote to CORE
  } else if (newConsecutiveAccurate >= THRESHOLD_PROBATION_TO_STANDARD && currentTrust === 1) {
    newTrustLevel = 2; // Promote to STANDARD
  }

  // Demote on too many errors (trust battery drains)
  if (newConsecutiveErrors >= 5 && currentTrust > 1) {
    newTrustLevel = currentTrust as number - 1;
  }

  // Calculate new thresholds
  const newThreshold = TRUST_THRESHOLDS[newTrustLevel as TrustLevelType];

  await db
    .update(schema.trustBattery)
    .set({
      consecutiveAccurate: newConsecutiveAccurate,
      consecutiveErrors: newConsecutiveErrors,
      totalDecisions: (record.totalDecisions ?? 0) + 1,
      accurateDecisions: (record.accurateDecisions ?? 0) + (isAccurate ? 1 : 0),
      trustLevel: newTrustLevel,
      autoApproveThreshold: newThreshold,
      lastDecisionAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.trustBattery.id, record.id));

  return {
    vendorId,
    trustLevel: newTrustLevel as TrustLevelType,
    consecutiveAccurate: newConsecutiveAccurate,
    consecutiveErrors: newConsecutiveErrors,
    totalDecisions: (record.totalDecisions ?? 0) + 1,
    accurateDecisions: (record.accurateDecisions ?? 0) + (isAccurate ? 1 : 0),
    accuracyRate: ((record.accurateDecisions ?? 0) + (isAccurate ? 1 : 0)) / ((record.totalDecisions ?? 0) + 1),
    autoApproveThreshold: newThreshold,
  };
}

/**
 * Get auto-approve threshold for a vendor based on trust level and amount
 */
export async function canAutoApprove(
  env: Env,
  vendorId: string,
  invoiceAmount: number
): Promise<{
  canAutoApprove: boolean;
  trustLevel: TrustLevelType;
  threshold: number;
  reason: string;
}> {
  const trust = await getTrustBattery(env, vendorId);

  if (invoiceAmount > trust.autoApproveThreshold) {
    return {
      canAutoApprove: false,
      trustLevel: trust.trustLevel,
      threshold: trust.autoApproveThreshold,
      reason: `Amount $${invoiceAmount} exceeds threshold $${trust.autoApproveThreshold}`,
    };
  }

  if (trust.trustLevel === TrustLevel.PROBATION) {
    return {
      canAutoApprove: false,
      trustLevel: trust.trustLevel,
      threshold: trust.autoApproveThreshold,
      reason: "Trust Level 1 (Probation): All decisions require review",
    };
  }

  return {
    canAutoApprove: true,
    trustLevel: trust.trustLevel,
    threshold: trust.autoApproveThreshold,
    reason: `Trust Level ${trust.trustLevel}: Auto-approved within threshold`,
  };
}

/**
 * Mark a decision outcome (for learning loop)
 */
export async function recordDecisionOutcome(
  env: Env,
  invoiceId: string,
  traceId: string,
  humanDecision: string,
  humanReason?: string
): Promise<void> {
  const db = getDb(env);

  // Update the agent decision record
  const [decision] = await db
    .select()
    .from(schema.agentDecisions)
    .where(and(
      eq(schema.agentDecisions.invoiceId, invoiceId),
      eq(schema.agentDecisions.traceId, traceId)
    ))
    .limit(1);

  if (decision) {
    const agentDecision = decision.decision;
    const wasCorrect = agentDecision === humanDecision ||
      (agentDecision === "HITL_REQUIRED" && humanDecision === "approved") ||
      (agentDecision === "AUTO_APPROVE" && humanDecision === "approved");

    // Update decision record
    await db
      .update(schema.agentDecisions)
      .set({
        humanIntervention: true,
        humanDecision,
        humanReason,
        outcomeVerified: true,
        outcomeCorrect: wasCorrect,
        verifiedAt: new Date().toISOString(),
        feedbackReceived: true,
      })
      .where(eq(schema.agentDecisions.id, decision.id));

    // Get vendor ID from invoice
    const [invoice] = await db
      .select({ vendorId: schema.invoices.vendorId })
      .from(schema.invoices)
      .where(eq(schema.invoices.id, invoiceId))
      .limit(1);

    if (invoice?.vendorId) {
      // Update trust battery
      await updateTrustBattery(
        env,
        invoice.vendorId,
        wasCorrect ? "accurate" : "error"
      );
    }
  }
}

/**
 * Get calibration report (for Shadow Mode)
 */
export async function getCalibrationReport(env: Env): Promise<{
  totalDecisions: number;
  verifiedDecisions: number;
  accuracyRate: number;
  levelDistribution: { probation: number; standard: number; core: number };
  recentAccuracy: number; // Last 50 decisions
  recommendations: string[];
}> {
  const db = getDb(env);

  // Get overall stats
  const [stats] = await db
    .select({
      total: sql<number>`count(*)`,
      verified: sql<number>`sum(case when ${schema.agentDecisions.outcomeVerified} = 1 then 1 else 0 end)`,
      correct: sql<number>`sum(case when ${schema.agentDecisions.outcomeCorrect} = 1 then 1 else 0 end)`,
      probation: sql<number>`sum(case when ${schema.agentDecisions.humanIntervention} = 0 then 1 else 0 end)`,
    })
    .from(schema.agentDecisions);

  // Get recent accuracy (last 50 verified decisions)
  const recentDecisions = await db
    .select({ outcomeCorrect: schema.agentDecisions.outcomeCorrect })
    .from(schema.agentDecisions)
    .where(eq(schema.agentDecisions.outcomeVerified, true))
    .orderBy(desc(schema.agentDecisions.createdAt))
    .limit(50);

  const recentCorrect = recentDecisions.filter(d => d.outcomeCorrect).length;
  const recentAccuracy = recentDecisions.length > 0 ? recentCorrect / recentDecisions.length : 0;

  // Get level distribution
  const globalStats = await getGlobalTrustStats(env);

  const recommendations: string[] = [];
  if (recentAccuracy >= 0.95) {
    recommendations.push("Agent accuracy exceeds 95%. Consider promoting to higher trust levels.");
  }
  if (recentAccuracy < 0.8) {
    recommendations.push("Agent accuracy below 80%. Review recent errors and adjust thresholds.");
  }
  if (globalStats.levelDistribution.core === 0) {
    recommendations.push("No vendors at Core trust level. Build accuracy to unlock full autonomy.");
  }

  return {
    totalDecisions: Number(stats.total) || 0,
    verifiedDecisions: Number(stats.verified) || 0,
    accuracyRate: Number(stats.total) > 0
      ? Number(stats.correct) / Number(stats.total)
      : 0,
    levelDistribution: globalStats.levelDistribution,
    recentAccuracy,
    recommendations,
  };
}

/**
 * Reset trust battery for a vendor (for testing or manual override)
 */
export async function resetTrustBattery(
  env: Env,
  vendorId: string,
  newLevel: TrustLevelType = TrustLevel.PROBATION
): Promise<void> {
  const db = getDb(env);

  await db
    .update(schema.trustBattery)
    .set({
      consecutiveAccurate: 0,
      consecutiveErrors: 0,
      totalDecisions: 0,
      accurateDecisions: 0,
      trustLevel: newLevel,
      autoApproveThreshold: TRUST_THRESHOLDS[newLevel],
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.trustBattery.vendorId, vendorId));
}

/**
 * Configure strategic settings
 */
export async function getStrategicConfig(env: Env): Promise<{
  strategyMode: string;
  payrollDate: string | null;
  payrollAmount: number;
  safetyBuffer: number;
  autoApproveThreshold: number;
  hitlThreshold: number;
}> {
  const db = getDb(env);

  const [config] = await db
    .select()
    .from(schema.strategicConfig)
    .where(eq(schema.strategicConfig.id, "default"))
    .limit(1);

  if (!config) {
    // Create default config
    const newId = crypto.randomUUID();
    await db.insert(schema.strategicConfig).values({
      id: newId,
      strategyMode: "OPTIMIZE",
      payrollDate: "15",
      payrollAmount: 15000,
      safetyBuffer: 10000,
      autoApproveThreshold: 500,
      hitlThreshold: 0.6,
      createdAt: new Date().toISOString(),
    });

    return {
      strategyMode: "OPTIMIZE",
      payrollDate: "15",
      payrollAmount: 15000,
      safetyBuffer: 10000,
      autoApproveThreshold: 500,
      hitlThreshold: 0.6,
    };
  }

  return {
    strategyMode: config.strategyMode ?? "OPTIMIZE",
    payrollDate: config.payrollDate ?? "15",
    payrollAmount: config.payrollAmount ?? 15000,
    safetyBuffer: config.safetyBuffer ?? 10000,
    autoApproveThreshold: config.autoApproveThreshold ?? 500,
    hitlThreshold: config.hitlThreshold ?? 0.6,
  };
}

/**
 * Update strategic settings
 */
export async function updateStrategicConfig(
  env: Env,
  updates: Partial<{
    strategyMode: string;
    payrollDate: string;
    payrollAmount: number;
    safetyBuffer: number;
    autoApproveThreshold: number;
    hitlThreshold: number;
  }>
): Promise<void> {
  const db = getDb(env);

  await db
    .update(schema.strategicConfig)
    .set({
      ...updates,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.strategicConfig.id, "default"));
}
