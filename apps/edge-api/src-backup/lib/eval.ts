/**
 * Invoicify Agent Evaluation Framework
 *
 * Based on Anthropic's Agent Eval Playbook:
 * - Test final output, not steps
 * - Code-based graders for objective metrics
 * - Model-based graders for flexible judgment
 * - Human graders for edge cases
 *
 * Key Eval Areas:
 * 1. Workflow Agent: Decision quality, risk accuracy
 * 2. Slack Intern: Query parsing, response correctness
 * 3. Trust Battery: Trust score evolution
 */

import { createInvoiceSchema, approvalSchema, startWorkflowSchema } from "./validation";
import { createInitialState, WorkflowNodes } from "./workflow";
import type { WorkflowState } from "./workflow";

// ============================================================================
// Test Case Types
// ============================================================================

export interface TestCase<T = any> {
  id: string;
  name: string;
  input: T;
  expected: {
    decision?: "auto_approve" | "hitl" | "block" | "re-schedule";
    riskScoreRange?: [number, number]; // min, max
    riskLevel?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
    hasSignals?: boolean;
    minSignals?: number;
    maxSignals?: number;
    markdownContains?: string[];
  };
  tags: string[];
  priority: "p0" | "p1" | "p2";
}

export interface EvalResult {
  testCaseId: string;
  passed: boolean;
  score: number; // 0-1
  metrics: {
    name: string;
    expected: any;
    actual: any;
    passed: boolean;
  }[];
  output: {
    decision?: string;
    riskScore?: number;
    riskLevel?: string;
    signals?: string[];
    markdown?: string;
  };
  latencyMs: number;
  error?: string;
}

export interface EvalRun {
  timestamp: string;
  totalTests: number;
  passed: number;
  failed: number;
  passRate: number;
  avgLatencyMs: number;
  results: EvalResult[];
  tagsRun: string[];
}

// ============================================================================
// Test Case Library
// ============================================================================

export const workflowTestCases: TestCase[] = [
  // P0: Critical path - Low risk should auto-approve
  {
    id: "WF-001",
    name: "Low risk invoice from trusted vendor",
    input: {
      vendorName: "Acme Office Supplies",
      vendorId: "vendor-001",
      invoiceNumber: "INV-2024-001",
      amount: 500,
      currency: "USD",
    },
    expected: {
      decision: "auto_approve",
      riskScoreRange: [0, 0.3],
      riskLevel: "LOW",
      hasSignals: false,
    },
    tags: ["low-risk", "trusted-vendor", "happy-path"],
    priority: "p0",
  },
  {
    id: "WF-002",
    name: "Recurring monthly invoice from core vendor",
    input: {
      vendorName: "Tech Solutions Inc",
      vendorId: "vendor-002",
      invoiceNumber: "INV-2024-002",
      amount: 15000,
      currency: "USD",
    },
    expected: {
      decision: "auto_approve",
      riskScoreRange: [0, 0.2],
      riskLevel: "LOW",
    },
    tags: ["recurring", "core-vendor", "happy-path"],
    priority: "p0",
  },

  // P0: Critical path - High risk should HITL
  {
    id: "WF-003",
    name: "New vendor with high amount",
    input: {
      vendorName: "Suspicious Vendor LLC",
      vendorId: "vendor-005",
      invoiceNumber: "INV-2024-003",
      amount: 45000,
      currency: "USD",
    },
    expected: {
      decision: "hitl",
      riskScoreRange: [0.4, 1.0],
      riskLevel: "MEDIUM",
      minSignals: 1,
    },
    tags: ["new-vendor", "high-amount", "hitl"],
    priority: "p0",
  },
  {
    id: "WF-004",
    name: "Duplicate invoice detection",
    input: {
      vendorName: "Acme Office Supplies",
      vendorId: "vendor-001",
      invoiceNumber: "INV-DUPLICATE-001",
      amount: 2450,
      currency: "USD",
      rawText: "Office supplies - same as INV-2024-001",
    },
    expected: {
      decision: "hitl",
      riskScoreRange: [0.3, 0.8],
      hasSignals: true,
      minSignals: 1,
    },
    tags: ["duplicate", "suspicious"],
    priority: "p0",
  },

  // P1: Edge cases
  {
    id: "WF-005",
    name: "Amount exceeds safety buffer",
    input: {
      vendorName: "Big Corp Inc",
      invoiceNumber: "INV-2024-005",
      amount: 80000,
      currency: "USD",
    },
    expected: {
      decision: "hitl",
      riskScoreRange: [0.5, 1.0],
    },
    tags: ["high-amount", "runway-risk"],
    priority: "p1",
  },
  {
    id: "WF-006",
    name: "Amount deviates from vendor average",
    input: {
      vendorName: "Tech Solutions Inc",
      vendorId: "vendor-002",
      invoiceNumber: "INV-2024-006",
      amount: 50000, // Much higher than typical 15k
      currency: "USD",
    },
    expected: {
      decision: "hitl",
      riskScoreRange: [0.3, 0.7],
      hasSignals: true,
    },
    tags: ["amount-deviation", "hitl"],
    priority: "p1",
  },

  // P1: Trust battery edge cases
  {
    id: "WF-007",
    name: "Core vendor with perfect track record",
    input: {
      vendorName: "Acme Office Supplies",
      vendorId: "vendor-001",
      invoiceNumber: "INV-2024-007",
      amount: 5000,
      currency: "USD",
    },
    expected: {
      decision: "auto_approve",
      riskScoreRange: [0, 0.15],
      riskLevel: "LOW",
    },
    tags: ["core-vendor", "trusted"],
    priority: "p1",
  },
  {
    id: "WF-008",
    name: "Probation vendor - extra scrutiny",
    input: {
      vendorName: "Startup Services",
      vendorId: "vendor-006",
      invoiceNumber: "INV-2024-008",
      amount: 10000,
      currency: "USD",
    },
    expected: {
      decision: "hitl",
      riskScoreRange: [0.3, 0.8],
    },
    tags: ["probation-vendor", "scrutiny"],
    priority: "p1",
  },

  // P2: Stress cases
  {
    id: "WF-009",
    name: "Zero amount invoice",
    input: {
      vendorName: "Free Service",
      invoiceNumber: "INV-2024-009",
      amount: 0,
      currency: "USD",
    },
    expected: {
      decision: "auto_approve",
      riskScoreRange: [0, 0.1],
    },
    tags: ["zero-amount", "edge-case"],
    priority: "p2",
  },
  {
    id: "WF-010",
    name: "Large amount under auto-approve threshold",
    input: {
      vendorName: "Acme Office Supplies",
      vendorId: "vendor-001",
      invoiceNumber: "INV-2024-010",
      amount: 250,
      currency: "USD",
    },
    expected: {
      decision: "auto_approve",
      riskScoreRange: [0, 0.1],
    },
    tags: ["low-amount", "happy-path"],
    priority: "p2",
  },
];

export const slackInternTestCases: TestCase<string>[] = [
  {
    id: "SI-001",
    name: "Runway query",
    input: "How much runway do we have?",
    expected: {
      markdownContains: ["runway", "months", "cash"],
    },
    tags: ["query", "runway"],
    priority: "p0",
  },
  {
    id: "SI-002",
    name: "Burn rate query",
    input: "What's our burn rate?",
    expected: {
      markdownContains: ["burn", "month", "$"],
    },
    tags: ["query", "burn"],
    priority: "p0",
  },
  {
    id: "SI-003",
    name: "Vendor spend query",
    input: "How much did we pay to Acme?",
    expected: {
      markdownContains: ["Acme", "$"],
    },
    tags: ["query", "vendor-spend"],
    priority: "p0",
  },
  {
    id: "SI-004",
    name: "Auto-approve instruction",
    input: "From now on, auto-approve Vercel under $500",
    expected: {
      markdownContains: ["Vercel", "$500", "recorded"],
    },
    tags: ["instruction", "trust-policy"],
    priority: "p0",
  },
  {
    id: "SI-005",
    name: "Help query",
    input: "help",
    expected: {
      markdownContains: ["help", "runway", "burn"],
    },
    tags: ["query", "help"],
    priority: "p1",
  },
];

// ============================================================================
// Code-Based Graders
// ============================================================================

/**
 * Grade workflow output against expected criteria
 */
export function gradeWorkflowOutput(
  result: WorkflowState,
  expected: TestCase["expected"]
): { passed: boolean; metrics: EvalResult["metrics"] } {
  const metrics: EvalResult["metrics"] = [];

  // Grade decision
  if (expected.decision) {
    const actualDecision = result.action;
    const passed = actualDecision === expected.decision ||
      (expected.decision === "hitl" && actualDecision === "re-schedule"); // Re-schedule counts as HITL
    metrics.push({
      name: "decision",
      expected: expected.decision,
      actual: actualDecision,
      passed,
    });
  }

  // Grade risk score
  if (expected.riskScoreRange && result.riskScore !== null) {
    const [min, max] = expected.riskScoreRange;
    const passed = result.riskScore >= min && result.riskScore <= max;
    metrics.push({
      name: "riskScore",
      expected: `${min}-${max}`,
      actual: result.riskScore.toFixed(3),
      passed,
    });
  }

  // Grade risk level
  if (expected.riskLevel && result.riskLevel) {
    const passed = result.riskLevel === expected.riskLevel;
    metrics.push({
      name: "riskLevel",
      expected: expected.riskLevel,
      actual: result.riskLevel,
      passed,
    });
  }

  // Grade signals
  if (expected.hasSignals !== undefined) {
    const hasSignals = result.riskSignals.length > 0;
    const passed = hasSignals === expected.hasSignals;
    metrics.push({
      name: "hasSignals",
      expected: expected.hasSignals,
      actual: hasSignals,
      passed,
    });
  }

  if (expected.minSignals !== undefined) {
    const passed = result.riskSignals.length >= expected.minSignals;
    metrics.push({
      name: "minSignals",
      expected: `>= ${expected.minSignals}`,
      actual: result.riskSignals.length,
      passed,
    });
  }

  // Grade markdown
  if (expected.markdownContains && result.markdownOutput) {
    const allPresent = expected.markdownContains.every(keyword =>
      result.markdownOutput!.toLowerCase().includes(keyword.toLowerCase())
    );
    metrics.push({
      name: "markdownContains",
      expected: expected.markdownContains.join(", "),
      actual: result.markdownOutput.substring(0, 100),
      passed: allPresent,
    });
  }

  const passed = metrics.every(m => m.passed);
  return { passed, metrics };
}

/**
 * Grade Slack Intern output
 */
export function gradeSlackOutput(
  response: { text: string; blocks?: any[] },
  expected: TestCase["expected"]
): { passed: boolean; metrics: EvalResult["metrics"] } {
  const metrics: EvalResult["metrics"] = [];

  if (expected.markdownContains) {
    const text = response.text.toLowerCase();
    const allPresent = expected.markdownContains.every(keyword =>
      text.includes(keyword.toLowerCase())
    );
    metrics.push({
      name: "responseContains",
      expected: expected.markdownContains.join(", "),
      actual: response.text.substring(0, 100),
      passed: allPresent,
    });
  }

  const passed = metrics.every(m => m.passed);
  return { passed, metrics };
}

// ============================================================================
// Evaluation Runner
// ============================================================================

export interface EvalRunnerOptions {
  testCases: TestCase[];
  runWorkflow: (input: any) => Promise<WorkflowState>;
  runSlackQuery: (query: string) => Promise<{ text: string; blocks?: any[] }>;
  runId?: string;
  tags?: string[];
}

export async function runEval({
  testCases,
  runWorkflow,
  runSlackQuery,
  runId = crypto.randomUUID(),
  tags,
}: EvalRunnerOptions): Promise<EvalRun> {
  const startTime = Date.now();
  const results: EvalResult[] = [];

  // Filter by tags if provided
  const filteredCases = tags?.length
    ? testCases.filter(tc => tags.some(tag => tc.tags.includes(tag)))
    : testCases;

  for (const testCase of filteredCases) {
    const caseStartTime = Date.now();

    try {
      let output: any;
      let gradeResult: { passed: boolean; metrics: EvalResult["metrics"] };

      if ("vendorName" in testCase.input) {
        // Workflow test case
        output = await runWorkflow(testCase.input);
        gradeResult = gradeWorkflowOutput(output, testCase.expected);
      } else {
        // Slack Intern test case
        output = await runSlackQuery(testCase.input);
        gradeResult = gradeSlackOutput(output, testCase.expected);
      }

      results.push({
        testCaseId: testCase.id,
        passed: gradeResult.passed,
        score: gradeResult.metrics.every(m => m.passed) ? 1 :
          gradeResult.metrics.filter(m => m.passed).length / gradeResult.metrics.length,
        metrics: gradeResult.metrics,
        output: {
          decision: output.action,
          riskScore: output.riskScore,
          riskLevel: output.riskLevel,
          signals: output.riskSignals,
          markdown: output.markdownOutput || output.text,
        },
        latencyMs: Date.now() - caseStartTime,
      });
    } catch (error) {
      results.push({
        testCaseId: testCase.id,
        passed: false,
        score: 0,
        metrics: [],
        output: {},
        latencyMs: Date.now() - caseStartTime,
        error: (error as Error).message,
      });
    }
  }

  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;

  return {
    timestamp: new Date().toISOString(),
    totalTests: results.length,
    passed,
    failed,
    passRate: results.length > 0 ? passed / results.length : 0,
    avgLatencyMs: results.length > 0
      ? results.reduce((sum, r) => sum + r.latencyMs, 0) / results.length
      : 0,
    results,
    tagsRun: tags || [],
  };
}

// ============================================================================
// Evaluation Report
// ============================================================================

export function formatEvalReport(run: EvalRun): string {
  const lines: string[] = [];

  lines.push(`# Invoicify Agent Evaluation Report`);
  lines.push(`Timestamp: ${run.timestamp}`);
  lines.push(`Tests Run: ${run.totalTests}`);
  lines.push(`Passed: ${run.passed} ✅`);
  lines.push(`Failed: ${run.failed} ❌`);
  lines.push(`Pass Rate: ${(run.passRate * 100).toFixed(1)}%`);
  lines.push(`Avg Latency: ${run.avgLatencyMs.toFixed(0)}ms`);
  lines.push(``);

  // Failed tests
  const failedTests = run.results.filter(r => !r.passed);
  if (failedTests.length > 0) {
    lines.push(`## Failed Tests`);
    lines.push(``);
    for (const result of failedTests) {
      lines.push(`### ${result.testCaseId}`);
      lines.push(`Error: ${result.error || "Metrics mismatch"}`);
      if (result.metrics.length > 0) {
        lines.push(`Metrics:`);
        for (const metric of result.metrics) {
          const status = metric.passed ? "✅" : "❌";
          lines.push(`  ${status} ${metric.name}: expected=${metric.expected}, actual=${metric.actual}`);
        }
      }
      lines.push(``);
    }
  }

  // Performance summary
  lines.push(`## Performance`);
  const byTag: Record<string, { passed: number; total: number }> = {};
  // Group by tags would go here

  return lines.join("\n");
}

export function printEvalReport(run: EvalRun): void {
  console.log(formatEvalReport(run));
}

// ============================================================================
// Trial Runner (for stochastic evaluation)
 // ============================================================================

/**
 * Run multiple trials and aggregate results
 * Agents can be non-deterministic, so run multiple times
 */
export async function runTrials(
  options: EvalRunnerOptions & { trials: number; passThreshold: number }
): Promise<{
  overallPass: boolean;
  trials: EvalRun[];
  consistency: number;
}> {
  const allResults: EvalRun[] = [];

  for (let i = 0; i < options.trials; i++) {
    console.log(`Running trial ${i + 1}/${options.trials}...`);
    const run = await runEval({ ...options, runId: `trial-${i}` });
    allResults.push(run);
  }

  // Aggregate results
  const totalPassed = allResults.reduce((sum, run) => sum + run.passed, 0);
  const totalTests = allResults.reduce((sum, run) => sum + run.totalTests, 0);
  const overallPass = (totalPassed / totalTests) >= options.passThreshold;

  // Calculate consistency (what % of tests pass in all trials)
  const testPassCounts: Record<string, number> = {};
  for (const run of allResults) {
    for (const result of run.results) {
      if (!testPassCounts[result.testCaseId]) {
        testPassCounts[result.testCaseId] = 0;
      }
      if (result.passed) {
        testPassCounts[result.testCaseId]++;
      }
    }
  }

  const consistentCount = Object.values(testPassCounts).filter(
    count => count === options.trials
  ).length;
  const consistency = consistentCount / Object.keys(testPassCounts).length;

  return {
    overallPass,
    trials: allResults,
    consistency,
  };
}
