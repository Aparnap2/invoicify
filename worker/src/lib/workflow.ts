/**
 * LangGraph Workflow State Machine
 *
 * Implements the agent workflow from PRD Section 7:
 * START → Ingest → Extract → Context → Risk → (AutoApprove|HITL|Escalate) → Ledger → Learn → END
 *
 * State machine for invoice processing workflow
 */

import { getDb, schema } from "../db";
import { eq } from "drizzle-orm";
import type { Env } from "../db";

/**
 * Workflow state definition
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

  // Context
  vendorTrustScore: number | null;
  avgVendorAmount: number | null;
  vendorPaymentTerms: number | null;
  companyRunwayDays: number | null;
  companyCashBalance: number | null;

  // Risk assessment
  riskScore: number | null;
  riskConfidence: number | null;
  riskLevel: string | null;
  riskSignals: string[];
  riskBreakdown: Record<string, number>;

  // Decision
  action: "auto_approve" | "hitl" | "escalate" | null;
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
}

/**
 * Initial state factory
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
    vendorPaymentTerms: null,
    companyRunwayDays: 90,
    companyCashBalance: 100000,
    riskScore: null,
    riskConfidence: null,
    riskLevel: null,
    riskSignals: [],
    riskBreakdown: {},
    action: null,
    approval: null,
    paymentScheduledDate: null,
    ledgerPosted: false,
    markdownOutput: "",
    success: false,
    errors: [],
    traceId: crypto.randomUUID(),
    currentNode: "START",
    ...overrides,
  };
}

/**
 * Workflow nodes
 */
export const WorkflowNodes = {
  START: "START",
  INGEST: "ingest_invoice",
  EXTRACT: "extract_fields",
  CONTEXT: "fetch_context",
  RISK: "assess_risk",
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

    const inputs = {
      vendorTrust: state.vendorTrustScore || 0.5,
      amountDeviation: state.amount && state.avgVendorAmount
        ? Math.abs(state.amount - state.avgVendorAmount) / state.avgVendorAmount
        : 0,
      duplicateSimilarity: 0,
      runwayPressure: state.amount && state.companyCashBalance && state.companyRunwayDays
        ? (state.amount / state.companyCashBalance) * 12 / state.companyRunwayDays
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
      nextNode: action === "auto_approve" ? WorkflowNodes.AUTO_APPROVE :
        action === "hitl" ? WorkflowNodes.HUMAN_REVIEW :
          WorkflowNodes.HUMAN_REVIEW, // Escalate also goes to HITL
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
  const nodeHandlers: Record<string, (env: Env, state: WorkflowState) => Promise<NodeResult>> = {
    [WorkflowNodes.INGEST]: nodeIngestInvoice,
    [WorkflowNodes.EXTRACT]: nodeExtractFields,
    [WorkflowNodes.CONTEXT]: nodeFetchContext,
    [WorkflowNodes.RISK]: nodeAssessRisk,
    [WorkflowNodes.AUTO_APPROVE]: nodeAutoApprove,
    [WorkflowNodes.HUMAN_REVIEW]: nodeHumanReview,
    [WorkflowNodes.POST_LEDGER]: nodePostLedger,
    [WorkflowNodes.LEARN]: nodeLearnFromOutcome,
  };

  const handler = nodeHandlers[state.currentNode];
  if (!handler) {
    return { ...state, success: false, errors: [...state.errors, "Unknown node"] } as WorkflowState;
  }

  const result = await handler(env, state);

  return {
    ...state,
    ...result.state,
    currentNode: result.nextNode,
    errors: result.error ? [...state.errors, result.error] : state.errors,
    success: result.nextNode === WorkflowNodes.END,
  } as WorkflowState;
}

/**
 * Run complete workflow
 */
export async function runWorkflow(
  env: Env,
  initialState: WorkflowState
): Promise<WorkflowState> {
  let state = initialState;
  const maxSteps = 10; // Prevent infinite loops
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
