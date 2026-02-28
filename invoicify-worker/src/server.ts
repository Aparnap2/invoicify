/**
 * Azure Container Apps entry point.
 * Runs the Hono app on a plain Node.js HTTP server.
 * Replaces wrangler.toml's `fetch` export handler.
 *
 * Cloudflare primitives replaced:
 *   D1          → postgres (via DATABASE_URL env)
 *   R2          → @azure/storage-blob (via AZURE_STORAGE_*)
 *   KV          → in-memory Map with TTL (good enough at this scale)
 *   Queues      → azure-storage-queue (enqueue only; consumer = agent-core)
 *   DurableObjs → stateless + Postgres (no sticky routing needed)
 */

import { serve } from '@hono/node-server';
import { Pool } from 'pg';
import { BlobServiceClient } from '@azure/storage-blob';
import { QueueServiceClient } from '@azure/storage-queue';
import { app } from './app';
import type { Env } from './types';

const PORT = parseInt(process.env.PORT ?? '8787', 10);

// ── Azure service clients (replaces Cloudflare bindings) ─────────────────────

const db = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes('azure') ? { rejectUnauthorized: false } : false,
  max: 10,
  idleTimeoutMillis: 30_000,
});

const blobClient = process.env.AZURE_STORAGE_CONNECTION_STRING
  ? BlobServiceClient.fromConnectionString(process.env.AZURE_STORAGE_CONNECTION_STRING)
  : null;

const queueClient = process.env.AZURE_STORAGE_CONNECTION_STRING
  ? QueueServiceClient.fromConnectionString(process.env.AZURE_STORAGE_CONNECTION_STRING)
  : null;

// Simple in-memory KV with TTL (replaces Cloudflare KV for session/cache data)
const kvStore = new Map<string, { value: string; expires: number }>();
const kv = {
  async get(key: string): Promise<string | null> {
    const entry = kvStore.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expires) { kvStore.delete(key); return null; }
    return entry.value;
  },
  async put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> {
    const ttlMs = (options?.expirationTtl ?? 3600) * 1000;
    kvStore.set(key, { value, expires: Date.now() + ttlMs });
  },
  async delete(key: string): Promise<void> { kvStore.delete(key); },
};

// ── Build env bindings compatible with existing Hono route code ───────────────
const env: Partial<Env> = {
  DB: db as any,                          // routes use env.DB.prepare() — see adapters
  INVOICES_BUCKET: blobClient as any,     // routes use env.INVOICES_BUCKET.put()
  INVOICE_QUEUE: queueClient as any,      // routes use env.INVOICE_QUEUE.send()
  SESSION_KV: kv as any,
  ENVIRONMENT: (process.env.ENVIRONMENT ?? 'development') as any,
  AGENT_CORE_URL: process.env.AGENT_CORE_URL ?? 'http://invoicify-api',
  OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? '',
  GROQ_API_KEY: process.env.GROQ_API_KEY ?? '',
  SLACK_BOT_TOKEN: process.env.SLACK_BOT_TOKEN ?? '',
  SLACK_SIGNING_SECRET: process.env.SLACK_SIGNING_SECRET ?? '',
  QUICKBOOKS_CLIENT_ID: process.env.QUICKBOOKS_CLIENT_ID ?? '',
  QUICKBOOKS_CLIENT_SECRET: process.env.QUICKBOOKS_CLIENT_SECRET ?? '',
  QUICKBOOKS_REDIRECT_URI: process.env.QUICKBOOKS_REDIRECT_URI ?? '',
};

serve(
  {
    fetch: (req) => app.fetch(req, env as Env),
    port: PORT,
  },
  (info) => {
    console.log(JSON.stringify({
      level: 'INFO',
      msg: 'invoicify-worker started',
      port: info.port,
      environment: process.env.ENVIRONMENT ?? 'development',
    }));
  },
);

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log(JSON.stringify({ level: 'INFO', msg: 'SIGTERM received, shutting down' }));
  await db.end();
  process.exit(0);
});
