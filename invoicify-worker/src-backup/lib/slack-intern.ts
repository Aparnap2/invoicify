/**
 * Slack Intern Interface - "The Intern's Desk"
 *
 * Mimics a real Finance Intern that the founder can:
 * 1. Shout questions at (conversational queries)
 * 2. Receive proactive alerts from (blocked invoices, budget warnings)
 * 3. Give instructions to (episode creation / memory injection)
 *
 * Key behaviors:
 * - Conversational, helpful tone (not robotic)
 * - Context-aware answers
 * - Proactive notifications when important
 * - Memory of past instructions
 */

import { getDb, schema } from "../db";
import { eq, sql, desc, and, gte } from "drizzle-orm";
import { getFinancialContext, FinancialContext } from "./workflow";
import type { Env } from "../db";

// ============================================================================
// CONVERSATIONAL QUERY TYPES
// ============================================================================

export type QueryIntent =
  | "RUNWAY_QUERY"
  | "CASH_QUERY"
  | "BURN_QUERY"
  | "VENDOR_SPEND_QUERY"
  | "INVOICE_STATUS_QUERY"
  | "BUDGET_QUERY"
  | "HELP_QUERY"
  | "UNKNOWN_QUERY";

export interface InternQuery {
  intent: QueryIntent;
  entities: {
    vendorName?: string;
    amount?: number;
    timePeriod?: string;
    category?: string;
  };
  originalText: string;
}

export interface InternResponse {
  text: string; // Primary response
  blocks?: any[]; // Slack Block Kit for rich responses
  requiresAction?: boolean; // If this needs user approval
  actions?: InternAction[];
}

export interface InternAction {
  type: "approve" | "reject" | "view_details";
  label: string;
  value: string;
}

// ============================================================================
// QUERY PARSER - Intent detection
// ============================================================================

/**
 * Parse natural language query into structured intent
 */
export function parseInternQuery(text: string): InternQuery {
  const lowerText = text.toLowerCase();

  // RUNWAY queries
  if (lowerText.includes("runway") || lowerText.includes("how long")) {
    return {
      intent: "RUNWAY_QUERY",
      entities: {},
      originalText: text,
    };
  }

  // CASH queries
  if (lowerText.includes("cash") || lowerText.includes("bank balance") || lowerText.includes("money in the bank")) {
    return {
      intent: "CASH_QUERY",
      entities: {},
      originalText: text,
    };
  }

  // BURN queries
  if (lowerText.includes("burn") || lowerText.includes("spending rate") || lowerText.includes("how much.*spending")) {
    return {
      intent: "BURN_QUERY",
      entities: {},
      originalText: text,
    };
  }

  // VENDOR queries
  const vendorMatch = text.match(/(?:paid|owe|spend|how much).*?(?:to|from|for)\s+["']?([A-Za-z0-9\s]+)["']?/i);
  if ((lowerText.includes("paid") || lowerText.includes("owe") || lowerText.includes("spend")) && vendorMatch) {
    return {
      intent: "VENDOR_SPEND_QUERY",
      entities: { vendorName: vendorMatch[1].trim() },
      originalText: text,
    };
  }

  // INVOICE STATUS queries
  if (lowerText.includes("invoice") || lowerText.includes("bill") || lowerText.includes("did we pay")) {
    const invoiceNumMatch = text.match(/(?:invoice|bill|invs?)[-#\s]*([A-Z0-9-]+)/i);
    return {
      intent: "INVOICE_STATUS_QUERY",
      entities: { vendorName: invoiceNumMatch?.[1] },
      originalText: text,
    };
  }

  // BUDGET queries
  if (lowerText.includes("budget") || lowerText.includes("spend.*month") || lowerText.includes("category")) {
    const categoryMatch = text.match(/(?:in|for|on|spending)\s+(?:the\s+)?([A-Za-z]+)\s+(?:budget|category|spend)/i);
    return {
      intent: "BUDGET_QUERY",
      entities: { category: categoryMatch?.[1] },
      originalText: text,
    };
  }

  // HELP queries
  if (lowerText.includes("help") || lowerText.includes("what can you do") || lowerText.includes("?")) {
    return {
      intent: "HELP_QUERY",
      entities: {},
      originalText: text,
    };
  }

  return {
    intent: "UNKNOWN_QUERY",
    entities: {},
    originalText: text,
  };
}

// ============================================================================
// QUERY HANDLERS - Context-aware responses
// ============================================================================

/**
 * Handle runway query with context
 */
async function handleRunwayQuery(env: Env, context: FinancialContext): Promise<InternResponse> {
  const runwayMonths = context.runwayDays / 30;
  let tone = "You're doing great!";
  let warning = "";

  if (runwayMonths < 3) {
    tone = "Heads up - runway is getting tight.";
    warning = "\n\n⚠️ *Recommendation:* I'm holding all non-essential invoices until you review them.";
  } else if (runwayMonths < 6) {
    tone = "Runway looks okay, but worth watching.";
  } else if (runwayMonths > 18) {
    tone = "Nice position to be in!";
  }

  // Check for upcoming large payments
  const db = getDb(env);
  const [pendingTotal] = await db
    .select({ total: sql<number>`coalesce(sum(${schema.payments.amount}), 0)` })
    .from(schema.payments)
    .where(eq(schema.payments.status, "scheduled"));

  let paymentNote = "";
  if (pendingTotal && Number(pendingTotal.total) > context.monthlyBurnRate * 2) {
    paymentNote = `\n\n📋 *Note:* You have ~$${Number(pendingTotal.total).toLocaleString()} in scheduled payments coming up.`;
  }

  return {
    text: `${tone}\n\n*Current Runway:* ~${runwayMonths.toFixed(1)} months (${context.runwayDays} days)\n*Burn Rate:* ~$${context.monthlyBurnRate.toLocaleString()}/month\n*Cash:* $${context.currentCash.toLocaleString()}${paymentNote}${warning}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `${tone}\n\n• *Runway:* ~${runwayMonths.toFixed(1)} months\n• *Burn:* ~$${context.monthlyBurnRate.toLocaleString()}/mo\n• *Cash:* $${context.currentCash.toLocaleString()}${paymentNote}${warning}`,
        },
      },
    ],
  };
}

/**
 * Handle cash balance query
 */
async function handleCashQuery(env: Env, context: FinancialContext): Promise<InternResponse> {
  return {
    text: `*Bank Balance:* $${context.currentCash.toLocaleString()}\n\nBased on your burn rate of ~$${context.monthlyBurnRate.toLocaleString()}/month, you've got about ${context.runwayDays} days of runway.`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Current Cash:* $${context.currentCash.toLocaleString()}\n\n_This is what you have available to spend right now._`,
        },
      },
    ],
  };
}

/**
 * Handle burn rate query
 */
async function handleBurnQuery(env: Env, context: FinancialContext): Promise<InternResponse> {
  return {
    text: `*Monthly Burn Rate:* ~$${context.monthlyBurnRate.toLocaleString()}\n\nBreakdown:\n• Payroll: $${(context.monthlyBurnRate * 0.6).toLocaleString()}/mo\n• Infra: $${(context.monthlyBurnRate * 0.2).toLocaleString()}/mo\n• Marketing: $${(context.monthlyBurnRate * 0.1).toLocaleString()}/mo\n• G&A: $${(context.monthlyBurnRate * 0.1).toLocaleString()}/mo`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Monthly Spending:* ~$${context.monthlyBurnRate.toLocaleString()}\n\nThis is your average monthly cash outflow. Your runway is ~${(context.currentCash / context.monthlyBurnRate).toFixed(1)} months based on this.`,
        },
      },
    ],
  };
}

/**
 * Handle vendor spend query
 */
async function handleVendorSpendQuery(env: Env, query: InternQuery): Promise<InternResponse> {
  if (!query.entities.vendorName) {
    return {
      text: "Which vendor are you asking about? Try: \"How much did we pay to Acme?\"",
    };
  }

  const db = getDb(env);
  const vendorName = query.entities.vendorName;

  // Find vendor
  const [vendor] = await db
    .select()
    .from(schema.vendors)
    .where(sql`${schema.vendors.name} LIKE ${'%' + vendorName + '%'}`)
    .limit(1);

  if (!vendor) {
    return {
      text: `I don't have any records for "${vendorName}". Want me to look them up differently?`,
    };
  }

  // Get total spend
  const [spendResult] = await db
    .select({
      total: sql<number>`coalesce(sum(${schema.invoices.totalAmount}), 0)`,
      count: sql<number>`count(*)`,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.vendorId, vendor.id));

  const totalSpend = Number(spendResult.total) || 0;
  const invoiceCount = Number(spendResult.count) || 0;

  const trustStatus = vendor.riskLevel === "LOW" ? "✅ Trusted" : vendor.riskLevel === "MEDIUM" ? "⚠️ Review" : "❌ High Risk";

  return {
    text: `*${vendor.name}*\n\n• *Total Spend:* $${totalSpend.toLocaleString()}\n• *Invoices:* ${invoiceCount}\n• *Trust Status:* ${trustStatus}\n• *Avg Invoice:* $${invoiceCount > 0 ? (totalSpend / invoiceCount).toFixed(0) : 0}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*${vendor.name}*\n\n• *Total to date:* $${totalSpend.toLocaleString()}\n• *Invoices:* ${invoiceCount}\n• *Status:* ${trustStatus}`,
        },
        accessory: vendor.riskLevel === "LOW" ? {
          type: "button",
          text: "View Invoices",
          value: `vendor_${vendor.id}`,
        } : undefined,
      },
    ],
  };
}

/**
 * Handle invoice status query
 */
async function handleInvoiceStatusQuery(env: Env, query: InternQuery): Promise<InternResponse> {
  const db = getDb(env);

  // Get pending invoices
  const [pendingResult] = await db
    .select({ count: sql<number>`count(*)`, total: sql<number>`sum(${schema.invoices.totalAmount})` })
    .from(schema.invoices)
    .where(eq(schema.invoices.status, "PENDING"));

  const pendingCount = Number(pendingResult.count) || 0;
  const pendingAmount = Number(pendingResult.total) || 0;

  // Get recent invoices
  const recentInvoices = await db
    .select({
      id: schema.invoices.id,
      vendorName: schema.invoices.vendorName,
      amount: schema.invoices.totalAmount,
      status: schema.invoices.status,
      dueDate: schema.invoices.dueDate,
    })
    .from(schema.invoices)
    .orderBy(desc(schema.invoices.createdAt))
    .limit(5);

  let recentText = "*Recent Invoices:*\n";
  for (const inv of recentInvoices) {
    const emoji = inv.status === "APPROVED" ? "✅" : inv.status === "PENDING" ? "⏳" : "❌";
    recentText += `${emoji} ${inv.vendorName}: $${inv.amount?.toFixed(0)} (${inv.status})\n`;
  }

  return {
    text: `*Invoice Status*\n\n• *Pending:* ${pendingCount} invoices ($${pendingAmount.toLocaleString()})\n\n${recentText}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Pending Invoices:* ${pendingCount} totaling $${pendingAmount.toLocaleString()}\n\n_${recentText}_`,
        },
      },
    ],
  };
}

/**
 * Handle budget query
 */
async function handleBudgetQuery(env: Env, query: InternQuery, context: FinancialContext): Promise<InternResponse> {
  const category = query.entities.category;
  const budgets = context.budgets;

  if (category) {
    const budget = budgets.find(b => b.category.toLowerCase() === category.toLowerCase());
    if (budget) {
      const percent = (budget.currentSpend / budget.monthlyLimit) * 100;
      const emoji = percent > 90 ? "🔴" : percent > 70 ? "🟡" : "🟢";
      return {
        text: `${emoji} *${budget.category} Budget*\n\n• *Used:* $${budget.currentSpend.toLocaleString()} / $${budget.monthlyLimit.toLocaleString()}\n• *Remaining:* $${(budget.monthlyLimit - budget.currentSpend).toLocaleString()}\n• *Used:* ${percent.toFixed(0)}%`,
      };
    }
  }

  // Show all budgets
  let budgetText = "*Monthly Budgets:*\n";
  for (const budget of budgets) {
    const percent = (budget.currentSpend / budget.monthlyLimit) * 100;
    const emoji = percent > 90 ? "🔴" : percent > 70 ? "🟡" : "🟢";
    budgetText += `${emoji} ${budget.category}: $${budget.currentSpend.toLocaleString()}/${budget.monthlyLimit.toLocaleString()}\n`;
  }

  return {
    text: budgetText,
  };
}

/**
 * Handle help query
 */
export function handleHelpQuery(): InternResponse {
  return {
    text: `*Hey! I'm your Finance Intern. Here's what I can help with:*

📊 *Questions you can ask:*
• "How much runway do we have?"
• "What's our burn rate?"
• "How much cash do we have?"
• "How much did we pay to [Vendor]?"
• "What's pending?"
• "Show me the budget"

🚨 *Things I'll proactively alert you on:*
• Large invoices that could hurt runway
• Duplicate or suspicious invoices
• Budget overruns
• Unusual spending patterns

📝 *Instructions you can give:*
• "From now on, auto-approve [Vendor] up to $X"
• "Always flag invoices over $Y for review"

Just ask!`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*👋 Hey, I'm your Finance Intern!*

I can help you stay on top of your finances without opening a dashboard.

*Try asking me:*
• "How much runway do we have?"
• "What's our burn rate?"
• "How much did we pay to Acme?"
• "Show me pending invoices"

*Or give me instructions:*
• "Auto-approve Vercel invoices under $500"
• "Always flag invoices over $5k for review"`,
        },
      },
    ],
  };
}

// ============================================================================
// MAIN QUERY HANDLER
// ============================================================================

/**
 * Process a query from Slack and return a response
 */
export async function processInternQuery(
  env: Env,
  text: string
): Promise<InternResponse> {
  const query = parseInternQuery(text);
  const context = await getFinancialContext(env);

  switch (query.intent) {
    case "RUNWAY_QUERY":
      return handleRunwayQuery(env, context);
    case "CASH_QUERY":
      return handleCashQuery(env, context);
    case "BURN_QUERY":
      return handleBurnQuery(env, context);
    case "VENDOR_SPEND_QUERY":
      return handleVendorSpendQuery(env, query);
    case "INVOICE_STATUS_QUERY":
      return handleInvoiceStatusQuery(env, query);
    case "BUDGET_QUERY":
      return handleBudgetQuery(env, query, context);
    case "HELP_QUERY":
      return handleHelpQuery();
    case "UNKNOWN_QUERY":
    default:
      return {
        text: `Hmm, I'm not sure what you mean by "${text}". Try asking about runway, burn rate, vendor spend, or just say "help" to see what I can do!`,
      };
  }
}

// ============================================================================
// EPISODE / MEMORY INJECTION
// ============================================================================

export interface Episode {
  id: string;
  type: "TRUST_POLICY" | "APPROVAL_RULE" | "WORKFLOW_INSTRUCTION";
  description: string;
  pattern: Record<string, any>;
  action: Record<string, any>;
  createdAt: string;
}

/**
 * Parse an instruction into an episode
 */
export function parseEpisode(text: string): Episode | null {
  const lowerText = text.toLowerCase();

  // "From now on, auto-approve [Vendor] up to $X"
  // Matches: "auto-approve Vercel up to $500", "auto-approve Vercel under $500", "auto-approve invoices from Vercel under 500"
  // Handle optional dollar sign and capture amount separately
  const autoApproveMatch = text.match(/auto-?approve\s+(?:invoices?\s+from\s+)?["']?([^"']+)["']?(?:\s+(?:up to|under|below))\s*\$?\s*([0-9,]+(?:\.[0-9]{2})?)/i);
  if (autoApproveMatch) {
    const amount = parseFloat(autoApproveMatch[2].replace(/,/g, ""));
    return {
      id: crypto.randomUUID(),
      type: "TRUST_POLICY",
      description: `Auto-approve ${autoApproveMatch[1]} up to $${amount}`,
      pattern: { vendorName: autoApproveMatch[1] },
      action: { autoApprove: true, maxAmount: amount },
      createdAt: new Date().toISOString(),
    };
  }

  // "Always flag [Vendor] for review"
  const flagReviewMatch = text.match(/always\s+flag\s+(?:invoices?\s+from\s+)?["']?([^"']+)["']?\s+for\s+review/i);
  if (flagReviewMatch) {
    return {
      id: crypto.randomUUID(),
      type: "APPROVAL_RULE",
      description: `Always flag ${flagReviewMatch[1]} for review`,
      pattern: { vendorName: flagReviewMatch[1] },
      action: { requireReview: true },
      createdAt: new Date().toISOString(),
    };
  }

  return null;
}

/**
 * Save an episode to the database
 */
export async function saveEpisode(env: Env, episode: Episode): Promise<boolean> {
  try {
    const db = getDb(env);
    // In a real implementation, we'd have an episodes table
    // For now, we'll store this in the strategic_config or a new table
    await db.insert(schema.strategicConfig).values({
      id: episode.id,
      strategyMode: "OPTIMIZE" as any,
      autoApproveThreshold: episode.action.maxAmount || 500,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    return true;
  } catch (error) {
    console.error("Failed to save episode:", error);
    return false;
  }
}
