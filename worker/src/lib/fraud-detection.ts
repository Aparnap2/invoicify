import type { Env } from "../db";
import { getDb, schema } from "../db";
import { eq, and, desc } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";

/**
 * Risk assessment result
 */
export interface RiskAssessmentResult {
  score: number;
  level: RiskLevel;
  indicators: RiskIndicator[];
  recommendation: string;
}

/**
 * Risk level enum
 */
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

/**
 * Risk indicator detected
 */
export interface RiskIndicator {
  type: string;
  severity: RiskLevel;
  description: string;
  scoreContribution: number;
}

/**
 * Vendor history for comparison
 */
interface VendorHistory {
  exists: boolean;
  avgInvoiceAmount: number;
  totalInvoices: number;
  bankAccount?: string;
  riskLevel?: string;
}

/**
 * Invoice data for risk analysis
 */
export interface InvoiceData {
  id: string;
  vendorId?: string;
  vendorName: string;
  totalAmount: number;
  currency: string;
  dueDate?: string;
  invoiceDate?: string;
  paymentTerms?: string;
  bankAccount?: string;
  confidenceScore?: number;
}

/**
 * Calculate risk score for an invoice
 */
export async function calculateRiskScore(
  env: Env,
  invoiceData: InvoiceData
): Promise<RiskAssessmentResult> {
  const db = getDb(env);
  const indicators: RiskIndicator[] = [];
  let totalScore = 0;

  // Get vendor history
  const vendorHistory = await getVendorHistory(db, invoiceData.vendorName);

  // Amount anomaly check (>3x average)
  if (vendorHistory.exists && vendorHistory.avgInvoiceAmount > 0) {
    const amountMultiplier = invoiceData.totalAmount / vendorHistory.avgInvoiceAmount;

    if (amountMultiplier > 5) {
      indicators.push({
        type: "AMOUNT_ANOMALY",
        severity: "CRITICAL",
        description: `Invoice amount is ${amountMultiplier.toFixed(1)}x the vendor's average ($${vendorHistory.avgInvoiceAmount.toFixed(2)})`,
        scoreContribution: 40,
      });
      totalScore += 40;
    } else if (amountMultiplier > 3) {
      indicators.push({
        type: "AMOUNT_ANOMALY",
        severity: "HIGH",
        description: `Invoice amount is ${amountMultiplier.toFixed(1)}x the vendor's average ($${vendorHistory.avgInvoiceAmount.toFixed(2)})`,
        scoreContribution: 30,
      });
      totalScore += 30;
    } else if (amountMultiplier > 2) {
      indicators.push({
        type: "AMOUNT_ANOMALY",
        severity: "MEDIUM",
        description: `Invoice amount is ${amountMultiplier.toFixed(1)}x the vendor's average ($${vendorHistory.avgInvoiceAmount.toFixed(2)})`,
        scoreContribution: 15,
      });
      totalScore += 15;
    }
  }

  // New vendor check
  if (!vendorHistory.exists) {
    indicators.push({
      type: "NEW_VENDOR",
      severity: "MEDIUM",
      description: "First invoice from this vendor - no historical data available",
      scoreContribution: 20,
    });
    totalScore += 20;
  }

  // Bank account change check
  if (vendorHistory.bankAccount && invoiceData.bankAccount) {
    if (invoiceData.bankAccount !== vendorHistory.bankAccount) {
      indicators.push({
        type: "BANK_CHANGE",
        severity: "HIGH",
        description: "Bank account number differs from vendor's historical records",
        scoreContribution: 25,
      });
      totalScore += 25;
    }
  }

  // Urgent payment terms check
  const urgentTerms = ["COD", "Immediate", "Net 0", "Due on Receipt", "Prepaid"];
  if (invoiceData.paymentTerms && urgentTerms.some(term => invoiceData.paymentTerms?.toLowerCase().includes(term.toLowerCase()))) {
    indicators.push({
      type: "URGENT_PAYMENT",
      severity: "MEDIUM",
      description: "Payment terms require immediate or urgent payment",
      scoreContribution: 15,
    });
    totalScore += 15;
  }

  // Low extraction confidence check
  if (invoiceData.confidenceScore && invoiceData.confidenceScore < 0.7) {
    indicators.push({
      type: "LOW_CONFIDENCE",
      severity: "MEDIUM",
      description: `Data extraction confidence is low (${(invoiceData.confidenceScore * 100).toFixed(0)}%) - manual review recommended`,
      scoreContribution: 15,
    });
    totalScore += 15;
  }

  // High invoice amount check
  if (invoiceData.totalAmount > 100000) {
    indicators.push({
      type: "HIGH_VALUE",
      severity: "HIGH",
      description: `High value invoice ($${invoiceData.totalAmount.toLocaleString()}) requires approval`,
      scoreContribution: 20,
    });
    totalScore += 20;
  } else if (invoiceData.totalAmount > 50000) {
    indicators.push({
      type: "HIGH_VALUE",
      severity: "MEDIUM",
      description: `Elevated invoice value ($${invoiceData.totalAmount.toLocaleString()})`,
      scoreContribution: 10,
    });
    totalScore += 10;
  }

  // Due date in the past
  if (invoiceData.dueDate && invoiceData.invoiceDate) {
    const dueDate = new Date(invoiceData.dueDate);
    const invoiceDate = new Date(invoiceData.invoiceDate);
    if (dueDate < invoiceDate) {
      indicators.push({
        type: "PAST_DUE_DATE",
        severity: "HIGH",
        description: "Due date is before invoice date - possible data error or fraud indicator",
        scoreContribution: 25,
      });
      totalScore += 25;
    }
  }

  // Duplicate check (same vendor, amount, close date)
  if (vendorHistory.exists && vendorHistory.totalInvoices > 0) {
    const recentDuplicates = await checkForDuplicates(db, invoiceData);
    if (recentDuplicates) {
      indicators.push({
        type: "POTENTIAL_DUPLICATE",
        severity: "CRITICAL",
        description: "Similar invoice found from same vendor within last 30 days",
        scoreContribution: 35,
      });
      totalScore += 35;
    }
  }

  // Check for blacklisted vendors
  if (vendorHistory.riskLevel === "HIGH" || vendorHistory.riskLevel === "CRITICAL") {
    indicators.push({
      type: "BLACKLISTED_VENDOR",
      severity: "CRITICAL",
      description: `Vendor has a ${vendorHistory.riskLevel} risk rating`,
      scoreContribution: 50,
    });
    totalScore += 50;
  }

  // Determine overall risk level
  const level = classifyRiskLevel(totalScore);

  // Generate recommendation
  const recommendation = generateRecommendation(level, indicators);

  // Update invoice with risk data
  await db
    .update(schema.invoices)
    .set({
      riskScore: totalScore,
      riskLevel: level,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, invoiceData.id));

  // Store risk indicators
  for (const indicator of indicators) {
    await db.insert(schema.riskIndicators).values({
      id: uuidv4(),
      invoiceId: invoiceData.id,
      indicatorType: indicator.type,
      severity: indicator.severity,
      description: indicator.description,
      scoreContribution: indicator.scoreContribution,
      createdAt: new Date().toISOString(),
    });
  }

  return {
    score: Math.min(totalScore, 100),
    level,
    indicators,
    recommendation,
  };
}

/**
 * Get vendor history for comparison
 */
async function getVendorHistory(db: any, vendorName: string): Promise<VendorHistory> {
  const [vendor] = await db
    .select()
    .from(schema.vendors)
    .where(eq(schema.vendors.name, vendorName))
    .limit(1);

  if (!vendor) {
    return { exists: false, avgInvoiceAmount: 0, totalInvoices: 0 };
  }

  // Calculate average invoice amount from invoices
  const [stats] = await db
    .select({
      avg: db.$typeof<number>`coalesce(avg(${schema.invoices.totalAmount}), 0)`,
      count: db.$typeof<number>`count(*)`,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.vendorName, vendorName));

  return {
    exists: true,
    avgInvoiceAmount: stats.avg || 0,
    totalInvoices: stats.count || 0,
    bankAccount: vendor.bankAccount || undefined,
    riskLevel: vendor.riskLevel || undefined,
  };
}

/**
 * Check for potential duplicates
 */
async function checkForDuplicates(db: any, invoiceData: InvoiceData): Promise<boolean> {
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const [recentInvoice] = await db
    .select()
    .from(schema.invoices)
    .where(
      and(
        eq(schema.invoices.vendorName, invoiceData.vendorName),
        eq(schema.invoices.totalAmount, invoiceData.totalAmount),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        db.$typeof<any>`date(${schema.invoices.createdAt}) >= date('${thirtyDaysAgo.toISOString()}')`
      )
    )
    .limit(1);

  return recentInvoice !== undefined && recentInvoice.id !== invoiceData.id;
}

/**
 * Classify risk score into level
 */
function classifyRiskLevel(score: number): RiskLevel {
  if (score >= 70) return "CRITICAL";
  if (score >= 50) return "HIGH";
  if (score >= 25) return "MEDIUM";
  return "LOW";
}

/**
 * Generate recommendation based on risk level and indicators
 */
function generateRecommendation(level: RiskLevel, indicators: RiskIndicator[]): string {
  if (level === "CRITICAL") {
    return "BLOCKED - Do not process. Manual investigation required. Multiple high-risk indicators detected.";
  }

  if (level === "HIGH") {
    return "ESCALATE - Requires manager approval before processing. Review all flagged indicators.";
  }

  if (level === "MEDIUM") {
    return "REVIEW - Consider quick review before approval. Flagged indicators should be verified.";
  }

  return "APPROVE - Low risk invoice. Can proceed with normal approval workflow.";
}

/**
 * Run fraud detection for an invoice
 */
export async function runFraudDetection(
  env: Env,
  invoiceId: string
): Promise<RiskAssessmentResult | null> {
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return null;
  }

  const invoiceData: InvoiceData = {
    id: invoice.id,
    vendorId: invoice.vendorId || undefined,
    vendorName: invoice.vendorName,
    totalAmount: invoice.totalAmount,
    currency: invoice.currency || "USD",
    dueDate: invoice.dueDate || undefined,
    invoiceDate: invoice.invoiceDate || undefined,
    confidenceScore: invoice.confidenceScore || undefined,
  };

  return await calculateRiskScore(env, invoiceData);
}

/**
 * Get risk indicators for an invoice
 */
export async function getRiskIndicators(
  env: Env,
  invoiceId: string
): Promise<RiskIndicator[]> {
  const db = getDb(env);

  const indicators = await db
    .select()
    .from(schema.riskIndicators)
    .where(eq(schema.riskIndicators.invoiceId, invoiceId))
    .orderBy(desc(schema.riskIndicators.scoreContribution));

  return indicators.map(i => ({
    type: i.indicatorType,
    severity: i.severity as RiskLevel,
    description: i.description,
    scoreContribution: i.scoreContribution,
  }));
}

/**
 * Resolve a risk indicator
 */
export async function resolveRiskIndicator(
  env: Env,
  indicatorId: string,
  resolvedBy: string
): Promise<boolean> {
  const db = getDb(env);

  const [indicator] = await db
    .select()
    .from(schema.riskIndicators)
    .where(eq(schema.riskIndicators.id, indicatorId))
    .limit(1);

  if (!indicator) {
    return false;
  }

  await db
    .update(schema.riskIndicators)
    .set({
      resolved: true,
      resolvedAt: new Date().toISOString(),
      resolvedBy,
    })
    .where(eq(schema.riskIndicators.id, indicatorId));

  // Recalculate risk score
  await runFraudDetection(env, indicator.invoiceId);

  return true;
}
