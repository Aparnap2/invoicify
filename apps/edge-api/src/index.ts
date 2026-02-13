import { Hono } from "hono";
import { cors } from "hono/cors";
import { secureHeaders } from "hono/secure-headers";

import { invoicesRoutes } from "./routes/invoices";
import { internalRoutes } from "./routes/internal";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

// Security headers
app.use("/*", secureHeaders());

// CORS for frontend
app.use("/*", cors({
  origin: ["http://localhost:3000", "https://invoicify.pages.dev"],
  allowMethods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
  allowHeaders: ["Content-Type", "Authorization"],
  credentials: false,
}));

// Health check
app.get("/health", (c) => {
  return c.json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    version: "1.0.0"
  });
});

// API version
app.get("/api/v1", (c) => {
  return c.json({ version: "1.0.0", name: "Invoicify API" });
});

// Internal R2 proxy for agent-core to download PDFs
app.get("/internal/r2/*", async (c) => {
  const key = c.req.path.replace('/internal/r2/', '');

  try {
    const object = await c.env.R2_BUCKET.get(key);

    if (!object) {
      return c.json({ error: 'Object not found' }, 404);
    }

    return new Response(object.body, {
      headers: {
        'Content-Type': object.httpMetadata?.contentType || 'application/pdf',
        'Cache-Control': 'private, max-age=3600',
      },
    });
  } catch (error) {
    console.error('R2 proxy error:', error);
    return c.json({ error: 'Failed to retrieve object' }, 500);
  }
});

// Mount routes
app.route("/api/v1/invoices", invoicesRoutes);
app.route("/internal", internalRoutes);

// Error handling
app.onError((err, c) => {
  console.error("Unhandled error:", err);
  return c.json(
    { error: "Internal server error", message: err.message },
    500
  );
});

// Export handlers
export default {
  fetch: app.fetch,

  // Scheduled jobs
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    console.log("Cron triggered at", new Date().toISOString());
    // Future: Cleanup or background sync
  },
};
