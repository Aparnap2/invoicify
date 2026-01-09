import { Hono } from "hono";
import { cors } from "hono/cors";
import { getDb } from "./db";
import { invoicesRoutes } from "./routes/invoices";
import { extractRoutes } from "./routes/extract";
import { uploadRoutes } from "./routes/upload";
import { riskRoutes } from "./routes/risk";
import type { Env } from "./db";

const app = new Hono<{ Bindings: Env }>();

// CORS for frontend
app.use("/*", cors({
  origin: ["http://localhost:3000", "https://invoicify.pages.dev"],
  allowMethods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
  allowHeaders: ["Content-Type", "Authorization"],
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
