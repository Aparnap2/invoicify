/**
 * Payment Scheduling Module
 *
 * Implements strategic cash management per PRD:
 * - Schedule payments based on due dates and cash position
 * - Consider early payment discounts
 * - Calculate runway impact
 * - Flag overdue payments
 */

import { getDb, schema } from "../db";
import { eq, sql, and, desc } from "drizzle-orm";
import type { Env } from "../db";

/**
 * Payment status enum
 */
export const PaymentStatus = {
  SCHEDULED: "scheduled",
  EXECUTED: "executed",
  FAILED: "failed",
  DELAYED: "delayed",
  PENDING_FUNDS: "pending_funds",
} as const;

export type PaymentStatusType = (typeof PaymentStatus)[keyof typeof PaymentStatus];

/**
 * Payment scheduling input
 */
export interface PaymentInput {
  invoiceId: string;
  amount: number;
  dueDate: string;
  vendorId: string;
  cashBalance: number;
  monthlyBurnRate: number;
  earlyDiscountPercent?: number;
  earlyDiscountDays?: number;
}

/**
 * Payment scheduling result
 */
export interface PaymentSchedule {
  invoiceId: string;
  scheduledDate: string;
  amount: number;
  status: PaymentStatusType;
  reason: string;
  earlyDiscountPercent?: number;
  discountAmount?: number;
  lateFeeRisk: boolean;
  cashImpactPercent: number;
  runwayImpact: number;
}

/**
 * Schedule payment strategically based on cash position
 */
export async function schedulePayment(input: PaymentInput): Promise<PaymentSchedule> {
  const { invoiceId, amount, dueDate, cashBalance, monthlyBurnRate, earlyDiscountPercent, earlyDiscountDays } = input;

  const due = new Date(dueDate);
  const today = new Date();

  // Calculate cash impact percentage
  const cashImpactPercent = (amount / cashBalance) * 100;

  // Calculate runway impact (months of burn)
  const runwayImpact = amount / monthlyBurnRate;

  // Strategy 1: High cash impact, try to delay
  if (cashImpactPercent > 20 || runwayImpact > 0.3) {
    const optimalDate = new Date(due);
    optimalDate.setDate(optimalDate.getDate() - 5); // Pay 5 days before due

    if (optimalDate < today) {
      return {
        invoiceId,
        scheduledDate: today.toISOString().split("T")[0],
        amount,
        status: PaymentStatus.DELAYED,
        reason: "Payment delayed - cash conservation",
        lateFeeRisk: true,
        cashImpactPercent,
        runwayImpact,
      };
    }

    return {
      invoiceId,
      scheduledDate: optimalDate.toISOString().split("T")[0],
      amount,
      status: PaymentStatus.SCHEDULED,
      reason: "Payment scheduled for cash conservation",
      lateFeeRisk: false,
      cashImpactPercent,
      runwayImpact,
    };
  }

  // Strategy 2: Early payment discount available
  if (earlyDiscountPercent && earlyDiscountPercent > 0) {
    const discountAmount = amount * (earlyDiscountPercent / 100);
    const discountedAmount = amount - discountAmount;

    const earlyDate = new Date(today);
    earlyDate.setDate(earlyDate.getDate() + (earlyDiscountDays || 10));

    if (earlyDate < due && cashBalance >= discountedAmount) {
      return {
        invoiceId,
        scheduledDate: earlyDate.toISOString().split("T")[0],
        amount: discountedAmount,
        status: PaymentStatus.SCHEDULED,
        reason: `Early payment - save $${discountAmount.toFixed(2)} (${earlyDiscountPercent}% discount)`,
        earlyDiscountPercent,
        discountAmount,
        lateFeeRisk: false,
        cashImpactPercent: (discountedAmount / cashBalance) * 100,
        runwayImpact: discountedAmount / monthlyBurnRate,
      };
    }
  }

  // Strategy 3: Normal case - pay 7 days before due
  const normalDate = new Date(due);
  normalDate.setDate(normalDate.getDate() - 7);

  if (normalDate < today) {
    normalDate.setTime(today.getTime());
  }

  // Check for late fee risk
  const lateFeeRisk = normalDate > new Date(due.getTime() - 3 * 24 * 60 * 60 * 1000);

  return {
    invoiceId,
    scheduledDate: normalDate.toISOString().split("T")[0],
    amount,
    status: PaymentStatus.SCHEDULED,
    reason: "Normal processing",
    lateFeeRisk,
    cashImpactPercent,
    runwayImpact,
  };
}

/**
 * Calculate optimal payment date considering all factors
 */
export function calculateOptimalPaymentDate(
  dueDate: string,
  amount: number,
  cashBalance: number,
  monthlyBurnRate: number,
  earlyDiscountPercent?: number
): string {
  const due = new Date(dueDate);
  const today = new Date();

  // If early discount available, check if beneficial
  if (earlyDiscountPercent && earlyDiscountPercent > 0) {
    const discountAmount = amount * (earlyDiscountPercent / 100);
    const dailyInterestRate = 0.0001; // Assume 0.01% daily opportunity cost

    const daysEarly = Math.floor((due.getTime() - today.getTime()) / (24 * 60 * 60 * 1000));
    const costOfEarlyPayment = discountAmount - (amount * dailyInterestRate * daysEarly);

    if (costOfEarlyPayment > 0) {
      // Early payment is beneficial
      const earlyDate = new Date(today);
      earlyDate.setDate(earlyDate.getDate() + 10); // Assume 10 days early for 2/10 net 30
      return earlyDate < due ? earlyDate.toISOString().split("T")[0] : due.toISOString().split("T")[0];
    }
  }

  // Default: pay 7 days before due
  const optimalDate = new Date(due);
  optimalDate.setDate(optimalDate.getDate() - 7);

  if (optimalDate < today) {
    return today.toISOString().split("T")[0];
  }

  return optimalDate.toISOString().split("T")[0];
}

/**
 * Get overdue payments
 */
export async function getOverduePayments(env: Env): Promise<PaymentSchedule[]> {
  const db = getDb(env);
  const today = new Date().toISOString().split("T")[0];

  const invoices = await db
    .select({
      id: schema.invoices.id,
      vendorName: schema.invoices.vendorName,
      totalAmount: schema.invoices.totalAmount,
      dueDate: schema.invoices.dueDate,
      riskLevel: schema.invoices.riskLevel,
    })
    .from(schema.invoices)
    .where(
      and(
        sql`${schema.invoices.dueDate} < '${today}'`,
        sql`${schema.invoices.status} IN ('PENDING', 'VALIDATED', 'APPROVED')`
      )
    )
    .orderBy(schema.invoices.dueDate);

  return invoices.map((inv) => ({
    invoiceId: inv.id,
    scheduledDate: today,
    amount: inv.totalAmount,
    status: PaymentStatus.DELAYED as PaymentStatusType,
    reason: "Overdue payment",
    lateFeeRisk: true,
    cashImpactPercent: 0,
    runwayImpact: 0,
  }));
}

/**
 * Schedule all pending invoices
 */
export async function schedulePendingPayments(env: Env): Promise<{
  scheduled: number;
  delayed: number;
  pendingFunds: number;
}> {
  const db = getDb(env);
  const result = { scheduled: 0, delayed: 0, pendingFunds: 0 };

  // Get pending invoices
  const pendingInvoices = await db
    .select()
    .from(schema.invoices)
    .where(
      sql`${schema.invoices.status} IN ('PENDING', 'VALIDATED', 'APPROVED')`
    );

  for (const invoice of pendingInvoices) {
    // Get company defaults (would come from settings in real implementation)
    const cashBalance = 100000; // Default
    const monthlyBurnRate = 20000; // Default

    const schedule = await schedulePayment({
      invoiceId: invoice.id,
      amount: invoice.totalAmount,
      dueDate: invoice.dueDate || new Date().toISOString().split("T")[0],
      vendorId: invoice.vendorId || "",
      cashBalance,
      monthlyBurnRate,
    });

    // Create payment record
    await db.insert(schema.payments).values({
      id: crypto.randomUUID(),
      invoiceId: invoice.id,
      scheduledDate: schedule.scheduledDate,
      status: schedule.status,
      amount: schedule.amount,
      createdAt: new Date().toISOString(),
    });

    // Update invoice status
    await db
      .update(schema.invoices)
      .set({
        status: "PENDING",
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.invoices.id, invoice.id));

    // Count by status
    if (schedule.status === PaymentStatus.SCHEDULED) result.scheduled++;
    else if (schedule.status === PaymentStatus.DELAYED) result.delayed++;
    else if (schedule.status === PaymentStatus.PENDING_FUNDS) result.pendingFunds++;
  }

  return result;
}

/**
 * Calculate cash runway
 */
export function calculateRunway(cashBalance: number, monthlyBurnRate: number): number {
  if (monthlyBurnRate <= 0) return 99; // Infinite runway
  return cashBalance / monthlyBurnRate;
}
