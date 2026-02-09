/**
 * Slack Integration for HITL Approval Requests
 *
 * Sends contextual approval requests to Slack channels with:
 * - Invoice details and risk assessment
 * - Vendor trust history
 * - Temporal context from knowledge graph
 * - Suggested action with confidence metrics
 */

import type { Env } from "../db";

interface SlackBlock {
  type: string;
  text?: {
    type: string;
    text: string;
    emoji?: boolean;
  };
  elements?: Array<{
    type: string;
    text?: {
      type: string;
      text: string;
      emoji?: boolean;
    };
    value?: string;
    action_id?: string;
  }>;
  accessory?: {
    type: string;
    text?: {
      type: string;
      text: string;
      emoji?: boolean;
    };
    url?: string;
  };
}

interface HITLMessage {
  invoiceId: string;
  vendorName: string;
  amount: number;
  currency: string;
  riskScore: number;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  riskSignals: string[];
  trustLevel: number;
  trustBattery: string;
  vendorHistory: {
    totalInvoices: number;
    avgProcessingDays: number;
    rejectionRate: number;
  };
  suggestedAction: "approve" | "reject" | "review";
  confidence: number;
  dueDate?: string;
  invoiceNumber?: string;
}

/**
 * Send HITL approval request to Slack
 */
export async function sendHITLApprovalRequest(
  env: Env,
  message: HITLMessage
): Promise<{ success: boolean; error?: string }> {
  const slackToken = env.SLACK_BOT_USER_OAUTH_TOKEN;

  if (!slackToken) {
    console.error("SLACK_BOT_USER_OAUTH_TOKEN not configured");
    return { success: false, error: "Slack token not configured" };
  }

  const channel = "#invoicify-approvals"; // Default channel
  const riskEmoji = getRiskEmoji(message.riskLevel);
  const actionColor = getActionColor(message.suggestedAction);

  const blocks: SlackBlock[] = [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: `${riskEmoji} Invoice Approval Required`,
        emoji: true,
      },
    },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*${message.vendorName}* | *${message.currency} ${message.amount.toLocaleString()}*${message.invoiceNumber ? ` | \`${message.invoiceNumber}\`` : ""}`,
      },
    },
    {
      type: "section",
      fields: [
        {
          type: "mrkdwn",
          text: `*Risk Score:*\n${message.riskScore}/100 (${message.riskLevel})`,
        },
        {
          type: "mrkdwn",
          text: `*Trust Battery:*\n${message.trustBattery} (Level ${message.trustLevel})`,
        },
        {
          type: "mrkdwn",
          text: `*Confidence:*\n${(message.confidence * 100).toFixed(0)}%`,
        },
        {
          type: "mrkdwn",
          text: `*Suggested:*\n${actionColor} ${message.suggestedAction.toUpperCase()}`,
        },
      ],
    },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*Risk Signals:*\n${message.riskSignals.length > 0 ? message.riskSignals.map((s) => `• ${s}`).join("\n") : "• No significant signals detected"}`,
      },
    },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*Vendor History:*\n• ${message.vendorHistory.totalInvoices} past invoices | ${message.vendorHistory.avgProcessingDays} day avg | ${message.vendorHistory.rejectionRate}% rejection rate`,
      },
    },
    {
      type: "divider",
    },
    {
      type: "actions",
      elements: [
        {
          type: "button",
          text: {
            type: "plain_text",
            text: "✅ Approve",
            emoji: true,
          },
          value: JSON.stringify({ action: "approve", invoiceId: message.invoiceId }),
          action_id: "hitl_approve",
          style: "primary",
        },
        {
          type: "button",
          text: {
            type: "plain_text",
            text: "❌ Reject",
            emoji: true,
          },
          value: JSON.stringify({ action: "reject", invoiceId: message.invoiceId }),
          action_id: "hitl_reject",
          style: "danger",
        },
        {
          type: "button",
          text: {
            type: "plain_text",
            text: "👁️ View Details",
            emoji: true,
          },
          url: `https://invoicify.pages.dev/invoices/${message.invoiceId}`,
          action_id: "hitl_view",
        },
      ],
    },
  ];

  try {
    const response = await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${slackToken}`,
      },
      body: JSON.stringify({
        channel,
        text: `Invoice approval required: ${message.vendorName} - ${message.currency} ${message.amount}`,
        blocks,
        unfurl_links: false,
      }),
    });

    const result = await response.json();

    if (!result.ok) {
      console.error("Slack API error:", result.error);
      return { success: false, error: result.error };
    }

    console.log("Slack HITL message sent:", result.ts);
    return { success: true };
  } catch (error) {
    console.error("Failed to send Slack message:", error);
    return { success: false, error: (error as Error).message };
  }
}

/**
 * Send follow-up message with decision context
 */
export async function sendDecisionFollowUp(
  env: Env,
  invoiceId: string,
  decision: "approved" | "rejected",
  decidedBy: string,
  reasoning: string
): Promise<{ success: boolean }> {
  const slackToken = env.SLACK_BOT_USER_OAUTH_TOKEN;

  if (!slackToken) {
    return { success: false };
  }

  const emoji = decision === "approved" ? "✅" : "❌";
  const status = decision === "approved" ? "APPROVED" : "REJECTED";

  try {
    await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${slackToken}`,
      },
      body: JSON.stringify({
        channel: "#invoicify-approvals",
        text: `${emoji} Invoice ${status}: ${invoiceId}`,
        blocks: [
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `${emoji} *Invoice ${status}*\nBy: ${decidedBy}\n\n_Reasoning: ${reasoning}_`,
            },
          },
        ],
      }),
    });

    return { success: true };
  } catch (error) {
    console.error("Failed to send follow-up:", error);
    return { success: false };
  }
}

function getRiskEmoji(level: string): string {
  switch (level) {
    case "LOW":
      return "🟢";
    case "MEDIUM":
      return "🟡";
    case "HIGH":
      return "🟠";
    case "CRITICAL":
      return "🔴";
    default:
      return "⚪";
  }
}

function getActionColor(action: string): string {
  switch (action) {
    case "approve":
      return "🟢";
    case "reject":
      return "🔴";
    case "review":
      return "🟡";
    default:
      return "⚪";
  }
}
