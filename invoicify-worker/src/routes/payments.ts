/**
 * Payment Scheduling Routes
 *
 * Implements strategic cash management per PRD:
 * - Schedule payments based on due dates and cash position
 * - Consider early payment discounts
 * - Calculate runway impact
 * - Flag overdue payments
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  schedulePayment,
  calculateOptimalPaymentDate,
  getOverduePayments,
  schedulePendingPayments,
  calculateRunway,
  type PaymentInput,
} from "../lib/payment-scheduling";
import { AuditTracer } from "../lib/audit-tracer";
import { eq, sql, and, desc } from "drizzle-orm";
import type { Env } from "../db";

const paymentRoutes = new Hono<{ Bindings: Env }>();

/**
 * Schedule a single payment
 * POST /api/v1/payments/schedule
 */
paymentRoutes.post("/schedule", async (c) => {
  const env = c.env;
  const body = await c.req.json<PaymentInput>();

  if (!body.invoiceId || !body.amount || !body.dueDate || !body.cashBalance || !body.monthlyBurnRate) {
    return c.json({ error: "Missing required fields" }, 400);
  }

  const schedule = await schedulePayment(body);

  // Create payment record if scheduled
  if (schedule.status === "scheduled") {
    const db = getDb(env);
    await db.insert(schema.payments).values({
      id: crypto.randomUUID(),
      invoiceId: body.invoiceId,
      scheduledDate: schedule.scheduledDate,
      amount: schedule.amount,
      status: "scheduled",
      createdAt: new Date().toISOString(),
    });
  }

  return c.json({
    success: true,
    data: schedule,
  });
});

/**
 * Calculate optimal payment date
 * POST /api/v1/payments/optimal-date
 */
paymentRoutes.post("/optimal-date", async (c) => {
  const body = await c.req.json<{
    dueDate: string;
    amount: number;
    cashBalance: number;
    monthlyBurnRate: number;
    earlyDiscountPercent?: number;
  }>();

  if (!body.dueDate || !body.amount || !body.cashBalance || !body.monthlyBurnRate) {
    return c.json({ error: "Missing required fields" }, 400);
  }

  const optimalDate = calculateOptimalPaymentDate(
    body.dueDate,
    body.amount,
    body.cashBalance,
    body.monthlyBurnRate,
    body.earlyDiscountPercent
  );

  return c.json({
    success: true,
    data: {
      optimalDate,
      dueDate: body.dueDate,
      amount: body.amount,
      earlyDiscountPercent: body.earlyDiscountPercent,
    },
  });
});

/**
 * Get overdue payments
 * GET /api/v1/payments/overdue
 */
paymentRoutes.get("/overdue", async (c) => {
  const env = c.env;

  const overduePayments = await getOverduePayments(env);

  const totalOverdue = overduePayments.reduce((sum, p) => sum + p.amount, 0);

  return c.json({
    success: true,
    count: overduePayments.length,
    totalOverdue,
    payments: overduePayments,
  });
});

/**
 * Schedule all pending payments
 * POST /api/v1/payments/schedule-all
 */
paymentRoutes.post("/schedule-all", async (c) => {
  const env = c.env;

  const result = await schedulePendingPayments(env);

  return c.json({
    success: true,
    data: result,
  });
});

/**
 * Calculate cash runway
 * POST /api/v1/payments/runway
 */
paymentRoutes.post("/runway", async (c) => {
  const body = await c.req.json<{
    cashBalance: number;
    monthlyBurnRate: number;
  }>();

  if (!body.cashBalance || !body.monthlyBurnRate) {
    return c.json({ error: "Missing required fields" }, 400);
  }

  const runwayMonths = calculateRunway(body.cashBalance, body.monthlyBurnRate);

  return c.json({
    success: true,
    data: {
      cashBalance: body.cashBalance,
      monthlyBurnRate: body.monthlyBurnRate,
      runwayMonths: Math.round(runwayMonths * 10) / 10,
      runwayCategory:
        runwayMonths >= 12
          ? "healthy"
          : runwayMonths >= 6
            ? "moderate"
            : runwayMonths >= 3
              ? "caution"
              : "critical",
    },
  });
});

/**
 * Get scheduled payments
 * GET /api/v1/payments/scheduled
 */
paymentRoutes.get("/scheduled", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const statusFilter = c.req.query("status");

  let query = db
    .select({
      id: schema.payments.id,
      invoiceId: schema.payments.invoiceId,
      scheduledDate: schema.payments.scheduledDate,
      amount: schema.payments.amount,
      status: schema.payments.status,
      createdAt: schema.payments.createdAt,
    })
    .from(schema.payments)
    .orderBy(schema.payments.scheduledDate);

  if (statusFilter) {
    query = query.where(eq(schema.payments.status, statusFilter)) as any;
  }

  const payments = await query;

  return c.json({
    count: payments.length,
    payments,
  });
});

/**
 * Get payment by invoice ID
 * GET /api/v1/payments/invoice/:invoiceId
 */
paymentRoutes.get("/invoice/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [payment] = await db
    .select({
      id: schema.payments.id,
      invoiceId: schema.payments.invoiceId,
      scheduledDate: schema.payments.scheduledDate,
      amount: schema.payments.amount,
      status: schema.payments.status,
      executedAt: schema.payments.executedAt,
      createdAt: schema.payments.createdAt,
    })
    .from(schema.payments)
    .where(eq(schema.payments.invoiceId, invoiceId))
    .limit(1);

  if (!payment) {
    return c.json({ error: "Payment not found" }, 404);
  }

  // Get invoice details
  const [invoice] = await db
    .select({
      vendorName: schema.invoices.vendorName,
      invoiceNumber: schema.invoices.invoiceNumber,
      dueDate: schema.invoices.dueDate,
      totalAmount: schema.invoices.totalAmount,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  return c.json({
    success: true,
    data: {
      ...payment,
      invoice: invoice,
    },
  });
});

/**
 * Execute a payment
 * POST /api/v1/payments/:paymentId/execute
 */
paymentRoutes.post("/:paymentId/execute", async (c) => {
  const env = c.env;
  const paymentId = c.req.param("paymentId");
  const db = getDb(env);

  const [payment] = await db
    .select()
    .from(schema.payments)
    .where(eq(schema.payments.id, paymentId))
    .limit(1);

  if (!payment) {
    return c.json({ error: "Payment not found" }, 404);
  }

  if (payment.status === "executed") {
    return c.json({ error: "Payment already executed" }, 400);
  }

  // Update payment status
  await db
    .update(schema.payments)
    .set({
      status: "executed",
      executedAt: new Date().toISOString(),
    })
    .where(eq(schema.payments.id, paymentId));

  // Update invoice status
  await db
    .update(schema.invoices)
    .set({
      status: "PAID",
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, payment.invoiceId));

  // Log audit event
  const tracer = new AuditTracer(env);
  await tracer.log({
    eventType: "PAYMENT_EXECUTED" as any,
    entityType: "payment",
    entityId: paymentId,
    action: "executed",
    actor: "system",
    details: {
      invoiceId: payment.invoiceId,
      amount: payment.amount,
      scheduledDate: payment.scheduledDate,
    },
    success: true,
  });

  return c.json({
    success: true,
    message: "Payment executed",
    data: {
      paymentId,
      status: "executed",
    },
  });
});

export { paymentRoutes };
