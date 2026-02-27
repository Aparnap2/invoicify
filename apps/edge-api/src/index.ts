/**
 * Edge API - Cloudflare Workers with Hono
 * 
 * Handles invoice submission at the edge:
 * - Auth via Entra ID B2C JWT
 * - Rate limiting (10 invoices/min per tenant)
 * - R2 storage for PDFs
 * - D1 metadata storage
 * - Event Grid publishing
 */

import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { bearerAuth } from 'hono/bearer-auth'
import { z } from 'zod'
import { zValidator } from '@hono/zod-validator'
import { v4 as uuidv4 } from 'uuid'

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export interface Env {
  // Cloudflare bindings
  R2: R2Bucket
  DB: D1Database
  EVENT_GRID_ENDPOINT: string
  EVENT_GRID_KEY: string
  
  // Auth
  ENTRA_JWT_ISSUER: string
  ENTRA_JWT_AUDIENCE: string
  
  // Rate limiting
  KV_STORE: KVNamespace
}

// ─────────────────────────────────────────────────────────────────────────────
// VALIDATION SCHEMAS
// ─────────────────────────────────────────────────────────────────────────────

const SubmitInvoiceSchema = z.object({
  tenant_id: z.string().uuid(),
  file_name: z.string().min(1).max(255),
  file_content: z.string(), // base64 encoded
  vendor_phone: z.string().optional(),
  language: z.string().default('hi-IN'),
  metadata: z.record(z.string(), z.any()).optional(),
})

const GetInvoiceSchema = z.object({
  tenant_id: z.string().uuid(),
})

const ListInvoicesSchema = z.object({
  tenant_id: z.string().uuid(),
  status: z.enum(['SUBMITTED', 'EXTRACTING', 'VALIDATING', 'APPROVED', 'PENDING_REVIEW', 'REJECTED']).optional(),
  limit: z.number().default(50),
})

// ─────────────────────────────────────────────────────────────────────────────
// ROUTES
// ─────────────────────────────────────────────────────────────────────────────

const invoiceRouter = new Hono<{ Bindings: Env }>()

// POST /invoices — submit invoice for processing
invoiceRouter.post(
  '/',
  zValidator('json', SubmitInvoiceSchema),
  async (c) => {
    const body = c.req.valid('json')
    const traceId = uuidv4()
    const invoiceId = uuidv4()
    
    // 1. Upload to R2
    const r2Key = `${body.tenant_id}/${invoiceId}/${body.file_name}`
    const fileBuffer = Buffer.from(body.file_content, 'base64')
    
    await c.env.R2.put(r2Key, fileBuffer, {
      httpMetadata: { contentType: 'application/pdf' },
      customMetadata: {
        traceId,
        tenantId: body.tenant_id,
        vendorPhone: body.vendor_phone || '',
        language: body.language,
      },
    })
    
    // 2. Write metadata to D1
    await c.env.DB.prepare(`
      INSERT INTO invoice_submissions (id, tenant_id, trace_id, r2_key, file_name, file_size, status)
      VALUES (?, ?, ?, ?, ?, ?, 'SUBMITTED')
    `).bind(
      invoiceId,
      body.tenant_id,
      traceId,
      r2Key,
      body.file_name,
      fileBuffer.length
    ).run()
    
    // 3. Publish to Azure Event Grid
    await publishEvent(c.env, {
      id: traceId,
      subject: `invoices/${invoiceId}`,
      eventType: 'invoice.submitted',
      dataVersion: '1.0',
      data: {
        invoice_id: invoiceId,
        trace_id: traceId,
        tenant_id: body.tenant_id,
        r2_url: `https://${c.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${r2Key}`,
        vendor_phone: body.vendor_phone,
        language: body.language,
        metadata: body.metadata,
      },
    })
    
    // 4. Log submission
    console.log('invoice_submitted', {
      invoice_id: invoiceId,
      trace_id: traceId,
      tenant_id: body.tenant_id,
      file_size: fileBuffer.length,
    })
    
    return c.json({
      invoice_id: invoiceId,
      trace_id: traceId,
      status: 'SUBMITTED',
    }, 201)
  }
)

// GET /invoices/:id — get invoice status
invoiceRouter.get(
  '/:id',
  zValidator('query', GetInvoiceSchema),
  async (c) => {
    const invoiceId = c.req.param('id')
    const { tenant_id } = c.req.valid('query')
    
    const row = await c.env.DB.prepare(`
      SELECT * FROM invoice_submissions
      WHERE id = ? AND tenant_id = ?
    `).bind(invoiceId, tenantId).first()
    
    if (!row) {
      return c.json({ error: 'Not found' }, 404)
    }
    
    return c.json(row)
  }
)

// GET /invoices — list invoices
invoiceRouter.get(
  '/',
  zValidator('query', ListInvoicesSchema),
  async (c) => {
    const { tenant_id, status, limit } = c.req.valid('query')
    
    let query = `
      SELECT * FROM invoice_submissions
      WHERE tenant_id = ?
    `
    const params: any[] = [tenant_id]
    
    if (status) {
      query += ` AND status = ?`
      params.push(status)
    }
    
    query += ` ORDER BY submitted_at DESC LIMIT ?`
    params.push(limit)
    
    const { results } = await c.env.DB.prepare(query).bind(...params).all()
    
    return c.json({
      invoices: results,
      total: results.length,
    })
  }
)

// GET /invoices/pending-review — list HITL pending invoices
invoiceRouter.get(
  '/pending-review',
  zValidator('query', z.object({ tenant_id: z.string().uuid() })),
  async (c) => {
    const { tenant_id } = c.req.valid('query')
    
    const { results } = await c.env.DB.prepare(`
      SELECT * FROM invoice_submissions
      WHERE tenant_id = ? AND status = 'PENDING_REVIEW'
      ORDER BY submitted_at DESC
      LIMIT 50
    `).bind(tenant_id).all()
    
    return c.json({
      invoices: results,
      total: results.length,
    })
  }
)

// ─────────────────────────────────────────────────────────────────────────────
// HEALTH & METRICS
// ─────────────────────────────────────────────────────────────────────────────

const healthRouter = new Hono<{ Bindings: Env }>()

healthRouter.get('/health', async (c) => {
  // Check R2
  let r2Status = 'ok'
  try {
    await c.env.R2.get('health-check')
  } catch {
    r2Status = 'error'
  }
  
  // Check D1
  let d1Status = 'ok'
  try {
    await c.env.DB.prepare('SELECT 1').first()
  } catch {
    d1Status = 'error'
  }
  
  const status = r2Status === 'ok' && d1Status === 'ok' ? 'ok' : 'degraded'
  
  return c.json({
    status,
    services: {
      r2: r2Status,
      d1: d1Status,
    },
    timestamp: new Date().toISOString(),
  })
})

healthRouter.get('/metrics', async (c) => {
  // Get submission counts from D1
  const { total } = await c.env.DB.prepare(`
    SELECT COUNT(*) as total FROM invoice_submissions
  `).first()
  
  const { pending } = await c.env.DB.prepare(`
    SELECT COUNT(*) as pending FROM invoice_submissions WHERE status = 'PENDING_REVIEW'
  `).first()
  
  return c.json({
    invoices_total: total,
    invoices_pending_review: pending,
    timestamp: new Date().toISOString(),
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// MIDDLEWARE
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Rate limiting middleware
 * Limits to 10 invoices per minute per tenant
 */
const rateLimiter = async (c: any, next: any) => {
  const tenantId = c.req.header('X-Tenant-ID')
  if (!tenantId) {
    return c.json({ error: 'X-Tenant-ID header required' }, 400)
  }
  
  const key = `rate:${tenantId}:${Math.floor(Date.now() / 60000)}`
  const count = await c.env.KV_STORE.get(key)
  
  if (count && parseInt(count) >= 10) {
    return c.json({
      error: 'Rate limit exceeded',
      retry_after: 60 - (Date.now() % 60000),
    }, 429)
  }
  
  await c.env.KV_STORE.put(key, (parseInt(count) || 0) + 1, { expirationTtl: 120 })
  
  await next()
}

/**
 * JWT Auth middleware for Entra ID B2C
 */
const jwtAuth = async (c: any, next: any) => {
  const authHeader = c.req.header('Authorization')
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return c.json({ error: 'Bearer token required' }, 401)
  }
  
  const token = authHeader.substring(7)
  
  try {
    // Verify JWT with Entra ID B2C
    // In production, use @azure/msal-node or similar
    const decoded = await verifyEntraJWT(token, c.env)
    
    // Attach user info to context
    c.set('user', decoded)
    
    await next()
  } catch (error) {
    return c.json({ error: 'Invalid token', details: error.message }, 401)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Publish event to Azure Event Grid
 */
async function publishEvent(env: Env, event: any) {
  try {
    await fetch(env.EVENT_GRID_ENDPOINT, {
      method: 'POST',
      headers: {
        'aeg-sas-key': env.EVENT_GRID_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([event]),
    })
  } catch (error) {
    console.error('event_grid_publish_failed', { error, event })
    // Don't throw - event grid failure shouldn't block submission
  }
}

/**
 * Verify Entra ID B2C JWT
 */
async function verifyEntraJWT(token: string, env: Env) {
  // In production, implement proper JWT verification:
  // 1. Fetch JWKS from Entra ID B2C issuer
  // 2. Verify signature
  // 3. Validate claims (iss, aud, exp, nbf)
  
  // For now, simple base64 decode (NOT SECURE - placeholder)
  const parts = token.split('.')
  if (parts.length !== 3) {
    throw new Error('Invalid JWT format')
  }
  
  const payload = JSON.parse(atob(parts[1]))
  
  // Validate issuer
  if (payload.iss !== env.ENTRA_JWT_ISSUER) {
    throw new Error('Invalid issuer')
  }
  
  // Validate audience
  if (payload.aud !== env.ENTRA_JWT_AUDIENCE) {
    throw new Error('Invalid audience')
  }
  
  // Validate expiration
  if (payload.exp && payload.exp < Date.now() / 1000) {
    throw new Error('Token expired')
  }
  
  return payload
}

// ─────────────────────────────────────────────────────────────────────────────
// APP
// ─────────────────────────────────────────────────────────────────────────────

const app = new Hono<{ Bindings: Env }>()

// Global middleware
app.use('*', cors())
app.use('/api/v1/invoices/*', rateLimiter)
app.use('/api/v1/*', jwtAuth)

// Mount routers
app.route('/api/v1/invoices', invoiceRouter)
app.route('/health', healthRouter)

// 404 handler
app.notFound((c) => {
  return c.json({ error: 'Not found' }, 404)
})

// Error handler
app.onError((err, c) => {
  console.error('unhandled_error', { error: err.message, stack: err.stack })
  return c.json({ error: 'Internal server error' }, 500)
})

export default app
