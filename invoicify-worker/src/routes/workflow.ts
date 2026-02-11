/**
 * Workflow Execution Routes
 *
 * Implements PRD Section 7 workflow:
 * START → Ingest → Extract → Context → Risk → (AutoApprove|HITL|Escalate) → Ledger → Learn → END
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  WorkflowState,
  createInitialState,
  WorkflowNodes,
  executeWorkflowStep,
  runWorkflow,
  nodeIngestInvoice,
  nodeExtractFields,
  nodeFetchContext,
  nodeAssessRisk,
  nodeAutoApprove,
  nodeHumanReview,
  nodePostLedger,
} from "../lib/workflow";
import { AuditTracer, getInvoiceAuditTrail } from "../lib/audit-tracer";
import { eq, sql } from "drizzle-orm";
import type { Env } from "../db";

const workflowRoutes = new Hono<{ Bindings: Env }>();

/**
 * Start a new invoice processing workflow
 * POST /api/v1/workflow/start
 */
workflowRoutes.post("/start", async (c) => {
  const env = c.env;
  const body = await c.req.json<{
    vendorName: string;
    invoiceNumber?: string;
    amount: number;
    currency?: string;
    dueDate?: string;
    issueDate?: string;
    rawText?: string;
    vendorId?: string;
  }>();

  if (!body.vendorName || !body.amount) {
    return c.json({ error: "Missing required fields: vendorName, amount" }, 400);
  }

  const initialState = createInitialState({
    vendorName: body.vendorName,
    invoiceNumber: body.invoiceNumber,
    amount: body.amount,
    currency: body.currency || "USD",
    dueDate: body.dueDate,
    issueDate: body.issueDate,
    rawText: body.rawText,
    vendorId: body.vendorId,
  });

  // Run the complete workflow
  const result = await runWorkflow(env, initialState);

  // Log start event
  const tracer = new AuditTracer(env, result.traceId || undefined);
  await tracer.logInvoiceReceived(result.invoiceId || "", body.vendorName, body.amount);

  return c.json({
    success: result.success,
    traceId: result.traceId,
    invoiceId: result.invoiceId,
    currentNode: result.currentNode,
    action: result.action,
    riskScore: result.riskScore,
    riskLevel: result.riskLevel,
    riskSignals: result.riskSignals,
    markdownOutput: result.markdownOutput,
    errors: result.errors,
    workflowComplete: result.currentNode === WorkflowNodes.END,
  });
});

/**
 * Execute a single workflow step
 * POST /api/v1/workflow/step/:invoiceId
 */
workflowRoutes.post("/step/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const body = await c.req.json<{
    targetNode: string;
    parsedData?: Record<string, any>;
  }>();

  const db = getDb(env);

  // Get current invoice state
  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Build workflow state from invoice
  let currentState: WorkflowState = createInitialState({
    invoiceId,
    vendorId: invoice.vendorId || undefined,
    vendorName: invoice.vendorName,
    invoiceNumber: invoice.invoiceNumber,
    amount: invoice.totalAmount,
    currency: invoice.currency,
    dueDate: invoice.dueDate || undefined,
    issueDate: invoice.invoiceDate || undefined,
    rawText: invoice.rawContent || undefined,
  });

  // Execute specific node based on targetNode
  let result;
  switch (body.targetNode) {
    case "ingest_invoice":
      result = await nodeIngestInvoice(env, currentState);
      break;
    case "extract_fields":
      currentState = { ...currentState, parsedData: body.parsedData || {} };
      result = await nodeExtractFields(env, currentState);
      break;
    case "fetch_context":
      result = await nodeFetchContext(env, currentState);
      break;
    case "assess_risk":
      result = await nodeAssessRisk(env, currentState);
      break;
    case "auto_approve":
      result = await nodeAutoApprove(env, currentState);
      break;
    case "human_review":
      result = await nodeHumanReview(env, currentState);
      break;
    case "post_to_ledger":
      result = await nodePostLedger(env, currentState);
      break;
    default:
      return c.json({ error: `Unknown target node: ${body.targetNode}` }, 400);
  }

  // Log audit event
  const tracer = new AuditTracer(env);
  await tracer.log({
    eventType: "SYSTEM_ACTION" as any,
    entityType: "invoice",
    entityId: invoiceId,
    action: body.targetNode,
    actor: "agent",
    details: {
      targetNode: body.targetNode,
      result: result.state,
    },
    riskScore: result.state.riskScore || undefined,
    success: !result.error,
    errorMessage: result.error,
  });

  return c.json({
    success: !result.error,
    nextNode: result.nextNode,
    interrupt: result.interrupt,
    state: result.state,
    error: result.error,
  });
});

/**
 * Continue workflow after HITL approval
 * POST /api/v1/workflow/:invoiceId/approve
 */
workflowRoutes.post("/:invoiceId/approve", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const body = await c.req.json<{
    decision: "approved" | "rejected";
    approver: string;
    reason?: string;
  }>();

  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Build state from invoice
  let state = createInitialState({
    invoiceId,
    vendorId: invoice.vendorId || undefined,
    vendorName: invoice.vendorName,
    invoiceNumber: invoice.invoiceNumber,
    amount: invoice.totalAmount,
    currency: invoice.currency,
    dueDate: invoice.dueDate || undefined,
    riskScore: invoice.riskScore || undefined,
    riskLevel: invoice.riskLevel || undefined,
  });

  // Execute approval based on decision
  let result;
  if (body.decision === "approved") {
    // Update invoice status
    await db
      .update(schema.invoices)
      .set({
        status: "APPROVED",
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.invoices.id, invoiceId));

    result = await nodeAutoApprove(env, state);

    // Log approval
    const tracer = new AuditTracer(env);
    await tracer.logApprovalDecision(invoiceId, "approved", body.approver, invoice.riskScore || 0, body.reason);
  } else {
    // Rejected - don't proceed to ledger
    await db
      .update(schema.invoices)
      .set({
        status: "REJECTED",
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.invoices.id, invoiceId));

    const tracer = new AuditTracer(env);
    await tracer.logApprovalDecision(invoiceId, "rejected", body.approver, invoice.riskScore || 0, body.reason);

    return c.json({
      success: true,
      decision: "rejected",
      message: "Invoice rejected",
      invoiceId,
    });
  }

  // Continue to ledger
  state = { ...state, ...result.state };
  const ledgerResult = await nodePostLedger(env, state);

  return c.json({
    success: true,
    decision: body.decision,
    invoiceId,
    currentNode: ledgerResult.nextNode,
    ledgerPosted: ledgerResult.state.ledgerPosted,
    markdownOutput: ledgerResult.state.markdownOutput,
  });
});

/**
 * Get workflow status for an invoice
 * GET /api/v1/workflow/:invoiceId/status
 */
workflowRoutes.get("/:invoiceId/status", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
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
      updatedAt: schema.invoices.updatedAt,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Map status to workflow node
  const nodeMap: Record<string, string> = {
    NEW: "ingest_invoice",
    EXTRACTED: "extract_fields",
    VALIDATED: "fetch_context",
    ASSESSED: "assess_risk",
    PENDING: "human_review",
    APPROVED: "auto_approve",
    PAID: "post_to_ledger",
    REJECTED: "END",
  };

  return c.json({
    success: true,
    invoiceId,
    currentNode: invoice.status ? (nodeMap[invoice.status] || "UNKNOWN") : "UNKNOWN",
    status: invoice.status,
    riskScore: invoice.riskScore,
    riskLevel: invoice.riskLevel,
    invoice: {
      vendorName: invoice.vendorName,
      invoiceNumber: invoice.invoiceNumber,
      amount: invoice.totalAmount,
      currency: invoice.currency,
      dueDate: invoice.dueDate,
      createdAt: invoice.createdAt,
      updatedAt: invoice.updatedAt,
    },
  });
});

/**
 * Get workflow audit trail
 * GET /api/v1/workflow/:invoiceId/audit
 */
workflowRoutes.get("/:invoiceId/audit", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const auditTrail = await getInvoiceAuditTrail(env, invoiceId);

  return c.json({
    success: true,
    invoiceId,
    ...auditTrail,
  });
});

export { workflowRoutes };
