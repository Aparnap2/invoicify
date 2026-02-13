import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  getAuthorizationUrl,
  exchangeCodeForTokens,
  syncInvoiceToQuickBooks,
  getQuickBooksSyncStatus,
  queueForSync,
} from "../lib/quickbooks";
import { eq, sql, asc, desc } from "drizzle-orm";
import type { Env } from "../db";

const quickbooksRoutes = new Hono<{ Bindings: Env }>();

// Get OAuth authorization URL
quickbooksRoutes.get("/auth", async (c) => {
  const state = crypto.randomUUID();

  const authUrl = getAuthorizationUrl(state);
  return c.json({ authUrl, state });
});

// OAuth callback handler
quickbooksRoutes.get("/callback", async (c) => {
  const code = c.req.query("code");
  const state = c.req.query("state");
  const error = c.req.query("error");

  if (error) {
    return c.json({ error: `OAuth error: ${error}` }, 400);
  }

  if (!code || !state) {
    return c.json({ error: "Invalid OAuth callback: missing code or state" }, 400);
  }

  const tokens = await exchangeCodeForTokens(code);

  if (!tokens) {
    return c.json({ error: "Failed to exchange code for tokens" }, 500);
  }

  // Store tokens in database (in production, encrypt these!)
  const db = getDb(c.env);
  // For demo, we'll just return success
  // In production: await db.insert(qbTokens).values(...)

  return c.json({
    success: true,
    message: "QuickBooks connected successfully",
    realmId: tokens.realmId,
  });
});

// Sync invoice to QuickBooks
quickbooksRoutes.post("/sync/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const result = await syncInvoiceToQuickBooks(env, invoiceId);

  if (!result.success) {
    return c.json({ error: result.error }, 500);
  }

  return c.json({
    success: true,
    quickbooksId: result.quickbooksId,
  });
});

// Get sync status for invoice
quickbooksRoutes.get("/status/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const status = await getQuickBooksSyncStatus(env, invoiceId);

  return c.json(status);
});

// Queue invoice for sync
quickbooksRoutes.post("/queue/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");

  const result = await queueForSync(env, invoiceId);

  return c.json(result);
});

// Get sync queue status
quickbooksRoutes.get("/queue", async (c) => {
  const db = getDb(c.env);
  const statusFilter = c.req.query("status");

  const queue = await db
    .select()
    .from(schema.syncQueue)
    .where(statusFilter ? eq(schema.syncQueue.status, statusFilter) : undefined)
    .orderBy(desc(schema.syncQueue.scheduledAt))
    .limit(100);

  const counts = await db
    .select({
      pending: sql<number>`count(case when ${schema.syncQueue.status} = 'PENDING' then 1 end)`,
      processing: sql<number>`count(case when ${schema.syncQueue.status} = 'PROCESSING' then 1 end)`,
      completed: sql<number>`count(case when ${schema.syncQueue.status} = 'COMPLETED' then 1 end)`,
      failed: sql<number>`count(case when ${schema.syncQueue.status} = 'FAILED' then 1 end)`,
    })
    .from(schema.syncQueue);

  return c.json({
    items: queue,
    counts: counts[0] || { pending: 0, processing: 0, completed: 0, failed: 0 },
  });
});

// Process sync queue (would be called by cron)
quickbooksRoutes.post("/queue/process", async (c) => {
  const env = c.env;
  const db = getDb(env);

  // Get pending items
  const pending = await db
    .select()
    .from(schema.syncQueue)
    .where(eq(schema.syncQueue.status, "PENDING"))
    .orderBy(asc(schema.syncQueue.scheduledAt))
    .limit(10);

  const results = {
    processed: 0,
    success: 0,
    failed: 0,
    errors: [] as string[],
  };

  for (const item of pending) {
    // Mark as processing
    await db
      .update(schema.syncQueue)
      .set({
        status: "PROCESSING",
        attempts: (item.attempts || 0) + 1,
      })
      .where(eq(schema.syncQueue.id, item.id));

    try {
      if (item.entityType === "invoice") {
        const result = await syncInvoiceToQuickBooks(env, item.entityId);

        if (result.success) {
          await db
            .update(schema.syncQueue)
            .set({
              status: "COMPLETED",
              processedAt: new Date().toISOString(),
            })
            .where(eq(schema.syncQueue.id, item.id));
          results.success++;
        } else {
          throw new Error(result.error || "Sync failed");
        }
      }
    } catch (err) {
      const errorMsg = String(err);
      await db
        .update(schema.syncQueue)
        .set({
          status: "FAILED",
          lastError: errorMsg,
        })
        .where(eq(schema.syncQueue.id, item.id));
      results.failed++;
      results.errors.push(`${item.entityId}: ${errorMsg}`);
    }

    results.processed++;
  }

  return c.json(results);
});

// Get QuickBooks connection status
quickbooksRoutes.get("/connection", async (c) => {
  // In production, check if tokens exist and are valid
  // For demo, return disconnected state
  return c.json({
    connected: false,
    environment: "sandbox",
    message: "QuickBooks not connected. Use /auth to initiate OAuth flow.",
  });
});

export { quickbooksRoutes };
