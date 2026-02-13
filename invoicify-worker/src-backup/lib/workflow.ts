/**
 * LangGraph Workflow State Machine - Context-Aware Agent
 *
 * Implements the agent workflow from PRD Section 7:
 * START → Ingest → Extract → Context → Risk → (Analyst → Critic) → (AutoApprove|HITL|Escalate) → Ledger → Learn → END
 *
 * Key extensions for Context-Aware Agent:
 * - FinancialContext injection (Runway, Budget, Strategy)
 * - Critic Node with Priority Matrix (Runway > Strategy > Contract)
 * - Trust Battery for gradual autonomy
 * - Reasoning Chain for explainability
 *
 * State machine for invoice processing workflow
 */

import { getDb, schema } from "../db";
import { eq, sql, and, desc, gte } from "drizzle-orm";
import type { Env } from "../db";

// ============================================================================
// AGENT CONTEXT LAYER - The "Brain" of the Agent
// ============================================================================

/**
 * Strategic mode for the company (affects payment behavior)
 */
export const StrategyMode = {
  SURVIVAL: "SURVIVAL",   // Conserve cash, delay payments
  GROWTH: "GROWTH",       // Pay fast, build vendor trust
  OPTIMIZE: "OPTIMIZE",   // Balance, maximize discounts
} as const;

export type StrategyModeType = (typeof StrategyMode)[keyof typeof StrategyMode];

/**
 * Budget category for expense tracking
 */
export interface BudgetCategory {
  category: string;
  monthlyLimit: number;
  currentSpend: number;
  softCapAlert: boolean;
}

/**
 * Company financial context (injected at runtime)
 */
export interface FinancialContext {
  // Runway & Cash
  currentCash: number;
  monthlyBurnRate: number;
  runwayDays: number;
  payrollDate: string | null;
  payrollAmount: number;
  safetyBuffer: number; // Minimum cash to maintain

  // Strategy
  strategyMode: StrategyModeType;
  autoApproveThreshold: number; // Dollar threshold for auto-approve

  // Budget
  budgets: BudgetCategory[];

  // Trust Battery
  trustLevel: 1 | 2 | 3; // 1=Review All, 2=Review Exceptions, 3=Auto-Approve
  consecutiveAccuracy: number; // Track accuracy for trust graduation

  // Vendor State
  pendingPaymentsThisMonth: number;
  categorySpending: Record<string, number>;
}

/**
 * Get company financial context
 */
export async function getFinancialContext(env: Env): Promise<FinancialContext> {
  const db = getDb(env);

  // Get current cash balance (mock - would integrate with Plaid in production)
  const currentCash = 100000; // Default mock value
  const monthlyBurnRate = 20000;
  const runwayDays = Math.floor(currentCash / monthlyBurnRate * 30);

  // Get total pending payments
  const [pendingResult] = await db
    .select({ total: sql<number>`coalesce(sum(${schema.payments.amount}), 0)` })
    .from(schema.payments)
    .where(eq(schema.payments.status, "scheduled"));

  const pendingPaymentsThisMonth = pendingResult.total || 0;

  // Get category spending (mock - would query invoices in production)
  const categorySpending: Record<string, number> = {
    Infra: 5000,
    Marketing: 3000,
    "G&A": 2000,
    Payroll: 15000,
  };

  // Get strategy mode (would store in config table in production)
  const strategyMode = StrategyMode.OPTIMIZE;

  // Get trust level (would query trust_metrics table)
  const trustLevel: 1 | 2 | 3 = 2;

  // Get consecutive accuracy for trust battery
  const [accuracy] = await db
    .select({ avg: sql<number>`coalesce(avg(${schema.invoices.riskScore}), 0)` })
    .from(schema.invoices)
    .limit(1);

  return {
    currentCash,
    monthlyBurnRate,
    runwayDays,
    payrollDate: "2024-02-01", // Mock payroll date
    payrollAmount: 15000,
    safetyBuffer: 10000,
    strategyMode,
    autoApproveThreshold: 500,
    budgets: [
      { category: "Infra", monthlyLimit: 10000, currentSpend: 5000, softCapAlert: true },
      { category: "Marketing", monthlyLimit: 5000, currentSpend: 3000, softCapAlert: true },
      { category: "G&A", monthlyLimit: 3000, currentSpend: 2000, softCapAlert: true },
    ],
    pendingPaymentsThisMonth,
    categorySpending,
    trustLevel,
    consecutiveAccuracy: 0.95,
  };
}

/**
 * Decision signal from Analyst/Critic nodes
 */
export interface DecisionSignal {
  type: "RUNWAY" | "STRATEGY" | "CONTRACT" | "TRUST" | "BUDGET" | "DUPLICATE" | "FRAUD";
  severity: "INFO" | "WARNING" | "CRITICAL" | "BLOCK";
  message: string;
  recommendation: string;
  data?: Record<string, any>;
}

/**
 * Agent reasoning step (for explainability)
 */
export interface ReasoningStep {
  node: string;
  thought: string;
  decision: string;
  confidence: number;
  timestamp: string;
}

// ============================================================================
// WORKFLOW STATE EXTENDED FOR AGENT
// ============================================================================

/**
 * Extended workflow state definition for Context-Aware Agent
 */
export interface WorkflowState {
  // Invoice data
  invoiceId: string | null;
  vendorId: string | null;
  vendorName: string | null;
  invoiceNumber: string | null;
  amount: number | null;
  currency: string | null;
  dueDate: string | null;
  issueDate: string | null;
  rawText: string | null;
  parsedData: Record<string, any> | null;

  // Context (Extended)
  vendorTrustScore: number | null;
  avgVendorAmount: number | null;
  vendorPaymentTerms: number | null;
  vendorTrustLevel: 1 | 2 | 3; // 1=Core, 2=Standard, 3=Probation
  contractTerms: string | null;
  isNewVendor: boolean;

  // Company Financial Context (Injected)
  financialContext: FinancialContext | null;

  // Risk assessment
  riskScore: number | null;
  riskConfidence: number | null;
  riskLevel: string | null;
  riskSignals: string[];
  riskBreakdown: Record<string, number>;

  // Analyst/Critic Decision
  analystProposal: string | null;
  criticSignals: DecisionSignal[];
  criticOverruled: boolean;
  finalDecision: "AUTO_APPROVE" | "HITL_REQUIRED" | "BLOCK" | "RE-SCHEDULE" | null;

  // Decision
  action: "auto_approve" | "hitl" | "escalate" | "re-schedule" | null;
  approval: {
    decision: string | null;
    approver: string | null;
    reason: string | null;
    confidenceOverride: boolean;
  } | null;

  // Execution
  paymentScheduledDate: string | null;
  ledgerPosted: boolean;
  markdownOutput: string;

  // Meta
  success: boolean;
  errors: string[];
  traceId: string | null;
  currentNode: string;

  // Agent-specific (Explainability)
  reasoningChain: ReasoningStep[];
  agentMemory: Record<string, any>;
  toolResults: Record<string, any>;
}

/**
 * Initial state factory (Extended)
 */
export function createInitialState(overrides?: Partial<WorkflowState>): WorkflowState {
  return {
    invoiceId: null,
    vendorId: null,
    vendorName: null,
    invoiceNumber: null,
    amount: null,
    currency: "USD",
    dueDate: null,
    issueDate: null,
    rawText: null,
    parsedData: null,
    vendorTrustScore: null,
    avgVendorAmount: null,
    vendorPaymentTerms: 30,
    vendorTrustLevel: 3, // Default to probation
    contractTerms: null,
    isNewVendor: true,
    financialContext: null,
    riskScore: null,
    riskConfidence: null,
    riskLevel: null,
    riskSignals: [],
    riskBreakdown: {},
    analystProposal: null,
    criticSignals: [],
    criticOverruled: false,
    finalDecision: null,
    action: null,
    approval: null,
    paymentScheduledDate: null,
    ledgerPosted: false,
    markdownOutput: "",
    success: false,
    errors: [],
    traceId: crypto.randomUUID(),
    currentNode: "START",
    reasoningChain: [],
    agentMemory: {},
    toolResults: {},
    ...overrides,
  };
}

/**
 * Workflow nodes (Extended with Analyst/Critic)
 */
export const WorkflowNodes = {
  START: "START",
  INGEST: "ingest_invoice",
  EXTRACT: "extract_fields",
  CONTEXT: "fetch_context",
  RISK: "assess_risk",
  ANALYST: "analyst_propose",      // Proposes action based on history/patterns
  CRITIC: "critic_review",         // Safety checks - the "Internal Auditor"
  ROUTE: "route_action",
  AUTO_APPROVE: "auto_approve",
  HUMAN_REVIEW: "human_review",
  POST_LEDGER: "post_to_ledger",
  LEARN: "learn_from_outcome",
  END: "END",
} as const;

/**
 * Node result types
 */
export type NodeResult = {
  state: Partial<WorkflowState>;
  nextNode: string;
  interrupt?: boolean;
  error?: string;
};

/**
 * Ingest invoice node
 */
export async function nodeIngestInvoice(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    const db = getDb(env);

    // Create invoice record
    const invoiceId = crypto.randomUUID();

    await db.insert(schema.invoices).values({
      id: invoiceId,
      vendorName: state.vendorName || "Unknown",
      invoiceNumber: state.invoiceNumber || `INV-${Date.now()}`,
      totalAmount: state.amount || 0,
      currency: state.currency || "USD",
      dueDate: state.dueDate,
      invoiceDate: state.issueDate,
      rawContent: state.rawText,
      status: "NEW",
      createdAt: new Date().toISOString(),
    });

    return {
      state: {
        invoiceId,
        currentNode: WorkflowNodes.INGEST,
      },
      nextNode: WorkflowNodes.EXTRACT,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Extract fields node (OCR + parsing)
 */
export async function nodeExtractFields(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    // In real implementation, would use OCR/AI extraction
    const parsedData = state.parsedData || {};

    // Update invoice with extracted data
    if (state.invoiceId) {
      const db = getDb(env);
      await db
        .update(schema.invoices)
        .set({
          extractedData: JSON.stringify(parsedData),
          status: "EXTRACTED",
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, state.invoiceId));
    }

    return {
      state: {
        parsedData,
        currentNode: WorkflowNodes.EXTRACT,
      },
      nextNode: WorkflowNodes.CONTEXT,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Fetch context node
 */
export async function nodeFetchContext(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    const db = getDb(env);

    // Get vendor context
    let vendorTrustScore = 0.5;
    let avgVendorAmount = 0;
    let vendorPaymentTerms = 30;

    if (state.vendorId) {
      const [vendor] = await db
        .select()
        .from(schema.vendors)
        .where(eq(schema.vendors.id, state.vendorId))
        .limit(1);

      if (vendor) {
        vendorTrustScore = vendor.riskLevel
          ? vendor.riskLevel === "LOW"
            ? 0.9
            : vendor.riskLevel === "MEDIUM"
              ? 0.6
              : 0.3
          : 0.5;
        avgVendorAmount = vendor.avgInvoiceAmount || 0;
        vendorPaymentTerms = vendorPaymentTerms; // Default
      }
    }

    return {
      state: {
        vendorTrustScore,
        avgVendorAmount,
        vendorPaymentTerms,
        currentNode: WorkflowNodes.CONTEXT,
      },
      nextNode: WorkflowNodes.RISK,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Assess risk node
 */
export async function nodeAssessRisk(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    // Import risk scoring
    const { calculateRisk, routeAction } = await import("./risk-scoring");

    // Use financialContext if available, otherwise fall back to defaults
    const ctx = state.financialContext;
    const cashBalance = ctx?.currentCash || 100000;
    const runwayDays = ctx?.runwayDays || 90;

    const inputs = {
      vendorTrust: state.vendorTrustScore || 0.5,
      amountDeviation: state.amount && state.avgVendorAmount
        ? Math.abs(state.amount - state.avgVendorAmount) / state.avgVendorAmount
        : 0,
      duplicateSimilarity: 0,
      runwayPressure: state.amount && cashBalance && runwayDays
        ? (state.amount / cashBalance) * 12 / runwayDays
        : 0.1,
      isNewVendor: state.vendorTrustScore === null ? 1 : 0,
    };

    const assessment = calculateRisk(inputs);
    const action = routeAction(assessment.score, assessment.confidence);

    // Update invoice with risk assessment
    if (state.invoiceId) {
      const db = getDb(env);
      await db
        .update(schema.invoices)
        .set({
          riskScore: assessment.score,
          riskLevel: assessment.level,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, state.invoiceId));
    }

    return {
      state: {
        riskScore: assessment.score,
        riskConfidence: assessment.confidence,
        riskLevel: assessment.level,
        riskSignals: assessment.signals,
        riskBreakdown: assessment.breakdown,
        action,
        currentNode: WorkflowNodes.RISK,
      },
      // Route to Analyst first for pattern detection, then Critic for safety checks
      nextNode: WorkflowNodes.ANALYST,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

// ============================================================================
// ANALYST NODE - Proposes action based on history/patterns
// ============================================================================

/**
 * Analyst node: Proposes an action based on historical patterns
 */
export async function nodeAnalyst(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    const signals: DecisionSignal[] = [];
    const reasoning: string[] = [];

    // Pattern 1: Amount vs Vendor Average
    if (state.amount && state.avgVendorAmount) {
      const variance = Math.abs(state.amount - state.avgVendorAmount) / state.avgVendorAmount;
      if (variance > 0.5) {
        signals.push({
          type: "BUDGET",
          severity: "WARNING",
          message: `Invoice amount $${state.amount} is ${(variance * 100).toFixed(0)}% above vendor average $${state.avgVendorAmount}`,
          recommendation: "Review for overage or unusual purchase",
          data: { variance, avgAmount: state.avgVendorAmount },
        });
        reasoning.push(`Detected ${(variance * 100).toFixed(0)}% variance from vendor average`);
      }
    }

    // Pattern 2: Recurring Invoice Detection
    const db = getDb(env);
    if (state.vendorId && state.amount) {
      const [recentInvoices] = await db
        .select({ count: sql<number>`count(*)`, total: sql<number>`sum(${schema.invoices.totalAmount})` })
        .from(schema.invoices)
        .where(and(
          eq(schema.invoices.vendorId, state.vendorId),
          gte(schema.invoices.createdAt, new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString())
        ));

      if (recentInvoices.count && Number(recentInvoices.count) > 3) {
        const avgAmount = Number(recentInvoices.total) / Number(recentInvoices.count);
        if (Math.abs(state.amount - avgAmount) / avgAmount < 0.1) {
          signals.push({
            type: "DUPLICATE",
            severity: "INFO",
            message: "This appears to be a recurring monthly invoice",
            recommendation: "Auto-approve if consistent with history",
            data: { isRecurring: true, avgAmount },
          });
          reasoning.push("Identified as recurring invoice pattern");
        }
      }
    }

    // Pattern 3: Trust-based proposal
    if (state.vendorTrustLevel === 1 && state.amount && state.amount < 1000) {
      signals.push({
        type: "TRUST",
        severity: "INFO",
        message: "Core vendor with low invoice amount",
        recommendation: "Auto-approve: Core vendor, trusted",
        data: { trustLevel: state.vendorTrustLevel },
      });
      reasoning.push("Core vendor (Level 1) with amount below threshold");
    }

    // Propose action based on patterns
    const hasCritical = signals.some(s => s.severity === "CRITICAL" || s.severity === "BLOCK");
    const hasWarning = signals.some(s => s.severity === "WARNING");

    let proposal = "AUTO_APPROVE";
    if (hasCritical) {
      proposal = "HITL_REQUIRED";
    } else if (hasWarning) {
      proposal = "RE-SCHEDULE"; // Delay for review
    }

    // Add reasoning step
    const reasoningStep: ReasoningStep = {
      node: WorkflowNodes.ANALYST,
      thought: reasoning.join("; ") || "No anomalies detected in historical patterns",
      decision: proposal,
      confidence: 0.85,
      timestamp: new Date().toISOString(),
    };

    return {
      state: {
        analystProposal: proposal,
        criticSignals: signals,
        reasoningChain: [...state.reasoningChain, reasoningStep],
        currentNode: WorkflowNodes.ANALYST,
      },
      nextNode: WorkflowNodes.CRITIC,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

// ============================================================================
// CRITIC NODE - The "Internal Auditor" with Priority Matrix
// Priority: RUNWAY > STRATEGY > CONTRACT > TRUST > BUDGET
// ============================================================================

/**
 * Critic node: Safety checks - overrides Analyst if needed
 * This is the "Internal Auditor" that asks "Why shouldn't I pay this?"
 */
export async function nodeCritic(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    const signals: DecisionSignal[] = [...state.criticSignals];
    const reasoning: string[] = [];
    let overruled = false;
    let finalDecision: WorkflowState["finalDecision"] = state.analystProposal as WorkflowState["finalDecision"];

    const ctx = state.financialContext;
    if (!ctx) {
      signals.push({
        type: "RUNWAY",
        severity: "WARNING",
        message: "Financial context not available",
        recommendation: "Default to HITL for safety",
      });
      return {
        state: {
          criticSignals: signals,
          finalDecision: "HITL_REQUIRED",
          reasoningChain: [...state.reasoningChain, {
            node: WorkflowNodes.CRITIC,
            thought: "No financial context available",
            decision: "HITL_REQUIRED",
            confidence: 0.5,
            timestamp: new Date().toISOString(),
          }],
          currentNode: WorkflowNodes.CRITIC,
        },
        nextNode: WorkflowNodes.HUMAN_REVIEW,
      };
    }

    // ================================================================
    // PRIORITY 1: RUNWAY CHECK (Physical Survival)
    // "If you don't have cash, nothing else matters"
    // ================================================================

    const invoiceAmount = state.amount || 0;
    const projectedCash = ctx.currentCash - invoiceAmount;
    const postPaymentRunway = (projectedCash / ctx.monthlyBurnRate) * 30;

    if (projectedCash < ctx.payrollAmount) {
      signals.push({
        type: "RUNWAY",
        severity: "BLOCK",
        message: `Paying $${invoiceAmount} would leave only $${projectedCash.toFixed(0)} before $${ctx.payrollAmount.toFixed(0)} payroll`,
        recommendation: "BLOCK: Insufficient cash for payroll",
        data: { projectedCash, payrollAmount: ctx.payrollAmount },
      });
      reasoning.push("RUNWAY CHECK FAILED: Would risk payroll");
      finalDecision = "BLOCK";
      overruled = true;
    } else if (postPaymentRunway < 30) {
      signals.push({
        type: "RUNWAY",
        severity: "CRITICAL",
        message: `Payment would reduce runway to ${postPaymentRunway.toFixed(0)} days (< 1 month)`,
        recommendation: "RE-SCHEDULE: Delay payment",
        data: { postPaymentRunway, currentRunway: ctx.runwayDays },
      });
      reasoning.push("RUNWAY CHECK WARNING: Below 30 days");
      if (finalDecision !== "BLOCK") {
        finalDecision = "RE-SCHEDULE";
        overruled = true;
      }
    } else if (postPaymentRunway < 60) {
      signals.push({
        type: "RUNWAY",
        severity: "WARNING",
        message: `Payment would reduce runway to ${postPaymentRunway.toFixed(0)} days (< 2 months)`,
        recommendation: "Proceed with caution",
        data: { postPaymentRunway },
      });
    }

    // ================================================================
    // PRIORITY 2: STRATEGY CHECK (Business Philosophy)
    // "Are we in Survival, Growth, or Optimize mode?"
    // ================================================================

    if (ctx.strategyMode === StrategyMode.SURVIVAL && invoiceAmount > 0) {
      // In survival mode, question all spending
      signals.push({
        type: "STRATEGY",
        severity: "WARNING",
        message: "SURVIVAL mode active: All spending should be questioned",
        recommendation: "Delay payment unless absolutely critical",
        data: { strategyMode: ctx.strategyMode },
      });
      reasoning.push("STRATEGY CHECK: Survival mode");
      if (finalDecision === "AUTO_APPROVE" && !overruled) {
        finalDecision = "RE-SCHEDULE";
        overruled = true;
      }
    }

    if (ctx.strategyMode === StrategyMode.GROWTH && state.isNewVendor) {
      // In growth mode, new vendors get faster approval
      signals.push({
        type: "STRATEGY",
        severity: "INFO",
        message: "GROWTH mode: New vendors prioritized for fast payment",
        recommendation: "Fast-track approval",
        data: { strategyMode: ctx.strategyMode },
      });
    }

    // ================================================================
    // PRIORITY 3: CONTRACT CHECK (Legal/Ops)
    // "Does this invoice match our contract terms?"
    // ================================================================

    if (state.contractTerms && invoiceAmount > 1000) {
      // Mock contract violation check - in production would use Vector DB
      const hasOverageTerms = state.contractTerms.toLowerCase().includes("overage");
      const isLineItemOverage = state.parsedData?.lineItems?.some(
        (item: any) => item.description?.toLowerCase().includes("overage")
      );

      if (hasOverageTerms && isLineItemOverage) {
        signals.push({
          type: "CONTRACT",
          severity: "CRITICAL",
          message: "Invoice contains overage charges - verify against contract cap",
          recommendation: "HITL_REQUIRED: Review overage terms",
          data: { hasOverageTerms, isLineItemOverage },
        });
        reasoning.push("CONTRACT CHECK: Overage charges detected");
        if (finalDecision !== "BLOCK") {
          finalDecision = "HITL_REQUIRED";
          overruled = true;
        }
      }
    }

    // ================================================================
    // PRIORITY 4: TRUST BATTERY CHECK
    // "What's our autonomy level based on recent accuracy?"
    // ================================================================

    if (ctx.trustLevel === 1) {
      signals.push({
        type: "TRUST",
        severity: "INFO",
        message: "Trust Battery Level 1: Manual review required for all",
        recommendation: "Require human approval",
        data: { trustLevel: ctx.trustLevel, consecutiveAccuracy: ctx.consecutiveAccuracy },
      });
      if (finalDecision === "AUTO_APPROVE") {
        finalDecision = "HITL_REQUIRED";
        overruled = true;
        reasoning.push("TRUST BATTERY: Level 1 requires review");
      }
    } else if (ctx.trustLevel === 2 && finalDecision === "AUTO_APPROVE") {
      signals.push({
        type: "TRUST",
        severity: "INFO",
        message: "Trust Battery Level 2: Auto-approve with notification",
        recommendation: "Proceed with auto-approve",
        data: { trustLevel: ctx.trustLevel },
      });
    }

    // ================================================================
    // PRIORITY 5: BUDGET CHECK
    // "Does this break category budgets?"
    // ================================================================

    const invoiceCategory = state.parsedData?.category || "G&A";
    const categoryLimit = ctx.budgets.find(b => b.category === invoiceCategory);
    if (categoryLimit) {
      const projectedSpend = (ctx.categorySpending[invoiceCategory] || 0) + invoiceAmount;
      if (projectedSpend > categoryLimit.monthlyLimit) {
        signals.push({
          type: "BUDGET",
          severity: "WARNING",
          message: `This would exceed ${invoiceCategory} budget ($${projectedSpend} / $${categoryLimit.monthlyLimit})`,
          recommendation: "Flag for budget review",
          data: { category: invoiceCategory, projectedSpend, limit: categoryLimit.monthlyLimit },
        });
        reasoning.push("BUDGET CHECK: Would exceed monthly limit");
      }
    }

    // Add reasoning step
    const reasoningStep: ReasoningStep = {
      node: WorkflowNodes.CRITIC,
      thought: reasoning.length > 0
        ? `Critic review: ${signals.filter(s => s.severity !== "INFO").length} concerns found. ${signals.filter(s => s.severity === "BLOCK").length} blockers.`
        : "Critic passed: No safety concerns found",
      decision: finalDecision || "AUTO_APPROVE",
      confidence: overruled ? 0.95 : 0.8,
      timestamp: new Date().toISOString(),
    };

    return {
      state: {
        criticSignals: signals,
        criticOverruled: overruled,
        finalDecision,
        reasoningChain: [...state.reasoningChain, reasoningStep],
        currentNode: WorkflowNodes.CRITIC,
      },
      nextNode: finalDecision === "BLOCK"
        ? WorkflowNodes.END
        : finalDecision === "AUTO_APPROVE"
          ? WorkflowNodes.AUTO_APPROVE
          : WorkflowNodes.HUMAN_REVIEW,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Auto approve node
 */
export async function nodeAutoApprove(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    if (state.invoiceId) {
      const db = getDb(env);
      await db
        .update(schema.invoices)
        .set({
          status: "APPROVED",
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, state.invoiceId));

      // Create approval record
      await db.insert(schema.approvals).values({
        id: crypto.randomUUID(),
        invoiceId: state.invoiceId,
        approverEmail: "system@auto",
        approverName: "Auto-Approve",
        status: "APPROVED",
        comments: `Auto-approved: Risk score ${state.riskScore?.toFixed(2)}`,
        createdAt: new Date().toISOString(),
      });
    }

    return {
      state: {
        approval: {
          decision: "approved",
          approver: "system",
          reason: "Low risk auto-approval",
          confidenceOverride: false,
        },
        currentNode: WorkflowNodes.AUTO_APPROVE,
      },
      nextNode: WorkflowNodes.POST_LEDGER,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Human review (HITL) node
 */
export async function nodeHumanReview(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  // In real implementation, this would create an interrupt
  // For now, we mark as pending approval

  if (state.invoiceId) {
    const db = getDb(env);
    await db
      .update(schema.invoices)
      .set({
        status: "PENDING",
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.invoices.id, state.invoiceId));
  }

  return {
    state: {
      currentNode: WorkflowNodes.HUMAN_REVIEW,
    },
    nextNode: WorkflowNodes.POST_LEDGER,
    interrupt: true, // Marks this as a HITL point
  };
}

/**
 * Post to ledger node
 */
export async function nodePostLedger(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  try {
    // Generate markdown output
    const markdownOutput = generateInvoiceMarkdown(state);

    if (state.invoiceId) {
      const db = getDb(env);
      await db
        .update(schema.invoices)
        .set({
          status: state.action === "auto_approve" ? "APPROVED" : "PENDING",
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, state.invoiceId));

      // Log to audit
      await db.insert(schema.auditLogs).values({
        id: crypto.randomUUID(),
        action: "INVOICE_PROCESSED",
        entityType: "invoice",
        entityId: state.invoiceId,
        performedBy: "agent",
        performedAt: new Date().toISOString(),
        changes: JSON.stringify({
          riskScore: state.riskScore,
          riskLevel: state.riskLevel,
          action: state.action,
        }),
      });
    }

    return {
      state: {
        ledgerPosted: true,
        markdownOutput,
        success: true,
        currentNode: WorkflowNodes.POST_LEDGER,
      },
      nextNode: WorkflowNodes.LEARN,
    };
  } catch (error) {
    return {
      state: { errors: [(error as Error).message] },
      nextNode: WorkflowNodes.END,
      error: (error as Error).message,
    };
  }
}

/**
 * Learn from outcome node
 */
export async function nodeLearnFromOutcome(
  env: Env,
  state: WorkflowState
): Promise<NodeResult> {
  // In real implementation, would update vendor trust scores
  // and risk weights based on outcomes

  return {
    state: {
      currentNode: WorkflowNodes.LEARN,
    },
    nextNode: WorkflowNodes.END,
  };
}

/**
 * Generate markdown output for invoice
 */
function generateInvoiceMarkdown(state: WorkflowState): string {
  const lines = [
    `## Invoice ${state.invoiceNumber || "N/A"}`,
    "",
    `**Vendor:** ${state.vendorName || "Unknown"}`,
    `**Amount:** ${state.amount ? `$${state.amount.toFixed(2)}` : "N/A"}`,
    `**Currency:** ${state.currency || "USD"}`,
    `**Due Date:** ${state.dueDate || "N/A"}`,
    "",
    `**Risk Score:** ${state.riskScore?.toFixed(2) || "N/A"}`,
    `**Risk Level:** ${state.riskLevel || "N/A"}`,
    "",
  ];

  if (state.riskSignals.length > 0) {
    lines.push("**Risk Signals:**");
    state.riskSignals.forEach((signal) => {
      lines.push(`- ${signal}`);
    });
    lines.push("");
  }

  if (state.action) {
    lines.push(`**Action:** ${state.action.replace("_", " ")}`);
  }

  return lines.join("\n");
}

/**
 * Execute workflow step
 */
export async function executeWorkflowStep(
  env: Env,
  state: WorkflowState
): Promise<WorkflowState> {
  // Inject financial context if not present (for Analyst/Critic nodes)
  let currentState = state;
  if (!state.financialContext && state.currentNode !== WorkflowNodes.START) {
    const financialContext = await getFinancialContext(env);
    currentState = { ...state, financialContext };
  }

  const nodeHandlers: Record<string, (env: Env, state: WorkflowState) => Promise<NodeResult>> = {
    [WorkflowNodes.INGEST]: nodeIngestInvoice,
    [WorkflowNodes.EXTRACT]: nodeExtractFields,
    [WorkflowNodes.CONTEXT]: nodeFetchContext,
    [WorkflowNodes.RISK]: nodeAssessRisk,
    [WorkflowNodes.ANALYST]: nodeAnalyst,
    [WorkflowNodes.CRITIC]: nodeCritic,
    [WorkflowNodes.ROUTE]: nodeCritic, // Route uses critic logic
    [WorkflowNodes.AUTO_APPROVE]: nodeAutoApprove,
    [WorkflowNodes.HUMAN_REVIEW]: nodeHumanReview,
    [WorkflowNodes.POST_LEDGER]: nodePostLedger,
    [WorkflowNodes.LEARN]: nodeLearnFromOutcome,
  };

  // END node - workflow complete
  if (currentState.currentNode === WorkflowNodes.END) {
    return { ...currentState, success: true } as WorkflowState;
  }

  const handler = nodeHandlers[currentState.currentNode];
  if (!handler) {
    return { ...currentState, success: false, errors: [...currentState.errors, "Unknown node"] } as WorkflowState;
  }

  const result = await handler(env, currentState);

  return {
    ...currentState,
    ...result.state,
    currentNode: result.nextNode,
    errors: result.error ? [...currentState.errors, result.error] : currentState.errors,
    success: result.nextNode === WorkflowNodes.END,
  } as WorkflowState;
}

/**
 * Run complete workflow (Extended for Agent)
 */
export async function runWorkflow(
  env: Env,
  initialState: WorkflowState
): Promise<WorkflowState> {
  let state = initialState;

  // Handle START node - transition immediately to INGEST
  if (state.currentNode === WorkflowNodes.START) {
    state = { ...state, currentNode: WorkflowNodes.INGEST };
  }

  // Pre-fetch financial context for the workflow
  if (!state.financialContext) {
    state = { ...state, financialContext: await getFinancialContext(env) };
  }

  const maxSteps = 15; // Extended for Analyst/Critic nodes
  let steps = 0;

  while (state.currentNode !== WorkflowNodes.END && steps < maxSteps) {
    state = await executeWorkflowStep(env, state);
    steps++;

    // Break on interrupt (HITL)
    if (state.currentNode === WorkflowNodes.HUMAN_REVIEW) {
      break;
    }
  }

  return state;
}
