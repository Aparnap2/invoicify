/**
 * Invoicify Agent Evaluation Tests
 *
 * Run with: pnpm test
 * Coverage report: pnpm test --coverage
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  gradeWorkflowOutput,
  gradeSlackOutput,
  workflowTestCases,
  slackInternTestCases,
} from "../lib/eval";
import type { WorkflowState } from "../lib/workflow";

// ============================================================================
// Workflow Agent Evaluation Tests
// ============================================================================

describe("Workflow Agent Evaluations", () => {
  describe("Low Risk Invoices", () => {
    it("should auto-approve trusted vendor invoice", () => {
      const result: WorkflowState = {
        action: "auto_approve",
        riskScore: 0.15,
        riskLevel: "LOW",
        riskSignals: [],
        markdownOutput: "## Invoice INV-001\n\n**Risk:** LOW",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        decision: "auto_approve",
        riskScoreRange: [0, 0.3],
        riskLevel: "LOW",
        hasSignals: false,
      });

      expect(passed).toBe(true);
      expect(metrics.find(m => m.name === "decision")?.passed).toBe(true);
      expect(metrics.find(m => m.name === "riskScore")?.passed).toBe(true);
    });

    it("should handle recurring invoice pattern", () => {
      const result: WorkflowState = {
        action: "auto_approve",
        riskScore: 0.08,
        riskLevel: "LOW",
        riskSignals: ["Recurring invoice pattern detected"],
        markdownOutput: "## Invoice INV-002\n\n**Risk:** LOW",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        decision: "auto_approve",
        riskScoreRange: [0, 0.2],
        riskLevel: "LOW",
        minSignals: 0, // Signals optional
      });

      expect(passed).toBe(true);
    });
  });

  describe("High Risk Invoices", () => {
    it("should flag new vendor for HITL", () => {
      const result: WorkflowState = {
        action: "hitl",
        riskScore: 0.55,
        riskLevel: "MEDIUM",
        riskSignals: ["New vendor - first invoice", "Amount above average"],
        markdownOutput: "## Invoice INV-003\n\n**Risk:** MEDIUM",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        decision: "hitl",
        riskScoreRange: [0.4, 1.0],
        riskLevel: "MEDIUM",
        minSignals: 1,
      });

      expect(passed).toBe(true);
      expect(metrics.find(m => m.name === "decision")?.passed).toBe(true);
      expect(metrics.find(m => m.name === "minSignals")?.passed).toBe(true);
    });

    it("should detect duplicate invoices", () => {
      const result: WorkflowState = {
        action: "hitl",
        riskScore: 0.65,
        riskLevel: "HIGH",
        riskSignals: ["Possible duplicate of invoice INV-001"],
        markdownOutput: "## Invoice INV-DUP\n\n**Risk:** HIGH",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        decision: "hitl",
        hasSignals: true,
        minSignals: 1,
      });

      expect(passed).toBe(true);
      expect(metrics.find(m => m.name === "hasSignals")?.passed).toBe(true);
    });
  });

  describe("Edge Cases", () => {
    it("should handle zero amount", () => {
      const result: WorkflowState = {
        action: "auto_approve",
        riskScore: 0.01,
        riskLevel: "LOW",
        riskSignals: [],
        markdownOutput: "## Invoice INV-ZERO\n\n**Risk:** LOW",
      } as any;

      const { passed } = gradeWorkflowOutput(result, {
        decision: "auto_approve",
        riskScoreRange: [0, 0.1],
      });

      expect(passed).toBe(true);
    });

    it("should detect runway risk", () => {
      const result: WorkflowState = {
        action: "hitl",
        riskScore: 0.75,
        riskLevel: "HIGH",
        riskSignals: ["Would reduce runway below 30 days"],
        markdownOutput: "## Invoice INV-HIGH\n\n**Risk:** HIGH",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        decision: "hitl",
        riskScoreRange: [0.5, 1.0],
        minSignals: 1,
      });

      expect(passed).toBe(true);
    });
  });

  describe("Markdown Output Validation", () => {
    it("should contain vendor name in output", () => {
      const result: WorkflowState = {
        action: "auto_approve",
        riskScore: 0.1,
        riskLevel: "LOW",
        riskSignals: [],
        markdownOutput: "## Invoice INV-001\n\n**Vendor:** Acme Corp\n**Amount:** $500",
      } as any;

      const { passed, metrics } = gradeWorkflowOutput(result, {
        markdownContains: ["Acme", "$500"],
      });

      expect(passed).toBe(true);
      expect(metrics.find(m => m.name === "markdownContains")?.passed).toBe(true);
    });
  });
});

// ============================================================================
// Slack Intern Evaluation Tests
// ============================================================================

describe("Slack Intern Evaluations", () => {
  it("should parse runway query correctly", () => {
    const response = {
      text: "Runway looks okay, but worth watching.\n\n*Runway:* ~5.0 months\n*Burn:* ~$20,000/mo\n*Cash:* $100,000",
    };

    const { passed, metrics } = gradeSlackOutput(response, {
      markdownContains: ["runway", "months", "cash"],
    });

    expect(passed).toBe(true);
    expect(metrics.find(m => m.name === "responseContains")?.passed).toBe(true);
  });

  it("should parse vendor spend query", () => {
    const response = {
      text: "*Acme Corp*\n\n• *Total Spend:* $15,000\n• *Invoices:* 12\n• *Status:* Trusted",
    };

    const { passed } = gradeSlackOutput(response, {
      markdownContains: ["Acme", "$15,000"],
    });

    expect(passed).toBe(true);
  });

  it("should handle instruction parsing", () => {
    const response = {
      text: "✅ *Got it!*\n\nI've recorded this instruction:\n\n> Auto-approve Vercel up to $500\n\nI'll follow this for all future invoices.",
    };

    const { passed } = gradeSlackOutput(response, {
      markdownContains: ["Vercel", "$500", "recorded"],
    });

    expect(passed).toBe(true);
  });
});

// ============================================================================
// Test Case Library Validation
// ============================================================================

describe("Test Case Library", () => {
  it("should have comprehensive workflow test cases", () => {
    expect(workflowTestCases.length).toBeGreaterThanOrEqual(10);

    // Check for required test categories
    const categories = new Set(workflowTestCases.flatMap(tc => tc.tags));
    expect(categories.has("low-risk")).toBe(true);
    expect(categories.has("high-amount")).toBe(true);
    expect(categories.has("new-vendor")).toBe(true);
    expect(categories.has("hitl")).toBe(true);
  });

  it("should have critical P0 tests", () => {
    const p0Tests = workflowTestCases.filter(tc => tc.priority === "p0");
    expect(p0Tests.length).toBeGreaterThanOrEqual(4);
  });

  it("should have Slack Intern test cases", () => {
    expect(slackInternTestCases.length).toBeGreaterThanOrEqual(3);

    const categories = new Set(slackInternTestCases.flatMap(tc => tc.tags));
    expect(categories.has("query")).toBe(true);
    expect(categories.has("instruction")).toBe(true);
  });
});

// ============================================================================
// Grading Edge Cases
// ============================================================================

describe("Grading Edge Cases", () => {
  it("should handle missing risk signals gracefully", () => {
    const result: WorkflowState = {
      action: "auto_approve",
      riskScore: 0.1,
      riskLevel: "LOW",
      riskSignals: [],
      markdownOutput: "",
    } as any;

    const { passed } = gradeWorkflowOutput(result, {
      hasSignals: false,
    });

    expect(passed).toBe(true);
  });

  it("should handle null risk score gracefully", () => {
    const result: WorkflowState = {
      action: "auto_approve",
      riskScore: null,
      riskLevel: null,
      riskSignals: [],
      markdownOutput: "",
    } as any;

    // Should not throw even with null values
    const { passed, metrics } = gradeWorkflowOutput(result, {
      riskScoreRange: [0, 0.3],
    });

    // No metrics generated when riskScore is null
    expect(metrics.find(m => m.name === "riskScore")).toBeUndefined();
  });

  it("should accept re-schedule as HITL equivalent", () => {
    const result: WorkflowState = {
      action: "re-schedule",
      riskScore: 0.45,
      riskLevel: "MEDIUM",
      riskSignals: ["Amount variance detected"],
      markdownOutput: "",
    } as any;

    const { passed, metrics } = gradeWorkflowOutput(result, {
      decision: "hitl",
    });

    // re-schedule should count as hitl
    expect(metrics.find(m => m.name === "decision")?.passed).toBe(true);
  });
});
