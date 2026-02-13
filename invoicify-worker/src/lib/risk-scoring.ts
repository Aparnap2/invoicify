/**
 * PRD-Aligned Risk Scoring Module
 *
 * Implements the deterministic risk formula from PRD:
 * risk_score =
 *   (0.30 * amount_deviation)
 * + (0.25 * duplicate_similarity)
 * + (0.20 * (1 - vendor_trust))
 * + (0.15 * runway_pressure)
 * + (0.10 * is_new_vendor)
 *
 * Reference: prd.md Section 3 (Risk Scoring Formula)
 */

import { getDb, schema } from "../db";
import { eq, sql, and, gte, desc } from "drizzle-orm";
import type { Env } from "../db";

// PRD Weight Constants
export const WEIGHT_AMOUNT = 0.30;
export const WEIGHT_DUPLICATE = 0.25;
export const WEIGHT_VENDOR_TRUST = 0.20;
export const WEIGHT_RUNWAY = 0.15;
export const WEIGHT_NEW_VENDOR = 0.10;

/**
 * Risk assessment inputs per PRD specification
 */
export interface RiskInputs {
  /** Vendor trust score (0-1, higher is better) */
  vendorTrust: number;
  /** Amount deviation from vendor average (0-1) */
  amountDeviation: number;
  /** Duplicate similarity score (0-1) */
  duplicateSimilarity: number;
  /** Runway pressure impact (0-1) */
  runwayPressure: number;
  /** Whether this is a new vendor (0 or 1) */
  isNewVendor: number;
}

/**
 * Risk assessment result
 */
export interface RiskAssessmentResult {
  /** Final risk score (0-1) */
  score: number;
  /** Confidence score (0-1) */
  confidence: number;
  /** Risk level per PRD thresholds */
  level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  /** Individual signals that contributed to the score */
  signals: string[];
  /** Breakdown of score components */
  breakdown: {
    amountDeviation: number;
    duplicateSimilarity: number;
    vendorTrust: number;
    runwayPressure: number;
    newVendor: number;
  };
  /** Human-readable explanation */
  explanation: string;
}

/**
 * Company context for risk assessment
 */
export interface CompanyContext {
  runwayDays: number;
  cashBalance: number;
  monthlyBurnRate: number;
  availableCredit: number;
}

/**
 * Calculate risk score using PRD formula
 *
 * Formula from prd.md Section 3.2:
 * risk_score =
 *   (0.30 * amount_deviation)
 * + (0.25 * duplicate_similarity)
 * + (0.20 * (1 - vendor_trust))
 * + (0.15 * runway_pressure)
 * + (0.10 * is_new_vendor)
 */
export function calculateRisk(inputs: RiskInputs): RiskAssessmentResult {
  const { vendorTrust, amountDeviation, duplicateSimilarity, runwayPressure, isNewVendor } = inputs;

  // Clamp values to 0-1 range
  const clamped = {
    vendorTrust: Math.max(0, Math.min(1, vendorTrust)),
    amountDeviation: Math.max(0, Math.min(1, amountDeviation)),
    duplicateSimilarity: Math.max(0, Math.min(1, duplicateSimilarity)),
    runwayPressure: Math.max(0, Math.min(1, runwayPressure)),
    isNewVendor: Math.max(0, Math.min(1, isNewVendor)),
  };

  // Calculate weighted risk score
  const amountRisk = WEIGHT_AMOUNT * clamped.amountDeviation;
  const duplicateRisk = WEIGHT_DUPLICATE * clamped.duplicateSimilarity;
  const vendorRisk = WEIGHT_VENDOR_TRUST * (1 - clamped.vendorTrust);
  const runwayRisk = WEIGHT_RUNWAY * clamped.runwayPressure;
  const newVendorRisk = WEIGHT_NEW_VENDOR * clamped.isNewVendor;

  const totalScore = amountRisk + duplicateRisk + vendorRisk + runwayRisk + newVendorRisk;

  // Generate signals
  const signals: string[] = [];
  if (amountRisk > 0.15) signals.push(`High amount deviation: ${(amountDeviation * 100).toFixed(1)}%`);
  if (duplicateSimilarity > 0.5) signals.push(`Potential duplicate detected: ${(duplicateSimilarity * 100).toFixed(1)}%`);
  if (vendorRisk > 0.1) signals.push(`Low vendor trust: ${(vendorTrust * 100).toFixed(1)}%`);
  if (runwayRisk > 0.05) signals.push(`Runway pressure: ${(runwayPressure * 100).toFixed(1)}%`);
  if (isNewVendor === 1) signals.push("New vendor - no history");

  // Calculate confidence based on information completeness
  const confidence = calculateConfidence(clamped);

  // Determine risk level per PRD thresholds
  const level = determineRiskLevel(totalScore, confidence);

  // Generate explanation
  const explanation = generateExplanation(totalScore, level, confidence, signals);

  return {
    score: Math.round(totalScore * 1000) / 1000,
    confidence: Math.round(confidence * 1000) / 1000,
    level,
    signals,
    breakdown: {
      amountDeviation: Math.round(amountRisk * 1000) / 1000,
      duplicateSimilarity: Math.round(duplicateRisk * 1000) / 1000,
      vendorTrust: Math.round(vendorRisk * 1000) / 1000,
      runwayPressure: Math.round(runwayRisk * 1000) / 1000,
      newVendor: Math.round(newVendorRisk * 1000) / 1000,
    },
    explanation,
  };
}

/**
 * Calculate confidence based on information completeness
 */
function calculateConfidence(clamped: Omit<RiskInputs, "isNewVendor">): number {
  // More information = higher confidence
  const factors = [
    clamped.vendorTrust > 0 ? 1 : 0.5,  // Have vendor history
    clamped.amountDeviation >= 0 ? 1 : 0, // Have amount data
    clamped.duplicateSimilarity >= 0 ? 1 : 0, // Checked for duplicates
    clamped.runwayPressure >= 0 ? 1 : 0,  // Have company context
  ];

  const totalWeight = factors.reduce((a, b) => a + b, 0);
  return totalWeight / factors.length;
}

/**
 * Determine risk level per PRD thresholds
 * PRD Section 2.3: Low (<0.3) → auto-approve, Medium (0.3-0.6) → HITL, High (>0.6) → escalate
 */
function determineRiskLevel(score: number, confidence: number): "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" {
  // Low confidence increases scrutiny
  const adjustedScore = confidence < 0.7 ? score + 0.05 : score;

  if (adjustedScore < 0.3) return "LOW";
  if (adjustedScore < 0.6) return "MEDIUM";
  if (adjustedScore < 0.8) return "HIGH";
  return "CRITICAL";
}

/**
 * Generate human-readable explanation
 */
function generateExplanation(
  score: number,
  level: string,
  confidence: number,
  signals: string[]
): string {
  const scorePercent = (score * 100).toFixed(1);
  const confPercent = (confidence * 100).toFixed(1);

  let explanation = `Risk Score: ${scorePercent}% (${level}) - `;

  if (level === "LOW") {
    explanation += "auto-approve";
  } else if (level === "MEDIUM") {
    explanation += "human review recommended";
  } else {
    explanation += "escalation recommended";
  }

  explanation += `\nConfidence: ${confPercent}%`;

  if (signals.length > 0) {
    explanation += `\nKey factors: ${signals.join(", ")}`;
  }

  return explanation;
}

/**
 * Route action based on risk and confidence per PRD Section 2.3
 * Returns: "auto_approve" | "hitl" | "escalate"
 */
export function routeAction(riskScore: number, confidence: number): "auto_approve" | "hitl" | "escalate" {
  if (riskScore < 0.3 && confidence > 0.8) {
    return "auto_approve";
  } else if (riskScore < 0.6) {
    return "hitl";
  } else {
    return "escalate";
  }
}

/**
 * Calculate amount deviation from vendor average
 */
export async function calculateAmountDeviation(
  env: Env,
  vendorId: string | null,
  invoiceAmount: number
): Promise<number> {
  if (!vendorId) return 0.5; // No vendor = medium deviation

  const db = getDb(env);

  const [result] = await db
    .select({
      avg: sql<number>`coalesce(avg(${schema.invoices.totalAmount}), 0)`,
      count: sql<number>`count(*)`,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.vendorId, vendorId));

  if (result.count === 0 || result.avg === 0) return 0.5; // No history = medium deviation

  const deviation = Math.abs(invoiceAmount - result.avg) / result.avg;
  return Math.min(1, deviation); // Clamp to 0-1
}

/**
 * Check for duplicate invoices
 */
export async function checkDuplicateInvoices(
  env: Env,
  vendorId: string | null,
  invoiceNumber: string,
  amount: number,
  excludeInvoiceId?: string
): Promise<{ isDuplicate: boolean; similarity: number; duplicateOfId: string | null }> {
  const db = getDb(env);

  // Check for exact duplicate by vendor + invoice number
  if (vendorId) {
    const [existing] = await db
      .select({ id: schema.invoices.id })
      .from(schema.invoices)
      .where(
        and(
          eq(schema.invoices.vendorId, vendorId),
          eq(schema.invoices.invoiceNumber, invoiceNumber),
          excludeInvoiceId ? sql`${schema.invoices.id} != ${excludeInvoiceId}` : sql`1=1`
        )
      )
      .limit(1);

    if (existing) {
      return { isDuplicate: true, similarity: 1.0, duplicateOfId: existing.id };
    }
  }

  // Check for amount-based similarity (same amount within recent timeframe)
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const [similar] = await db
    .select({
      id: schema.invoices.id,
      similarity: sql<number>`1 - abs(${schema.invoices.totalAmount} - ${amount}) / ${Math.max(amount, 100)}`,
    })
    .from(schema.invoices)
    .where(
      and(
        vendorId ? eq(schema.invoices.vendorId, vendorId) : sql`1=1`,
        sql`${schema.invoices.createdAt} > '${thirtyDaysAgo.toISOString()}'`,
        excludeInvoiceId ? sql`${schema.invoices.id} != ${excludeInvoiceId}` : sql`1=1`
      )
    )
    .orderBy(desc(sql`1 - abs(${schema.invoices.totalAmount} - ${amount}) / ${Math.max(amount, 100)}`))
    .limit(1);

  if (similar && similar.similarity > 0.9) {
    return { isDuplicate: true, similarity: similar.similarity, duplicateOfId: similar.id };
  }

  return { isDuplicate: false, similarity: 0, duplicateOfId: null };
}

/**
 * Calculate runway pressure
 * Returns 0-1 based on cash impact
 */
export function calculateRunwayPressure(
  invoiceAmount: number,
  cashBalance: number,
  monthlyBurnRate: number
): number {
  if (monthlyBurnRate <= 0) return 0;

  const monthlyEquivalent = invoiceAmount / monthlyBurnRate;
  const pressure = monthlyEquivalent / 12; // Normalize to yearly

  return Math.min(1, Math.max(0, pressure));
}

/**
 * Assess vendor trust score
 * Returns 0-1 based on payment history
 */
export async function assessVendorTrust(
  env: Env,
  vendorId: string | null
): Promise<{ trustScore: number; avgInvoiceAmount: number; totalInvoices: number }> {
  if (!vendorId) {
    return { trustScore: 0.5, avgInvoiceAmount: 0, totalInvoices: 0 }; // Default for unknown vendors
  }

  const db = getDb(env);

  const [vendor] = await db
    .select({
      trustScore: schema.vendors.riskLevel, // Using riskLevel as proxy for trust
      avgInvoiceAmount: schema.vendors.avgInvoiceAmount,
      totalInvoices: schema.vendors.totalInvoices,
    })
    .from(schema.vendors)
    .where(eq(schema.vendors.id, vendorId))
    .limit(1);

  if (!vendor) {
    return { trustScore: 0.5, avgInvoiceAmount: 0, totalInvoices: 0 };
  }

  // Convert risk level to trust score (inverse)
  const trustScore = vendor.trustScore
    ? vendor.trustScore === "LOW"
      ? 0.9
      : vendor.trustScore === "MEDIUM"
        ? 0.6
        : vendor.trustScore === "HIGH"
          ? 0.3
          : 0.5
    : 0.5;

  return {
    trustScore,
    avgInvoiceAmount: vendor.avgInvoiceAmount || 0,
    totalInvoices: vendor.totalInvoices || 0,
  };
}

/**
 * Perform full risk assessment for an invoice
 */
export async function assessInvoiceRisk(
  env: Env,
  invoiceId: string
): Promise<RiskAssessmentResult | null> {
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) return null;

  // Get vendor trust
  const vendorTrust = await assessVendorTrust(env, invoice.vendorId);

  // Calculate amount deviation
  const amountDeviation = await calculateAmountDeviation(
    env,
    invoice.vendorId,
    invoice.totalAmount
  );

  // Check for duplicates
  const duplicate = await checkDuplicateInvoices(
    env,
    invoice.vendorId,
    invoice.invoiceNumber,
    invoice.totalAmount,
    invoiceId
  );

  // Calculate runway pressure (using defaults if company context not available)
  const runwayPressure = calculateRunwayPressure(
    invoice.totalAmount,
    100000, // Default cash balance
    20000   // Default burn rate
  );

  // Check if new vendor
  const isNewVendor = vendorTrust.totalInvoices === 0 ? 1 : 0;

  // Calculate risk
  const inputs: RiskInputs = {
    vendorTrust: vendorTrust.trustScore,
    amountDeviation,
    duplicateSimilarity: duplicate.similarity,
    runwayPressure,
    isNewVendor,
  };

  const result = calculateRisk(inputs);

  // Update invoice with risk assessment
  await db
    .update(schema.invoices)
    .set({
      riskScore: result.score,
      riskLevel: result.level,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, invoiceId));

  // Log risk assessment to audit
  await logRiskAssessment(env, invoiceId, result);

  return result;
}

/**
 * Log risk assessment to audit trail
 */
async function logRiskAssessment(
  env: Env,
  invoiceId: string,
  result: RiskAssessmentResult
): Promise<void> {
  const db = getDb(env);

  await db.insert(schema.auditLogs).values({
    id: crypto.randomUUID(),
    action: "RISK_ASSESSED",
    entityType: "invoice",
    entityId: invoiceId,
    performedBy: "system",
    performedAt: new Date().toISOString(),
    changes: JSON.stringify({
      riskScore: result.score,
      riskLevel: result.level,
      confidence: result.confidence,
      signals: result.signals,
    }),
  });
}
