import { Hono } from "hono";
import { sendHITLApprovalRequest, sendDecisionFollowUp } from "../lib/slack";
import { processInternQuery, parseEpisode, saveEpisode, handleHelpQuery } from "../lib/slack-intern";
import { getDb, schema } from "../db";
import { eq } from "drizzle-orm";
import type { Env } from "../db";

const slackRoutes = new Hono<{ Bindings: Env }>();

// Test endpoint to send a sample HITL message to Slack
slackRoutes.post("/test", async (c) => {
  const result = await sendHITLApprovalRequest(c.env, {
    invoiceId: "00ed4c75-4526-4b61-9c45-b2b61f251da3",
    vendorName: "Acme Corp",
    amount: 2500.00,
    currency: "USD",
    riskScore: 45,
    riskLevel: "MEDIUM",
    riskSignals: ["New vendor - first invoice", "Amount exceeds typical range"],
    trustLevel: 3,
    trustBattery: "🔋🔋🔋○○○",
    vendorHistory: {
      totalInvoices: 12,
      avgProcessingDays: 4.2,
      rejectionRate: 8.3,
    },
    suggestedAction: "review",
    confidence: 0.72,
    invoiceNumber: "INV-2024-001",
  });

  return c.json(result);
});

// Test follow-up message
slackRoutes.post("/test/followup", async (c) => {
  const result = await sendDecisionFollowUp(
    c.env,
    "test-001",
    "approved",
    "john@company.com",
    "Verified vendor in system, amount matches PO#12345"
  );

  return c.json(result);
});

// Interactive component endpoint (button clicks from Slack)
slackRoutes.post("/interactions", async (c) => {
  const db = getDb(c.env);
  const contentType = c.req.header("Content-Type") || "";

  let payload: any;

  if (contentType.includes("application/x-www-form-urlencoded")) {
    const formData = await c.req.formData();
    const payloadStr = formData.get("payload");
    if (payloadStr) {
      payload = JSON.parse(payloadStr as string);
    }
  } else {
    payload = await c.req.json();
  }

  if (!payload) {
    return c.json({ error: "No payload received" }, 400);
  }

  // Handle different interaction types
  if (payload.type === "block_actions") {
    const action = payload.actions?.[0];
    const actionValue = action?.value ? JSON.parse(action.value) : null;
    const invoiceId = actionValue?.invoiceId;
    const decision = actionValue?.action;

    if (invoiceId && decision) {
      const newStatus = decision === "approve" ? "APPROVED" : "REJECTED";
      const user = payload.user?.username || payload.user?.id || "unknown";

      // Check if invoice exists first
      const [existingInvoice] = await db
        .select()
        .from(schema.invoices)
        .where(eq(schema.invoices.id, invoiceId))
        .limit(1);

      if (!existingInvoice) {
        // Invoice doesn't exist - just respond to Slack without DB update
        const responseUrl = payload.response_url;
        await fetch(responseUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: `⚠️ Invoice ${invoiceId} not found in system. Please check the invoice ID.`,
            replace_original: true,
          }),
        });
        return c.json({ ok: true, warning: "Invoice not found" });
      }

      // Update invoice status
      await db
        .update(schema.invoices)
        .set({
          status: newStatus,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(schema.invoices.id, invoiceId));

      // Create approval record
      await db.insert(schema.approvals).values({
        id: crypto.randomUUID(),
        invoiceId,
        approverEmail: user,
        status: newStatus,
        comments: `Approved via Slack by ${user}`,
        createdAt: new Date().toISOString(),
      });

      // Send response back to Slack
      const responseUrl = payload.response_url;

      // Update the original message
      await fetch(responseUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `✅ Invoice ${invoiceId} has been ${decision === "approve" ? "approved" : "rejected"} by ${user}`,
          replace_original: true,
        }),
      });

      return c.json({ ok: true });
    }
  }

  return c.json({ ok: true });
});

// ============================================================================
// SLACK INTERN INTERFACE - "The Intern's Desk"
// ============================================================================

/**
 * Event handler for app_mention - when someone @mentions the intern
 * POST /api/v1/slack/intern/events
 */
slackRoutes.post("/intern/events", async (c) => {
  const payload = await c.req.json();

  // Handle URL verification challenge
  if (payload.type === "url_verification") {
    return c.json({ challenge: payload.challenge });
  }

  // Handle app_mention events
  if (payload.type === "event_callback") {
    const event = payload.event;
    const env = c.env;

    // Only handle app_mention events
    if (event.type === "app_mention") {
      const userId = event.user;
      const text = event.text;
      const channelId = event.channel;
      const timestamp = event.ts;

      // Remove the bot mention from the text
      const cleanText = text.replace(/<@[A-Z0-9]+>/, "").trim();

      // Check if this is an instruction (starts with "from now on", "always", etc.)
      const isInstruction = cleanText.toLowerCase().startsWith("from now on") ||
                            cleanText.toLowerCase().startsWith("always") ||
                            cleanText.toLowerCase().startsWith("remember");

      // Process the query or instruction
      let response;
      if (isInstruction) {
        // Handle as an episode/instruction
        const episode = parseEpisode(cleanText);
        if (episode) {
          await saveEpisode(env, episode);
          response = {
            text: `✅ *Got it!*\n\nI've recorded this instruction and will follow it going forward:\n\n> ${episode.description}`,
            thread_ts: timestamp, // Reply in thread
          };
        } else {
          response = {
            text: `I'm not sure how to interpret that instruction. Try something like:\n• "From now on, auto-approve Vercel invoices under $500"\n• "Always flag invoices from [Vendor] for review"`,
            thread_ts: timestamp,
          };
        }
      } else {
        // Handle as a query
        const internResponse = await processInternQuery(env, cleanText);

        // Check if we should respond in thread
        response = {
          text: internResponse.text,
          blocks: internResponse.blocks,
          thread_ts: timestamp,
        };
      }

      // Send response to the channel/thread
      // In production, use the Slack API with proper token
      console.log(`[Intern] Responding to ${userId} in ${channelId}: ${cleanText.substring(0, 50)}...`);

      // Return immediately, response will be sent asynchronously
      return c.json({ ok: true, response_type: "in_channel" });
    }
  }

  return c.json({ ok: true });
});

/**
 * Slash command /intern - Direct query to the intern
 * POST /api/v1/slack/intern/command
 */
slackRoutes.post("/intern/command", async (c) => {
  const formData = await c.req.formData();
  const text = formData.get("text") as string || "";
  const userId = formData.get("user_id") as string;
  const channelId = formData.get("channel_id") as string;
  const responseUrl = formData.get("response_url") as string;

  const env = c.env;

  // Check for help
  if (text.toLowerCase() === "help" || text.trim() === "") {
    const help = handleHelpQuery();
    return c.json({
      response_type: "ephemeral",
      text: help.text,
      blocks: help.blocks,
    });
  }

  // Check if this is an instruction
  const isInstruction = text.toLowerCase().startsWith("from now on") ||
                        text.toLowerCase().startsWith("always") ||
                        text.toLowerCase().startsWith("remember");

  if (isInstruction) {
    const episode = parseEpisode(text);
    if (episode) {
      await saveEpisode(env, episode);
      return c.json({
        response_type: "ephemeral",
        text: `✅ *Got it!*\n\nI've recorded this instruction:\n\n> ${episode.description}\n\nI'll follow this for all future invoices.`,
      });
    }
    return c.json({
      response_type: "ephemeral",
      text: "I'm not sure how to interpret that. Try: \"From now on, auto-approve Vercel invoices under $500\"",
    });
  }

  // Process the query
  const internResponse = await processInternQuery(env, text);

  return c.json({
    response_type: "in_channel",
    text: internResponse.text,
    blocks: internResponse.blocks,
  });
});

export { slackRoutes };
