/**
 * Hono app exported separately so both wrangler (Cloudflare) and
 * server.ts (Azure/Node) can import it without circular deps.
 */
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { secureHeaders } from 'hono/secure-headers';
import { invoicesRoutes } from './routes/invoices';
import { extractRoutes } from './routes/extract';
import { uploadRoutes } from './routes/upload';
import { riskRoutes } from './routes/risk';
import { vendorTrustRoutes } from './routes/vendor-trust';
import { paymentRoutes } from './routes/payments';
import { workflowRoutes } from './routes/workflow';
import { trustBatteryRoutes, strategyRoutes } from './routes/trust-battery';
import { quickbooksRoutes } from './routes/quickbooks';
import { slackRoutes } from './routes/slack';
import { seedRoutes } from './routes/seed';
import { evalRoutes } from './routes/eval';
import { billingRoutes } from './routes/billing';
import { apiKeysRoutes } from './routes/api-keys';
import { auditLogsRoutes } from './routes/audit-logs';
import type { Env } from './types';

export const app = new Hono<{ Bindings: Env }>();

app.use('/*', secureHeaders());
app.use('/*', cors({
  origin: [
    'http://localhost:3000',
    'https://invoicify.pages.dev',
    process.env.FRONTEND_URL ?? '',
  ].filter(Boolean),
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization'],
  credentials: false,
}));

app.get('/health', (c) =>
  c.json({ status: 'healthy', timestamp: new Date().toISOString(), version: '1.0.0' }),
);
app.get('/api/v1', (c) => c.json({ version: '1.0.0', name: 'Invoicify API' }));

app.route('/api/v1/invoices', invoicesRoutes);
app.route('/api/v1/extract', extractRoutes);
app.route('/api/v1/upload', uploadRoutes);
app.route('/api/v1/risk', riskRoutes);
app.route('/api/v1/vendor-trust', vendorTrustRoutes);
app.route('/api/v1/payments', paymentRoutes);
app.route('/api/v1/workflow', workflowRoutes);
app.route('/api/v1/trust-battery', trustBatteryRoutes);
app.route('/api/v1/strategy', strategyRoutes);
app.route('/api/v1/quickbooks', quickbooksRoutes);
app.route('/api/v1/slack', slackRoutes);
app.route('/api/v1/seed', seedRoutes);
app.route('/api/v1/eval', evalRoutes);
app.route('/api/v1/billing', billingRoutes);
app.route('/api/v1/api-keys', apiKeysRoutes);
app.route('/api/v1/audit-logs', auditLogsRoutes);

app.use('/api/v1/seed/*', async (c, next) => {
  if ((c.env as any)?.ENVIRONMENT === 'production') {
    return c.json({ error: 'Not available in production' }, 404);
  }
  return next();
});

app.use('/api/v1/eval/*', async (c, next) => {
  if ((c.env as any)?.ENVIRONMENT === 'production') {
    return c.json({ error: 'Not available in production' }, 404);
  }
  return next();
});

app.onError((err, c) => {
  console.error(JSON.stringify({ level: 'ERROR', msg: err.message, stack: err.stack }));
  return c.json({ error: 'Internal server error', message: err.message }, 500);
});

// Keep Cloudflare export intact — wrangler still works for local dev
export default {
  fetch: app.fetch,
};
