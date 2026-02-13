/**
 * Vendor Trust Scoring & Learning Loop Module
 *
 * Implements the learning loop from PRD Section E:
 * - Learn from approvals/rejections
 * - Learn vendor behavior
 * - Improve confidence thresholds
 * - Reduce HITL over time
 *
 * Updates vendor trust scores based on feedback
 */

import { getDb, schema } from "../db";
import { eq, sql, and, desc } from "drizzle-orm";
import type { Env } from "../db";

/**
 * Approval decision types
 */
export type ApprovalDecision = "approved" | "rejected" | "delayed";

/**
 * Feedback context for learning
 */
export interface FeedbackContext {
  vendorId: string;
  invoiceId: string;
  originalRiskScore: number;
  originalConfidence: number;
  approvalDecision: ApprovalDecision;
  actualAmount: number;
  isDuplicate?: boolean;
}

/**
 * Weight adjustment recommendation
 */
export interface WeightAdjustment {
  adjustmentMade: boolean;
  newWeights: {
    amountDeviation: number;
    duplicateSimilarity: number;
    vendorTrust: number;
    runwayPressure: number;
    newVendor: number;
  };
  explanation: string;
}

// Default weights from PRD
const DEFAULT_WEIGHTS = {
  amountDeviation: 0.30,
  duplicateSimilarity: 0.25,
  vendorTrust: 0.20,
  runwayPressure: 0.15,
  newVendor: 0.10,
};

/**
 * Update vendor trust based on approval decision
 * PRD Section E: Learn from approvals/rejections
 */
export async function updateVendorTrust(
  env: Env,
  vendorId: string,
  decision: ApprovalDecision,
  originalRiskScore: number,
  isNewVendor: boolean
): Promise<{ adjustment: number; newTrustScore: number }> {
  const db = getDb(env);

  // Get current vendor
  const [vendor] = await db
    .select()
    .from(schema.vendors)
    .where(eq(schema.vendors.id, vendorId))
    .limit(1);

  if (!vendor) {
    return { adjustment: 0, newTrustScore: 0.5 };
  }

  // Calculate trust adjustment based on decision and risk
  let adjustment = 0;

  switch (decision) {
    case "approved":
      // Approved low-risk invoices increase trust
      if (originalRiskScore < 0.3) {
        adjustment = 0.03;
      } else if (originalRiskScore > 0.6) {
        // Approved high-risk invoices decrease trust (false positive)
        adjustment = -0.05;
      } else {
        adjustment = 0.01;
      }
      break;

    case "rejected":
      // Rejected invoices decrease trust
      adjustment = -0.05;
      break;

    case "delayed":
      // Delayed payments slightly decrease trust
      adjustment = -0.02;
      break;
  }

  // New vendors get a boost when first invoice is approved
  if (isNewVendor && decision === "approved" && originalRiskScore < 0.4) {
    adjustment += 0.10;
  }

  // Calculate new trust score (clamped 0-1)
  const currentTrust = vendor.riskLevel
    ? vendor.riskLevel === "LOW"
      ? 0.9
      : vendor.riskLevel === "MEDIUM"
        ? 0.6
        : vendor.riskLevel === "HIGH"
          ? 0.3
          : 0.5
    : 0.5;

  const newTrust = Math.max(0.1, Math.min(0.99, currentTrust + adjustment));

  // Update vendor risk level based on new trust
  const newRiskLevel = newTrust > 0.7 ? "LOW" : newTrust > 0.4 ? "MEDIUM" : "HIGH";

  await db
    .update(schema.vendors)
    .set({
      riskLevel: newRiskLevel,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.vendors.id, vendorId));

  return { adjustment, newTrustScore: newTrust };
}

/**
 * Update risk weights based on accumulated feedback
 * PRD Section E: Improve confidence thresholds
 */
export async function updateRiskWeights(
  env: Env,
  feedbackContexts: FeedbackContext[]
): Promise<WeightAdjustment> {
  // Need minimum samples for meaningful adjustment
  const MIN_SAMPLES = 10;

  if (feedbackContexts.length < MIN_SAMPLES) {
    return {
      adjustmentMade: false,
      newWeights: DEFAULT_WEIGHTS,
      explanation: `Not enough feedback samples (${feedbackContexts.length}/${MIN_SAMPLES})`,
    };
  }

  // Analyze feedback patterns
  let falsePositives = 0;
  let falseNegatives = 0;
  let missedDuplicates = 0;
  let correctApprovals = 0;

  for (const ctx of feedbackContexts) {
    if (ctx.approvalDecision === "approved" && ctx.originalRiskScore > 0.5) {
      // High risk but approved - possible false positive
      falsePositives++;
    }

    if (ctx.approvalDecision === "rejected" && ctx.originalRiskScore < 0.3) {
      // Low risk but rejected - possible false negative
      falseNegatives++;
    }

    if (ctx.isDuplicate && ctx.approvalDecision === "approved") {
      // Missed duplicate detection
      missedDuplicates++;
    }

    if (
      ctx.approvalDecision === "approved" &&
      ctx.originalRiskScore < 0.4 &&
      !ctx.isDuplicate
    ) {
      // Correct approval
      correctApprovals++;
    }
  }

  // Calculate weight adjustments
  const adjustmentRate = 0.02; // 2% adjustment per pattern
  let adjustmentMade = false;

  const newWeights = { ...DEFAULT_WEIGHTS };

  // If many false positives, reduce amount weight
  if (falsePositives > feedbackContexts.length * 0.2) {
    newWeights.amountDeviation = Math.max(0.15, newWeights.amountDeviation - adjustmentRate);
    adjustmentMade = true;
  }

  // If many missed duplicates, increase duplicate weight
  if (missedDuplicates > 0) {
    newWeights.duplicateSimilarity = Math.min(0.35, newWeights.duplicateSimilarity + adjustmentRate);
    adjustmentMade = true;
  }

  // If many false negatives, increase vendor trust weight
  if (falseNegatives > feedbackContexts.length * 0.1) {
    newWeights.vendorTrust = Math.min(0.30, newWeights.vendorTrust + adjustmentRate);
    adjustmentMade = true;
  }

  // Normalize weights to sum to 1
  const total = Object.values(newWeights).reduce((a, b) => a + b, 0);
  Object.keys(newWeights).forEach((key) => {
    newWeights[key as keyof typeof newWeights] =
      Math.round((newWeights[key as keyof typeof newWeights] / total) * 100) / 100;
  });

  let explanation = "";
  if (adjustmentMade) {
    explanation = `Weights adjusted based on ${feedbackContexts.length} feedback samples`;
    if (falsePositives > 0) explanation += `, ${falsePositives} false positives detected`;
    if (missedDuplicates > 0) explanation += `, ${missedDuplicates} missed duplicates`;
  } else {
    explanation = "No significant patterns detected in feedback";
  }

  return {
    adjustmentMade,
    newWeights,
    explanation,
  };
}

/**
 * Record feedback for learning
 */
export async function recordFeedback(
  env: Env,
  context: FeedbackContext
): Promise<void> {
  const db = getDb(env);

  // Create feedback record (could be extended to a separate table)
  await db.insert(schema.auditLogs).values({
    id: crypto.randomUUID(),
    action: "FEEDBACK_RECORDED",
    entityType: "invoice",
    entityId: context.invoiceId,
    performedBy: "system",
    performedAt: new Date().toISOString(),
    changes: JSON.stringify({
      decision: context.approvalDecision,
      originalRiskScore: context.originalRiskScore,
      originalConfidence: context.originalConfidence,
      isDuplicate: context.isDuplicate,
    }),
    metadata: JSON.stringify({ vendorId: context.vendorId }),
  });

  // Update vendor trust
  await updateVendorTrust(
    env,
    context.vendorId,
    context.approvalDecision,
    context.originalRiskScore,
    false // Assume vendor exists
  );
}

/**
 * Get vendor trust history for analysis
 */
export async function getVendorTrustHistory(
  env: Env,
  vendorId: string
): Promise<{
  currentTrustScore: number;
  trend: "improving" | "stable" | "declining";
  totalFeedback: number;
  approvalRate: number;
}> {
  const db = getDb(env);

  // Get vendor
  const [vendor] = await db
    .select()
    .from(schema.vendors)
    .where(eq(schema.vendors.id, vendorId))
    .limit(1);

  if (!vendor) {
    return {
      currentTrustScore: 0.5,
      trend: "stable",
      totalFeedback: 0,
      approvalRate: 0,
    };
  }

  // Get recent feedback/approvals
  const recentApprovals = await db
    .select({
      count: sql<number>`count(*)`,
      approved: sql<number>`sum(case when ${schema.approvals.status} = 'APPROVED' then 1 else 0 end)`,
    })
    .from(schema.approvals)
    .where(eq(schema.approvals.id, vendorId))
    .limit(1);

  const totalFeedback = vendor.totalInvoices || 0;
  const approvedCount = Number(recentApprovals[0]?.approved || 0);
  const approvalRate = totalFeedback > 0 ? approvedCount / totalFeedback : 0;

  // Determine trend based on trust level
  const currentTrustScore = vendor.riskLevel
    ? vendor.riskLevel === "LOW"
      ? 0.9
      : vendor.riskLevel === "MEDIUM"
        ? 0.6
        : vendor.riskLevel === "HIGH"
          ? 0.3
          : 0.5
    : 0.5;

  return {
    currentTrustScore,
    trend: "stable", // Would need historical data for real trend
    totalFeedback,
    approvalRate,
  };
}

/**
 * Calculate optimal approval threshold based on historical data
 */
export async function calculateOptimalThreshold(
  env: Env
): Promise<{
  autoApproveThreshold: number;
  hitlThreshold: number;
  confidence: number;
}> {
  // Default thresholds from PRD
  return {
    autoApproveThreshold: 0.3,
    hitlThreshold: 0.6,
    confidence: 0.8,
  };
}
