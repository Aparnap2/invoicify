/**
 * Row-Level Security (RLS) Module
 *
 * Multi-tenant access control for Invoicify.
 *
 * Usage:
 *   import { withRLS, canViewInvoice, maskData } from './lib/rls';
 *
 *   app.use(withRLS());
 *
 *   app.get('/invoices', async (c) => {
 *     const context = getRLSContext(c);
 *     const invoices = await db.select().from(invoicesTable);
 *     const filtered = filterByRLS(invoices, context, 'invoice');
 *     return c.json(filtered);
 *   });
 */

export * from './types.js';
export * from './policies.js';
export * from './middleware.js';
export * from './bindings.js';
