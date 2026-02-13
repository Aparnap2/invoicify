import { Hono } from "hono";
import { cors } from "hono/cors";
import { secureHeaders } from "hono/secure-headers";
import { getDb } from "./db";
import { invoicesRoutes } from "./routes/invoices";
import { extractRoutes } from "./routes/extract";
import { uploadRoutes } from "./routes/upload";
import { riskRoutes } from "./routes/risk";
import { vendorTrustRoutes } from "./routes/vendor-trust";
import { paymentRoutes } from "./routes/payments";
import { workflowRoutes } from "./routes/workflow";
import { trustBatteryRoutes, strategyRoutes } from "./routes/trust-battery";
import { quickbooksRoutes } from "./routes/quickbooks";
import { slackRoutes } from "./routes/slack";
import { seedRoutes } from "./routes/seed";
import { evalRoutes } from "./routes/eval";
import { billingRoutes } from "./routes/billing";
import { apiKeysRoutes } from "./routes/api-keys";
import { auditLogsRoutes } from "./routes/audit-logs";
import type { Env } from "./db";

const app = new Hono<{ Bindings: Env }>();

// Security headers
app.use("/*", secureHeaders());

// CORS for frontend
app.use("/*", cors({
  origin: ["http://localhost:3000", "https://invoicify.pages.dev"],
  allowMethods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
  allowHeaders: ["Content-Type", "Authorization"],
  credentials: false,  // Explicitly deny credentials for security
}));

// Health check
app.get("/health", (c) => {
  return c.json({ status: "healthy", timestamp: new Date().toISOString() });
});

// API version
app.get("/api/v1", (c) => {
  return c.json({ version: "1.0.0", name: "Invoicify API" });
});

// Mount routes
app.route("/api/v1/invoices", invoicesRoutes);
app.route("/api/v1/extract", extractRoutes);
app.route("/api/v1/upload", uploadRoutes);
app.route("/api/v1/risk", riskRoutes);
app.route("/api/v1/vendor-trust", vendorTrustRoutes);
app.route("/api/v1/payments", paymentRoutes);
app.route("/api/v1/workflow", workflowRoutes);
app.route("/api/v1/trust-battery", trustBatteryRoutes);
app.route("/api/v1/strategy", strategyRoutes);
app.route("/api/v1/quickbooks", quickbooksRoutes);
app.route("/api/v1/slack", slackRoutes);
app.route("/api/v1/seed", seedRoutes);
app.route("/api/v1/eval", evalRoutes);
app.route("/api/v1/billing", billingRoutes);
app.route("/api/v1/api-keys", apiKeysRoutes);
app.route("/api/v1/audit-logs", auditLogsRoutes);

// Middleware to block seed/eval routes in production
app.use("/api/v1/seed/*", async (c, next) => {
  if (c.env?.ENVIRONMENT === "production") {
    return c.json({ error: "Not available in production" }, 404);
  }
  return next();
});

app.use("/api/v1/eval/*", async (c, next) => {
  if (c.env?.ENVIRONMENT === "production") {
    return c.json({ error: "Not available in production" }, 404);
  }
  return next();
});

// Error handling
app.onError((err, c) => {
  console.error("Unhandled error:", err);
  return c.json(
    { error: "Internal server error", message: err.message },
    500
  );
});

export default {
  fetch: app.fetch,
  async scheduled(controller: any, env: Env, ctx: ExecutionContext) {
    // Handle cron jobs for sync, cleanup, etc.
    console.log("Cron triggered at", new Date().toISOString());
  },
};
