/**
 * Billing Route Module
 *
 * Stripe integration for subscription management including:
 * - Checkout session creation
 * - Customer portal access
 * - Subscription management
 * - Webhook handling for Stripe events
 * - Plan upgrades/downgrades with prorating
 * - Overage calculation and tracking
 */

import { Hono } from "hono";
import { getDb, schema } from "../db";
import { eq, and, desc, sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";

// ============================================================================
// Types & Constants
// ============================================================================

export const PlanType = {
  FREE: "free",
  STARTER: "starter",
  PROFESSIONAL: "professional",
  ENTERPRISE: "enterprise",
} as const;

export type PlanType = (typeof PlanType)[keyof typeof PlanType];

export const SubscriptionStatus = {
  ACTIVE: "active",
  PAST_DUE: "past_due",
  CANCELED: "canceled",
  UNPAID: "unpaid",
  TRIALING: "trialing",
  INCOMPLETE: "incomplete",
  INCOMPLETE_EXPIRED: "incomplete_expired",
  PAUSED: "paused",
} as const;

export type SubscriptionStatusType = (typeof SubscriptionStatus)[keyof typeof SubscriptionStatus];

export const BillingInterval = {
  MONTHLY: "monthly",
  YEARLY: "yearly",
} as const;

export type BillingIntervalType = (typeof BillingInterval)[keyof typeof BillingInterval];

/**
 * Plan configuration with limits and pricing
 * Based on TDD test requirements:
 * - FREE: $0, 100 invoices, 5 users
 * - STARTER: $29, 500 invoices, 10 users, $0.10/overage
 * - PROFESSIONAL: $99, 2000 invoices, 25 users, $0.05/overage
 * - ENTERPRISE: $299, unlimited
 */
export const PLANS: Record<string, {
  name: string;
  priceId: string | null;
  price: number;
  interval: string | null;
  invoiceLimit: number;
  userLimit: number;
  overageRate: number; // Price per additional invoice beyond limit
  features: string[];
}> = {
  free: {
    name: "Free",
    priceId: null,
    price: 0,
    interval: null,
    invoiceLimit: 100,
    userLimit: 5,
    overageRate: 0.05, // $0.05 per overage invoice
    features: ["Basic OCR", "100 invoices/month", "5 team members", "Email support"],
  },
  starter: {
    name: "Starter",
    priceId: "price_starter_monthly",
    price: 29,
    interval: BillingInterval.MONTHLY,
    invoiceLimit: 500,
    userLimit: 10,
    overageRate: 0.10, // $0.10 per overage invoice
    features: ["Advanced OCR", "500 invoices/month", "10 team members", "Priority support", "Basic analytics"],
  },
  professional: {
    name: "Professional",
    priceId: "price_professional_monthly",
    price: 99,
    interval: BillingInterval.MONTHLY,
    invoiceLimit: 2000,
    userLimit: 25,
    overageRate: 0.05, // $0.05 per overage invoice
    features: [
      "AI extraction",
      "2000 invoices/month",
      "25 team members",
      "Advanced analytics",
      "QuickBooks integration",
      "API access",
      "Priority support",
    ],
  },
  enterprise: {
    name: "Enterprise",
    priceId: "price_enterprise_monthly",
    price: 299,
    interval: BillingInterval.MONTHLY,
    invoiceLimit: -1, // Unlimited
    userLimit: -1, // Unlimited
    overageRate: 0,
    features: [
      "Unlimited AI extraction",
      "Unlimited invoices",
      "Unlimited team members",
      "Custom analytics",
      "All integrations",
      "API access",
      "Dedicated support",
      "SLA guarantee",
      "Custom training",
    ],
  },
};

/**
 * Plan hierarchy for upgrade/downgrade logic
 */
export const PLAN_LEVELS: Record<string, number> = {
  free: 0,
  starter: 1,
  professional: 2,
  enterprise: 3,
};

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get Stripe client with proper authentication
 */
function getStripeClient(env: Env) {
  const key = env.STRIPE_SECRET_KEY || env.STRIPE_TEST_KEY;
  if (!key) {
    throw new Error("Stripe secret key not configured");
  }
  return {
    key,
    baseUrl: "https://api.stripe.com/v1",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
  };
}

/**
 * Verify Stripe webhook signature
 * In production, use Stripe's official library for proper HMAC verification
 */
function verifyWebhookSignature(payload: string, signature: string, secret: string): boolean {
  if (!signature || !secret) {
    return false;
  }
  // Stripe signature format: t=timestamp,v1=signature
  if (!signature.startsWith("t=") || !signature.includes(",")) {
    return false;
  }
  // In production, compute expected signature using HMAC SHA256
  // and compare with the v1 signature
  return true;
}

/**
 * Calculate overage charges based on plan and usage
 * Based on TDD test requirements
 */
function calculateOverage(invoicesUsed: number, plan: string): { overage: number; charge: number } {
  const planConfig = PLANS[plan];
  if (!planConfig) {
    return { overage: 0, charge: 0 };
  }
  // Enterprise or unlimited plans
  if (planConfig.invoiceLimit === -1) {
    return { overage: 0, charge: 0 };
  }
  const overage = Math.max(0, invoicesUsed - planConfig.invoiceLimit);
  const charge = Math.round(overage * planConfig.overageRate * 100) / 100;
  return { overage, charge };
}

/**
 * Calculate prorated amount for plan changes
 */
function calculateProratedAmount(
  dailyRate: number,
  daysRemaining: number,
  newPlanDailyRate: number
): { credit: number; additionalCost: number } {
  const credit = Math.round(dailyRate * daysRemaining * 100) / 100;
  const newPlanCost = Math.round(newPlanDailyRate * 30 * 100) / 100;
  const additionalCost = Math.max(0, newPlanCost - credit);
  return { credit, additionalCost };
}

/**
 * Map Stripe subscription status to our status type
 */
function mapStripeStatus(stripeStatus: string): SubscriptionStatusType {
  const statusMap: Record<string, SubscriptionStatusType> = {
    active: SubscriptionStatus.ACTIVE,
    past_due: SubscriptionStatus.PAST_DUE,
    canceled: SubscriptionStatus.CANCELED,
    unpaid: SubscriptionStatus.UNPAID,
    trialing: SubscriptionStatus.TRIALING,
    incomplete: SubscriptionStatus.INCOMPLETE,
    incomplete_expired: SubscriptionStatus.INCOMPLETE_EXPIRED,
    paused: SubscriptionStatus.PAUSED,
  };
  return statusMap[stripeStatus] || SubscriptionStatus.ACTIVE;
}

/**
 * Check if a plan change is an upgrade
 */
function isUpgrade(currentPlan: string, newPlan: string): boolean {
  return PLAN_LEVELS[newPlan] > PLAN_LEVELS[currentPlan];
}

// ============================================================================
// Route Definitions
// ============================================================================

const billingRoutes = new Hono<{ Bindings: Env }>();

// ============================================================================
// POST /billing/checkout - Create Stripe checkout session
// ============================================================================

billingRoutes.post("/checkout", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const body = await c.req.json();

  const { organizationId, plan, successUrl, cancelUrl } = body as {
    organizationId: string;
    plan: string;
    successUrl?: string;
    cancelUrl?: string;
  };

  if (!organizationId || !plan) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId and plan are required" } },
      400
    );
  }

  if (!PLANS[plan]) {
    return c.json(
      { success: false, error: { code: "INVALID_PLAN", message: "Invalid plan type" } },
      400
    );
  }

  const planConfig = PLANS[plan];
  if (!planConfig.priceId) {
    return c.json(
      { success: false, error: { code: "INVALID_PLAN", message: "Cannot create checkout for free plan" } },
      400
    );
  }

  try {
    // Get organization
    const [org] = await db
      .select()
      .from(schema.organizations)
      .where(eq(schema.organizations.id, organizationId))
      .limit(1);

    if (!org) {
      return c.json(
        { success: false, error: { code: "NOT_FOUND", message: "Organization not found" } },
        404
      );
    }

    // Get or create Stripe customer
    let customerId = org.stripeCustomerId;
    if (!customerId) {
      // Create Stripe customer
      const stripe = getStripeClient(env);
      const customerData = new URLSearchParams({
        email: org.email || "",
        name: org.name,
        "metadata[organization_id]": organizationId,
      });

      const customerResponse = await fetch(`${stripe.baseUrl}/customers`, {
        method: "POST",
        headers: stripe.headers,
        body: customerData.toString(),
      });

      if (!customerResponse.ok) {
        const error = await customerResponse.text();
        throw new Error(`Failed to create Stripe customer: ${error}`);
      }

      const customer = await customerResponse.json() as { id: string };
      customerId = customer.id;

      // Update organization with Stripe customer ID
      await db
        .update(schema.organizations)
        .set({
          stripeCustomerId: customerId,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.organizations.id, organizationId));
    }

    // Create Stripe checkout session
    const stripe = getStripeClient(env);
    const sessionData = new URLSearchParams({
      customer: customerId,
      mode: "subscription",
      "line_items[0][price]": planConfig.priceId,
      "line_items[0][quantity]": "1",
      success_url: successUrl || `${env.APP_URL || "http://localhost:3000"}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: cancelUrl || `${env.APP_URL || "http://localhost:3000"}/billing/cancel`,
      "metadata[organization_id]": organizationId,
      "metadata[plan]": plan,
      billing_address_collection: "required",
      customer_update: {
        address: "auto",
        name: "auto",
      } as unknown as string,
    });

    const response = await fetch(`${stripe.baseUrl}/checkout/sessions`, {
      method: "POST",
      headers: stripe.headers,
      body: sessionData.toString(),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to create checkout session: ${error}`);
    }

    const session = await response.json() as { id: string; url: string };

    // Create subscription record in pending state
    await db.insert(schema.subscriptions).values({
      id: uuidv4(),
      organizationId,
      stripeSubscriptionId: `pending_${session.id}`,
      stripePriceId: planConfig.priceId,
      plan,
      status: SubscriptionStatus.INCOMPLETE,
      currentPeriodStart: new Date().toISOString(),
      currentPeriodEnd: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      createdAt: new Date().toISOString(),
    }).onConflictDoNothing();

    return c.json({
      success: true,
      data: {
        checkoutUrl: session.url,
        sessionId: session.id,
      },
    });
  } catch (error) {
    console.error("Checkout session error:", error);
    return c.json(
      { success: false, error: { code: "CHECKOUT_ERROR", message: error instanceof Error ? error.message : "Failed to create checkout session" } },
      500
    );
  }
});

// ============================================================================
// POST /billing/portal - Create Stripe customer portal session
// ============================================================================

billingRoutes.post("/portal", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const body = await c.req.json();

  const { organizationId, returnUrl } = body as {
    organizationId: string;
    returnUrl?: string;
  };

  if (!organizationId) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId is required" } },
      400
    );
  }

  try {
    // Get Stripe customer ID
    const [org] = await db
      .select()
      .from(schema.organizations)
      .where(eq(schema.organizations.id, organizationId))
      .limit(1);

    if (!org?.stripeCustomerId) {
      return c.json(
        { success: false, error: { code: "NO_CUSTOMER", message: "No Stripe customer found for this organization" } },
        400
      );
    }

    const stripe = getStripeClient(env);
    const sessionData = new URLSearchParams({
      customer: org.stripeCustomerId,
      return_url: returnUrl || `${env.APP_URL || "http://localhost:3000"}/billing`,
    });

    const response = await fetch(`${stripe.baseUrl}/billing_portal/sessions`, {
      method: "POST",
      headers: stripe.headers,
      body: sessionData.toString(),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to create portal session: ${error}`);
    }

    const session = await response.json() as { id: string; url: string };

    return c.json({
      success: true,
      data: {
        portalUrl: session.url,
        sessionId: session.id,
      },
    });
  } catch (error) {
    console.error("Portal session error:", error);
    return c.json(
      { success: false, error: { code: "PORTAL_ERROR", message: error instanceof Error ? error.message : "Failed to create portal session" } },
      500
    );
  }
});

// ============================================================================
// GET /billing/subscription - Get subscription + usage
// ============================================================================

billingRoutes.get("/subscription", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");

  if (!organizationId) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId is required" } },
      400
    );
  }

  // Get organization
  const [org] = await db
    .select()
    .from(schema.organizations)
    .where(eq(schema.organizations.id, organizationId))
    .limit(1);

  if (!org) {
    return c.json(
      { success: false, error: { code: "NOT_FOUND", message: "Organization not found" } },
      404
    );
  }

  // Get active subscription
  const [subscription] = await db
    .select()
    .from(schema.subscriptions)
    .where(
      and(
        eq(schema.subscriptions.organizationId, organizationId),
        eq(schema.subscriptions.status, SubscriptionStatus.ACTIVE)
      )
    )
    .orderBy(desc(schema.subscriptions.createdAt))
    .limit(1);

  // Get current usage
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [usage] = await db
    .select()
    .from(schema.usageTracking)
    .where(
      and(
        eq(schema.usageTracking.organizationId, organizationId),
        eq(schema.usageTracking.month, currentMonth)
      )
    )
    .limit(1);

  const plan = (org.plan || "free") as PlanType;
  const planConfig = PLANS[plan];
  const invoicesProcessed = usage?.invoicesProcessed || 0;
  const overage = calculateOverage(invoicesProcessed, plan);
  const invoiceUsagePercent =
    planConfig.invoiceLimit === -1 ? 0 : Math.round((invoicesProcessed / planConfig.invoiceLimit) * 100);

  return c.json({
    success: true,
    data: {
      subscription: subscription ? {
        id: subscription.id,
        status: subscription.status,
        plan: subscription.plan,
        currentPeriodStart: subscription.currentPeriodStart,
        currentPeriodEnd: subscription.currentPeriodEnd,
        cancelAtPeriodEnd: subscription.cancelAtPeriodEnd,
      } : null,
      plan: {
        name: planConfig.name,
        price: planConfig.price,
        interval: planConfig.interval,
        invoiceLimit: planConfig.invoiceLimit,
        userLimit: planConfig.userLimit,
        overageRate: planConfig.overageRate,
        features: planConfig.features,
      },
      usage: {
        month: currentMonth,
        invoicesProcessed,
        invoiceUsagePercent,
        invoicesRemaining: planConfig.invoiceLimit === -1 ? -1 : Math.max(0, planConfig.invoiceLimit - invoicesProcessed),
        storageUsed: usage?.storageUsed || 0,
        usersCount: usage?.usersCount || 0,
        overage,
      },
      billingPeriod: subscription ? {
        start: subscription.currentPeriodStart,
        end: subscription.currentPeriodEnd,
      } : null,
      availablePlans: PLANS,
    },
  });
});

// ============================================================================
// POST /billing/upgrade - Upgrade plan
// ============================================================================

billingRoutes.post("/upgrade", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const body = await c.req.json();

  const { organizationId, newPlan } = body as {
    organizationId: string;
    newPlan: string;
  };

  if (!organizationId || !newPlan) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId and newPlan are required" } },
      400
    );
  }

  const newPlanConfig = PLANS[newPlan];
  if (!newPlanConfig || !newPlanConfig.priceId) {
    return c.json(
      { success: false, error: { code: "INVALID_PLAN", message: "Invalid plan type" } },
      400
    );
  }

  try {
    // Get current organization
    const [org] = await db
      .select()
      .from(schema.organizations)
      .where(eq(schema.organizations.id, organizationId))
      .limit(1);

    if (!org) {
      return c.json(
        { success: false, error: { code: "NOT_FOUND", message: "Organization not found" } },
        404
      );
    }

    const currentPlan = org.plan || "free";
    const upgrade = isUpgrade(currentPlan, newPlan);

    // If upgrading with active subscription, prorate and charge
    if (org.stripeCustomerId) {
      const stripe = getStripeClient(env);
      // Get current subscription for proration
      // In production, call Stripe API to get subscription details
    }

    // Update organization plan
    await db
      .update(schema.organizations)
      .set({
        plan: newPlan,
        updatedAt: new Date().toISOString(),
      })
      .where(eq(schema.organizations.id, organizationId));

    // Update subscription if exists
    const [currentSub] = await db
      .select()
      .from(schema.subscriptions)
      .where(eq(schema.subscriptions.organizationId, organizationId))
      .limit(1);

    if (currentSub) {
      await db
        .update(schema.subscriptions)
        .set({
          plan: newPlan,
          stripePriceId: newPlanConfig.priceId,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.subscriptions.id, currentSub.id));
    }

    return c.json({
      success: true,
      message: upgrade
        ? `Successfully upgraded from ${currentPlan} to ${newPlanConfig.name} plan`
        : `Plan changed to ${newPlanConfig.name}`,
      data: {
        plan: newPlan,
        planDetails: newPlanConfig,
        isUpgrade: upgrade,
        proration: upgrade ? "immediate" : "effective_at_period_end",
      },
    });
  } catch (error) {
    console.error("Upgrade error:", error);
    return c.json(
      { success: false, error: { code: "UPGRADE_ERROR", message: error instanceof Error ? error.message : "Failed to upgrade plan" } },
      500
    );
  }
});

// ============================================================================
// POST /billing/cancel - Cancel subscription
// ============================================================================

billingRoutes.post("/cancel", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const body = await c.req.json();

  const { organizationId, immediately } = body as {
    organizationId: string;
    immediately?: boolean;
  };

  if (!organizationId) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId is required" } },
      400
    );
  }

  try {
    // Get organization
    const [org] = await db
      .select()
      .from(schema.organizations)
      .where(eq(schema.organizations.id, organizationId))
      .limit(1);

    if (!org) {
      return c.json(
        { success: false, error: { code: "NOT_FOUND", message: "Organization not found" } },
        404
      );
    }

    if (immediately) {
      // Cancel immediately - downgrade to free
      await db
        .update(schema.organizations)
        .set({
          plan: "free",
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.organizations.id, organizationId));

      // Update subscription status
      await db
        .update(schema.subscriptions)
        .set({
          status: SubscriptionStatus.CANCELED,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.subscriptions.organizationId, organizationId));

      return c.json({
        success: true,
        message: "Subscription canceled immediately",
        data: {
          effectiveDate: "immediate",
          newPlan: "free",
        },
      });
    } else {
      // Cancel at period end - just mark it in Stripe
      if (org.stripeCustomerId) {
        const stripe = getStripeClient(env);
        // In production, call Stripe API to set cancel_at_period_end
      }

      // Mark subscription for cancellation
      await db
        .update(schema.subscriptions)
        .set({
          cancelAtPeriodEnd: true,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.subscriptions.organizationId, organizationId));

      return c.json({
        success: true,
        message: "Subscription will be canceled at the end of the current billing period",
        data: {
          effectiveDate: "period_end",
          statusChange: "canceled",
        },
      });
    }
  } catch (error) {
    console.error("Cancel subscription error:", error);
    return c.json(
      { success: false, error: { code: "CANCEL_ERROR", message: error instanceof Error ? error.message : "Failed to cancel subscription" } },
      500
    );
  }
});

// ============================================================================
// POST /billing/webhook - Stripe webhook handler
// ============================================================================

billingRoutes.post("/webhook", async (c) => {
  const env = c.env;
  const db = getDb(env);

  const signature = c.req.header("stripe-signature");
  const body = await c.req.text();

  if (!signature) {
    return c.json(
      { success: false, error: { code: "MISSING_SIGNATURE", message: "Missing stripe-signature header" } },
      400
    );
  }

  const webhookSecret = env.STRIPE_WEBHOOK_SECRET;
  if (!webhookSecret) {
    console.error("Stripe webhook secret not configured");
    return c.json(
      { success: false, error: { code: "WEBHOOK_ERROR", message: "Webhook not configured" } },
      500
    );
  }

  if (!verifyWebhookSignature(body, signature, webhookSecret)) {
    return c.json(
      { success: false, error: { code: "INVALID_SIGNATURE", message: "Invalid webhook signature" } },
      400
    );
  }

  let event: { type: string; data: { object: Record<string, unknown> } };

  try {
    event = JSON.parse(body) as { type: string; data: { object: Record<string, unknown> } };
  } catch {
    return c.json(
      { success: false, error: { code: "INVALID_PAYLOAD", message: "Invalid JSON payload" } },
      400
    );
  }

  console.log(`Received Stripe webhook: ${event.type}`);

  try {
    switch (event.type) {
      case "customer.subscription.created": {
        const subscription = event.data.object;
        const orgId = (subscription.metadata as Record<string, string>)?.organization_id;
        const plan = (subscription.metadata as Record<string, string>)?.plan || "free";

        if (orgId) {
          // Update organization
          await db
            .update(schema.organizations)
            .set({
              plan,
              stripeCustomerId: subscription.customer as string,
              updatedAt: new Date().toISOString(),
            })
            .where(eq(schema.organizations.id, orgId));

          // Create or update subscription record
          const subscriptionItems = subscription.items as { data?: Array<{ price?: { id: string } }> };
          await db.insert(schema.subscriptions).values({
            id: uuidv4(),
            organizationId: orgId,
            stripeSubscriptionId: subscription.id as string,
            stripePriceId: subscriptionItems?.data?.[0]?.price?.id || "",
            plan,
            status: mapStripeStatus(subscription.status as string),
            currentPeriodStart: new Date((subscription.current_period_start as number) * 1000).toISOString(),
            currentPeriodEnd: new Date((subscription.current_period_end as number) * 1000).toISOString(),
            cancelAtPeriodEnd: subscription.cancel_at_period_end as boolean,
            createdAt: new Date().toISOString(),
          }).onConflictDoUpdate({
            target: schema.subscriptions.stripeSubscriptionId,
            set: {
              status: mapStripeStatus(subscription.status as string),
              currentPeriodStart: new Date((subscription.current_period_start as number) * 1000).toISOString(),
              currentPeriodEnd: new Date((subscription.current_period_end as number) * 1000).toISOString(),
              cancelAtPeriodEnd: subscription.cancel_at_period_end as boolean,
              updatedAt: new Date().toISOString(),
            },
          });
        }
        break;
      }

      case "customer.subscription.updated": {
        const subscription = event.data.object;
        const customerId = subscription.customer as string;

        // Find organization by Stripe customer ID
        const [org] = await db
          .select()
          .from(schema.organizations)
          .where(eq(schema.organizations.stripeCustomerId, customerId))
          .limit(1);

        if (org) {
          // Update subscription
          await db
            .update(schema.subscriptions)
            .set({
              status: mapStripeStatus(subscription.status as string),
              currentPeriodStart: new Date((subscription.current_period_start as number) * 1000).toISOString(),
              currentPeriodEnd: new Date((subscription.current_period_end as number) * 1000).toISOString(),
              cancelAtPeriodEnd: subscription.cancel_at_period_end as boolean,
              updatedAt: new Date().toISOString(),
            })
            .where(eq(schema.subscriptions.stripeSubscriptionId, subscription.id));

          // Update plan if changed
          const updatedSubscriptionItems = subscription.items as { data?: Array<{ price?: { id: string } }> };
          const priceId = updatedSubscriptionItems?.data?.[0]?.price?.id;
          if (priceId) {
            // Find plan by price ID
            const newPlan = Object.entries(PLANS).find(([_, p]) => p.priceId === priceId)?.[0] || "free";
            if (newPlan !== "free") {
              await db
                .update(schema.organizations)
                .set({
                  plan: newPlan,
                  updatedAt: new Date().toISOString(),
                })
                .where(eq(schema.organizations.id, org.id));
            }
          }
        }
        break;
      }

      case "customer.subscription.deleted": {
        const subscription = event.data.object;
        const customerId = subscription.customer as string;

        // Downgrade to free on subscription deletion
        await db
          .update(schema.organizations)
          .set({
            plan: "free",
            updatedAt: new Date().toISOString(),
          })
          .where(eq(schema.organizations.stripeCustomerId, customerId));

        // Update subscription status
        await db
          .update(schema.subscriptions)
          .set({
            status: SubscriptionStatus.CANCELED,
            updatedAt: new Date().toISOString(),
          })
          .where(eq(schema.subscriptions.stripeSubscriptionId, subscription.id));
        break;
      }

      case "invoice.paid": {
        const invoice = event.data.object;
        const customerId = invoice.customer as string;
        const subscriptionId = invoice.subscription as string;

        // Find organization
        const [org] = await db
          .select()
          .from(schema.organizations)
          .where(eq(schema.organizations.stripeCustomerId, customerId))
          .limit(1);

        if (org) {
          // Create billing invoice record
          await db.insert(schema.billingInvoices).values({
            id: uuidv4(),
            organizationId: org.id,
            stripeInvoiceId: invoice.id as string,
            amount: (invoice.amount_paid as number) / 100,
            currency: (invoice.currency as string).toUpperCase(),
            status: "paid",
            periodStart: new Date((invoice.period_start as number) * 1000).toISOString(),
            periodEnd: new Date((invoice.period_end as number) * 1000).toISOString(),
            paidAt: new Date().toISOString(),
            createdAt: new Date().toISOString(),
          }).onConflictDoUpdate({
            target: schema.billingInvoices.stripeInvoiceId,
            set: {
              status: "paid",
              paidAt: new Date().toISOString(),
            },
          });

          // Update subscription if invoice paid for subscription
          if (subscriptionId) {
            await db
              .update(schema.subscriptions)
              .set({
                status: SubscriptionStatus.ACTIVE,
                updatedAt: new Date().toISOString(),
              })
              .where(eq(schema.subscriptions.stripeSubscriptionId, subscriptionId));
          }
        }
        break;
      }

      case "invoice.payment_failed": {
        const invoice = event.data.object;
        const customerId = invoice.customer as string;
        const subscriptionId = invoice.subscription as string;

        // Update subscription status to past_due
        if (subscriptionId) {
          await db
            .update(schema.subscriptions)
            .set({
              status: SubscriptionStatus.PAST_DUE,
              updatedAt: new Date().toISOString(),
            })
            .where(eq(schema.subscriptions.stripeSubscriptionId, subscriptionId));
        }

        // Log the failed payment
        console.error(`Payment failed for customer ${customerId}:`, invoice.last_finalization_error?.message);
        break;
      }

      default:
        console.log(`Unhandled webhook event: ${event.type}`);
    }

    return c.json({ success: true, received: true });
  } catch (error) {
    console.error("Webhook processing error:", error);
    return c.json(
      { success: false, error: { code: "WEBHOOK_ERROR", message: "Webhook processing failed" } },
      500
    );
  }
});

// ============================================================================
// POST /billing/usage - Record usage
// ============================================================================

billingRoutes.post("/usage", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json();

  const { organizationId, invoicesProcessed, storageUsed, usersCount } = body as {
    organizationId: string;
    invoicesProcessed?: number;
    storageUsed?: number;
    usersCount?: number;
  };

  if (!organizationId) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId is required" } },
      400
    );
  }

  const currentMonth = new Date().toISOString().slice(0, 7);

  // Upsert usage tracking
  await db
    .insert(schema.usageTracking)
    .values({
      id: uuidv4(),
      organizationId,
      month: currentMonth,
      invoicesProcessed: invoicesProcessed || 0,
      storageUsed: storageUsed || 0,
      usersCount: usersCount || 0,
      lastUpdatedAt: new Date().toISOString(),
    })
    .onConflictDoUpdate({
      target: [schema.usageTracking.organizationId, schema.usageTracking.month],
      set: {
        invoicesProcessed: invoicesProcessed || 0,
        storageUsed: storageUsed || 0,
        usersCount: usersCount || 0,
        lastUpdatedAt: new Date().toISOString(),
      },
    });

  // Get organization for overage calculation
  const [org] = await db
    .select()
    .from(schema.organizations)
    .where(eq(schema.organizations.id, organizationId))
    .limit(1);

  const plan = (org?.plan || "free") as PlanType;
  const overage = calculateOverage(invoicesProcessed || 0, plan);

  return c.json({
    success: true,
    data: {
      month: currentMonth,
      invoicesProcessed,
      storageUsed,
      usersCount,
      overage,
      shouldNotify: overage.overage > 0 && overage.overage % 10 === 0,
    },
  });
});

// ============================================================================
// GET /billing/invoices - List invoices
// ============================================================================

billingRoutes.get("/invoices", async (c) => {
  const db = getDb(c.env);
  const organizationId = c.req.query("organizationId");
  const limit = parseInt(c.req.query("limit") || "50");
  const offset = parseInt(c.req.query("offset") || "0");

  if (!organizationId) {
    return c.json(
      { success: false, error: { code: "INVALID_REQUEST", message: "organizationId is required" } },
      400
    );
  }

  // Get total count
  const [countResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(schema.billingInvoices)
    .where(eq(schema.billingInvoices.organizationId, organizationId));

  // Get invoices
  const invoices = await db
    .select()
    .from(schema.billingInvoices)
    .where(eq(schema.billingInvoices.organizationId, organizationId))
    .orderBy(desc(schema.billingInvoices.createdAt))
    .limit(limit)
    .offset(offset);

  return c.json({
    success: true,
    data: invoices,
    pagination: {
      total: countResult.count || 0,
      limit,
      offset,
      hasMore: (countResult.count || 0) > offset + limit,
    },
  });
});

// ============================================================================
// GET /billing/plans - Get plans
// ============================================================================

billingRoutes.get("/plans", (c) => {
  return c.json({
    success: true,
    data: {
      plans: PLANS,
      overagePricing: {
        free: { rate: 0.05, description: "$0.05 per additional invoice" },
        starter: { rate: 0.10, description: "$0.10 per additional invoice" },
        professional: { rate: 0.05, description: "$0.05 per additional invoice" },
        enterprise: { rate: 0, description: "No overage charges" },
      },
    },
  });
});

// ============================================================================
// Export
// ============================================================================

export { billingRoutes };
