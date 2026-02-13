import { Hono } from 'hono';
import type { Env } from '../db';

const internalRoutes = new Hono<{ Bindings: Env }>();

// Internal-only endpoint (should be protected in production)
internalRoutes.post('/update-status', async (c) => {
    try {
        const body = await c.req.json<{
            trace_id: string;
            status: string;
            quickbooks_bill_id?: string;
            error_message?: string;
            extracted_data?: any;
        }>();

        const { trace_id, status, quickbooks_bill_id, error_message, extracted_data } = body;

        if (!trace_id || !status) {
            return c.json({ error: 'trace_id and status required' }, 400);
        }

        // Prepare update fields
        let vendorName = extracted_data?.vendor_name || null;
        let invoiceNumber = extracted_data?.invoice_number || null;
        let totalAmount = extracted_data?.total_amount || 0;
        let dueDate = extracted_data?.due_date || null;
        let invoiceDate = extracted_data?.invoice_date || null;

        // Update D1
        await c.env.DB.prepare(`
      UPDATE invoices 
      SET status = ?, 
          quickbooks_id = ?,
          error_message = ?,
          extracted_data = ?,
          vendor_name = COALESCE(?, vendor_name),
          invoice_number = COALESCE(?, invoice_number),
          total_amount = CASE WHEN ? > 0 THEN ? ELSE total_amount END,
          due_date = COALESCE(?, due_date),
          invoice_date = COALESCE(?, invoice_date),
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(
            status,
            quickbooks_bill_id || null,
            error_message || null,
            extracted_data ? JSON.stringify(extracted_data) : null,
            vendorName,
            invoiceNumber,
            totalAmount,
            totalAmount,
            dueDate,
            invoiceDate,
            trace_id
        ).run();

        // Log to audit table
        await c.env.DB.prepare(`
      INSERT INTO audit_logs (id, resource_id, resource_type, action, actor_user_id, organization_id, created_at)
      VALUES (?, ?, 'invoice', ?, 'agent', 'org_1', datetime('now'))
    `).bind(
            crypto.randomUUID(),
            trace_id,
            `STATUS_UPDATE_${status}`
        ).run();

        console.log(`✅ Updated invoice ${trace_id} to ${status}`);

        return c.json({ success: true, trace_id, status });

    } catch (error) {
        console.error('Internal status update failed:', error);
        return c.json({ error: 'Failed to update status' }, 500);
    }
});

// --- Trust Battery Endpoints ---

internalRoutes.get('/trust-battery/:vendorId', async (c) => {
    const vendorId = c.req.param('vendorId');
    const record = await c.env.DB.prepare(`
    SELECT * FROM trust_battery WHERE vendor_id = ?
  `).bind(vendorId).first();

    return c.json(record || null);
});

internalRoutes.post('/trust-battery', async (c) => {
    const body = await c.req.json<{
        vendor_id: string;
        trust_level: number;
        consecutive_accurate: number;
        consecutive_errors: number;
        total_decisions: number;
        accurate_decisions: number;
        auto_approve_threshold: number;
    }>();

    await c.env.DB.prepare(`
    INSERT INTO trust_battery (
      id, vendor_id, trust_level, consecutive_accurate, 
      consecutive_errors, total_decisions, accurate_decisions, 
      auto_approve_threshold, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(vendor_id) DO UPDATE SET
      trust_level = excluded.trust_level,
      consecutive_accurate = excluded.consecutive_accurate,
      consecutive_errors = excluded.consecutive_errors,
      total_decisions = excluded.total_decisions,
      accurate_decisions = excluded.accurate_decisions,
      auto_approve_threshold = excluded.auto_approve_threshold,
      updated_at = datetime('now')
  `).bind(
        crypto.randomUUID(), body.vendor_id, body.trust_level,
        body.consecutive_accurate, body.consecutive_errors,
        body.total_decisions, body.accurate_decisions,
        body.auto_approve_threshold
    ).run();

    return c.json({ success: true });
});

export { internalRoutes };
