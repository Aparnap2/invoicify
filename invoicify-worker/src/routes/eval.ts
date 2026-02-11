/**
 * Evaluation API Endpoints
 *
 * POST /api/v1/eval/workflow - Run workflow agent evaluation
 * POST /api/v1/eval/slack - Run Slack Intern evaluation
 * GET /api/v1/eval/report - Get evaluation report
 */

import { Hono } from "hono";
import {
  workflowTestCases,
  slackInternTestCases,
  runEval,
  runTrials,
  printEvalReport,
  formatEvalReport,
} from "../lib/eval";
import { runWorkflow } from "../lib/workflow";
import { processInternQuery } from "../lib/slack-intern";
import { logger } from "../lib/logger";
import type { Env } from "../db";

const evalRoutes = new Hono<{ Bindings: Env }>();

/**
 * Run workflow agent evaluation
 * POST /api/v1/eval/workflow
 */
evalRoutes.post("/workflow", async (c) => {
  const body = await c.req.json<{
    tags?: string[];
    trials?: number;
    passThreshold?: number;
  }>();

  const { tags, trials = 1, passThreshold = 0.9 } = body || {};

  try {
    if (trials > 1) {
      // Run multiple trials for stochastic evaluation
      const trialResults = await runTrials({
        testCases: workflowTestCases,
        runWorkflow: async (input) => {
          const state = createInitialState(input);
          return runWorkflow(c.env, state);
        },
        tags,
        trials,
        passThreshold,
      });

      return c.json({
        success: true,
        overallPass: trialResults.overallPass,
        consistency: trialResults.consistency,
        trialsRun: trials,
        passRate: trialResults.trials.reduce(
          (sum, t) => sum + t.passed / t.totalTests, 0
        ) / trials,
      });
    }

    // Single trial
    const run = await runEval({
      testCases: workflowTestCases,
      runWorkflow: async (input) => {
        const state = createInitialState(input);
        return runWorkflow(c.env, state);
      },
      tags,
    });

    logger.info("Workflow evaluation completed", {
      passed: run.passed,
      failed: run.failed,
      passRate: run.passRate,
    });

    return c.json({
      success: true,
      run,
      report: formatEvalReport(run),
    });
  } catch (error) {
    logger.error("Workflow evaluation failed", { error: (error as Error).message });
    return c.json({ error: "Evaluation failed" }, 500);
  }
});

/**
 * Run Slack Intern evaluation
 * POST /api/v1/eval/slack
 */
evalRoutes.post("/slack", async (c) => {
  const body = await c.req.json<{
    tags?: string[];
  }>();

  const { tags } = body || {};

  try {
    const run = await runEval({
      testCases: slackInternTestCases,
      runSlackQuery: async (query) => {
        const response = await processInternQuery(c.env, query);
        return { text: response.text, blocks: response.blocks };
      },
      tags,
    });

    logger.info("Slack Intern evaluation completed", {
      passed: run.passed,
      failed: run.failed,
      passRate: run.passRate,
    });

    return c.json({
      success: true,
      run,
      report: formatEvalReport(run),
    });
  } catch (error) {
    logger.error("Slack Intern evaluation failed", { error: (error as Error).message });
    return c.json({ error: "Evaluation failed" }, 500);
  }
});

/**
 * Run full evaluation suite
 * POST /api/v1/eval/all
 */
evalRoutes.post("/all", async (c) => {
  const body = await c.req.json<{
    trials?: number;
    tags?: string[];
  }>();

  const { trials = 1, tags } = body || {};

  try {
    const [workflowRun, slackRun] = await Promise.all([
      runEval({
        testCases: workflowTestCases,
        runWorkflow: async (input) => {
          const state = createInitialState(input);
          return runWorkflow(c.env, state);
        },
        tags,
      }),
      runEval({
        testCases: slackInternTestCases,
        runSlackQuery: async (query) => {
          const response = await processInternQuery(c.env, query);
          return { text: response.text, blocks: response.blocks };
        },
        tags,
      }),
    ]);

    const combinedPassRate =
      (workflowRun.passed + slackRun.passed) /
      (workflowRun.totalTests + slackRun.totalTests);

    return c.json({
      success: true,
      workflow: {
        passed: workflowRun.passed,
        total: workflowRun.totalTests,
        passRate: workflowRun.passRate,
      },
      slack: {
        passed: slackRun.passed,
        total: slackRun.totalTests,
        passRate: slackRun.passRate,
      },
      combined: {
        passed: workflowRun.passed + slackRun.passed,
        total: workflowRun.totalTests + slackRun.totalTests,
        passRate: combinedPassRate,
      },
    });
  } catch (error) {
    logger.error("Full evaluation failed", { error: (error as Error).message });
    return c.json({ error: "Evaluation failed" }, 500);
  }
});

/**
 * Get test case library
 * GET /api/v1/eval/testcases
 */
evalRoutes.get("/testcases", async (c) => {
  return c.json({
    workflow: workflowTestCases,
    slack: slackInternTestCases,
    total: workflowTestCases.length + slackInternTestCases.length,
  });
});

/**
 * Get evaluation report
 * GET /api/v1/eval/report
 */
evalRoutes.get("/report", async (c) => {
  const format = c.req.query("format") || "json";

  // In production, you'd fetch the last N evaluation runs from KV/D1
  // For now, return a template
  const report = {
    lastRun: null,
    summary: {
      totalRuns: 0,
      avgPassRate: 0,
      trend: "stable",
    },
    testCounts: {
      workflow: workflowTestCases.length,
      slack: slackInternTestCases.length,
      p0: workflowTestCases.filter(t => t.priority === "p0").length,
      p1: workflowTestCases.filter(t => t.priority === "p1").length,
      p2: workflowTestCases.filter(t => t.priority === "p2").length,
    },
  };

  if (format === "markdown") {
    return c.text(formatEvalReport(report as any));
  }

  return c.json(report);
});

export { evalRoutes };
