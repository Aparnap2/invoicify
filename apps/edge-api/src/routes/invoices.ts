import { Hono } from 'hono';
import type { Env } from '../db';

const invoicesRoutes = new Hono<{ Bindings: Env }>();

// Helper to generate presigned URL for R2 object
function generatePresignedUrl(r2Key: string, baseUrl: string = 'http://localhost:8787'): string {
  // For local dev, return direct URL to internal proxy
  // For production, implement proper R2 presigned URL logic
  return `${baseUrl}/internal/r2/${r2Key}`;
}

// POST /api/v1/invoices - Upload Invoice
invoicesRoutes.post('/', async (c) => {
  try {
    const formData = await c.req.formData();
    const file = formData.get('file') as unknown as File;

    if (!file || file.type !== 'application/pdf') {
      return c.json({ error: 'Invalid file. PDF required.' }, 400);
    }

    // Generate trace_id
    const traceId = crypto.randomUUID();
    const date = new Date().toISOString().split('T')[0];
    const r2Key = `raw/${date}/${traceId}.pdf`;

    // Upload to R2
    await c.env.R2_BUCKET.put(r2Key, file.stream());
    console.log(`📦 Uploaded to R2: ${r2Key}`);

    // Create record in D1
    await c.env.DB.prepare(`
      INSERT INTO invoices (id, vendor_id, vendor_name, invoice_number, total_amount, status, r2_key_raw, created_at)
      VALUES (?, '', '', '', 0, 'PENDING', ?, datetime('now'))
    `).bind(traceId, r2Key).run();
    console.log(`💾 Created D1 record: ${traceId}`);

    // Generate presigned URL for agent-core to download PDF
    const presignedUrl = generatePresignedUrl(r2Key);

    // Start Agent Pipeline via Webhook
    try {
      fetch('http://localhost:8000/process-invoice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trace_id: traceId,
          r2_key: r2Key,
          r2_presigned_url: presignedUrl,
        }),
      }).catch(err => console.error('Agent webhook failed:', err));

      console.log(`⚡ Agent pipeline triggered via webhook for: ${traceId}`);
    } catch (error) {
      console.error('Failed to trigger agent:', error);
    }

    return c.json({
      trace_id: traceId,
      status: 'PENDING',
      status_url: `/api/v1/invoices/${traceId}`,
    }, 202);

  } catch (error) {
    console.error('Upload error:', error);
    return c.json({ error: 'Internal server error' }, 500);
  }
});

// POST /api/v1/invoices/:id/approve - HITL Approval
invoicesRoutes.post('/:id/approve', async (c) => {
  const traceId = c.req.param('id');
  const body = await c.req.json();
  const userId = body.user_id || 'unknown';

  try {
    // Send signal to Agent via Webhook
    await fetch(`http://localhost:8000/approve-invoice/${traceId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });

    // Update D1
    await c.env.DB.prepare(`
      UPDATE invoices SET status = 'APPROVED', updated_at = datetime('now') WHERE id = ?
    `).bind(traceId).run();

    // Log audit
    await c.env.DB.prepare(`
      INSERT INTO audit_logs (id, action, resource_type, resource_id, actor_user_id, organization_id, created_at)
      VALUES (?, 'HITL_APPROVED', 'invoice', ?, ?, 'org_1', datetime('now'))
    `).bind(crypto.randomUUID(), traceId, userId).run();

    return c.json({ status: 'APPROVED', message: 'Invoice approved' });

  } catch (error) {
    console.error('Approval error:', error);
    return c.json({ error: 'Failed to approve invoice' }, 500);
  }
});

// GET /api/v1/invoices/:id - Get Status
invoicesRoutes.get('/:id', async (c) => {
  const traceId = c.req.param('id');

  try {
    const result = await c.env.DB.prepare(`
      SELECT * FROM invoices WHERE id = ?
    `).bind(traceId).first();

    if (!result) {
      return c.json({ error: 'Invoice not found' }, 404);
    }

    // Workflow status check removed (no longer using Temporal)
    // In the future, this could fetch from agent-core if needed
    const workflowStatus = { status: 'DECOUPLED_FROM_TEMPORAL' };

    return c.json({
      invoice: result,
      workflow: workflowStatus,
    });

  } catch (error) {
    console.error('Status error:', error);
    return c.json({ error: 'Internal server error' }, 500);
  }
});

export { invoicesRoutes };
