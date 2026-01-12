import { Hono } from "hono";
import { getDb, schema } from "../db";
import { eq, desc, asc, like, and, or, gte, lte, sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";

const invoicesRoutes = new Hono<{ Bindings: Env }>();

// ============ Validation Helpers ============

function validatePagination(page?: string, limit?: string): { page: number; limit: number; error?: string } {
  const parsedPage = parseInt(page || "1");
  const parsedLimit = parseInt(limit || "20");

  if (isNaN(parsedPage) || parsedPage < 1) {
    return { page: 1, limit: parsedLimit, error: "Invalid page number" };
  }
  if (isNaN(parsedLimit) || parsedLimit < 1) {
    return { page: parsedPage, limit: 20, error: "Invalid limit" };
  }
  if (parsedLimit > 100) {
    return { page: parsedPage, limit: 100, error: "Limit capped at 100" };
  }

  return { page: parsedPage, limit: parsedLimit };
}

function validateDate(dateStr?: string): { date: string | undefined; error?: string } {
  if (!dateStr) return { date: undefined };
  // ISO date format validation (YYYY-MM-DD)
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  if (!dateRegex.test(dateStr)) {
    return { date: undefined, error: "Invalid date format (expected YYYY-MM-DD)" };
  }
  return { date: dateStr };
}

function sanitizeSearchQuery(query?: string): string | undefined {
  if (!query) return undefined;
  // Remove potentially dangerous characters for LIKE pattern
  return query.replace(/[%$_\\]/g, "").substring(0, 100);
}

// List all invoices with pagination and filters
invoicesRoutes.get("/", async (c) => {
  const db = getDb(c.env);

  // Validate pagination
  const { page, limit, error: pagError } = validatePagination(
    c.req.query("page"),
    c.req.query("limit")
  );
  if (pagError) {
    return c.json({ error: pagError, code: "INVALID_PAGINATION" }, 400);
  }

  const status = c.req.query("status");
  const vendorName = sanitizeSearchQuery(c.req.query("vendor"));
  const { date: fromDate, error: fromError } = validateDate(c.req.query("from"));
  const { date: toDate, error: toError } = validateDate(c.req.query("to"));

  if (fromError) return c.json({ error: fromError, code: "INVALID_FROM_DATE" }, 400);
  if (toError) return c.json({ error: toError, code: "INVALID_TO_DATE" }, 400);

  const sortBy = c.req.query("sortBy") || "createdAt";
  const sortOrder = c.req.query("sortOrder") || "desc";

  const offset = (page - 1) * limit;

  const conditions = [];

  if (status) {
    conditions.push(eq(schema.invoices.status, status));
  }

  if (vendorName) {
    conditions.push(like(schema.invoices.vendorName, `%${vendorName}%`));
  }

  if (fromDate) {
    conditions.push(gte(schema.invoices.createdAt, fromDate));
  }

  if (toDate) {
    conditions.push(lte(schema.invoices.createdAt, toDate));
  }

  const orderByFn = sortOrder === "desc" ? desc : asc;

  const [data, totalResult] = await Promise.all([
    db
      .select()
      .from(schema.invoices)
      .where(conditions.length > 0 ? and(...conditions) : undefined)
      .orderBy(orderByFn(schema.invoices.createdAt))
      .limit(limit)
      .offset(offset),
    db
      .select({ count: sql<number>`count(*)` })
      .from(schema.invoices)
      .where(conditions.length > 0 ? and(...conditions) : undefined),
  ]);

  return c.json({
    data,
    pagination: {
      page,
      limit,
      total: totalResult[0]?.count || 0,
      totalPages: Math.ceil((totalResult[0]?.count || 0) / limit),
    },
  });
});

// Get single invoice by ID
invoicesRoutes.get("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, id))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Get line items
  const lineItems = await db
    .select()
    .from(schema.lineItems)
    .where(eq(schema.lineItems.invoiceId, id));

  // Get approval history
  const approvals = await db
    .select()
    .from(schema.approvals)
    .where(eq(schema.approvals.invoiceId, id))
    .orderBy(desc(schema.approvals.createdAt));

  // Get risk indicators
  const riskIndicators = await db
    .select()
    .from(schema.riskIndicators)
    .where(eq(schema.riskIndicators.invoiceId, id));

  return c.json({
    ...invoice,
    lineItems,
    approvals,
    riskIndicators,
  });
});

// Create new invoice
invoicesRoutes.post("/", async (c) => {
  const db = getDb(c.env);
  const body = await c.req.json();

  const id = uuidv4();
  const now = new Date().toISOString();

  const [invoice] = await db
    .insert(schema.invoices)
    .values({
      id,
      vendorName: body.vendorName,
      vendorId: body.vendorId,
      invoiceNumber: body.invoiceNumber,
      totalAmount: body.totalAmount,
      currency: body.currency || "USD",
      status: schema.InvoiceStatus.NEW,
      dueDate: body.dueDate,
      invoiceDate: body.invoiceDate,
      fileUrl: body.fileUrl,
      fileName: body.fileName,
      mimeType: body.mimeType,
      createdAt: now,
      updatedAt: now,
    })
    .returning();

  // Insert line items if provided
  if (body.lineItems && Array.isArray(body.lineItems)) {
    const items = body.lineItems.map((item: any) => ({
      id: uuidv4(),
      invoiceId: id,
      description: item.description,
      quantity: item.quantity || 1,
      unitPrice: item.unitPrice || 0,
      amount: item.amount || 0,
      glCode: item.glCode,
    }));

    await db.insert(schema.lineItems).values(items);
  }

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "CREATE",
    entityType: "invoice",
    entityId: id,
    performedBy: body.performedBy || "system",
    changes: JSON.stringify(body),
    performedAt: now,
  });

  return c.json({ success: true, data: invoice }, 201);
});

// Update invoice
invoicesRoutes.put("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json();

  const [existing] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, id))
    .limit(1);

  if (!existing) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  const now = new Date().toISOString();

  const [invoice] = await db
    .update(schema.invoices)
    .set({
      vendorName: body.vendorName,
      vendorId: body.vendorId,
      invoiceNumber: body.invoiceNumber,
      totalAmount: body.totalAmount,
      currency: body.currency,
      status: body.status,
      dueDate: body.dueDate,
      invoiceDate: body.invoiceDate,
      updatedAt: now,
    })
    .where(eq(schema.invoices.id, id))
    .returning();

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "UPDATE",
    entityType: "invoice",
    entityId: id,
    performedBy: body.performedBy || "system",
    changes: JSON.stringify({ before: existing, after: body }),
    performedAt: now,
  });

  return c.json({ success: true, data: invoice });
});

// Delete invoice
invoicesRoutes.delete("/:id", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");

  const [existing] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, id))
    .limit(1);

  if (!existing) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  await db.delete(schema.invoices).where(eq(schema.invoices.id, id));

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "DELETE",
    entityType: "invoice",
    entityId: id,
    performedBy: "system",
    changes: JSON.stringify(existing),
    performedAt: new Date().toISOString(),
  });

  return c.json({ success: true });
});

// Update invoice status
invoicesRoutes.patch("/:id/status", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json();

  if (!body.status) {
    return c.json({ error: "Status is required" }, 400);
  }

  const [invoice] = await db
    .update(schema.invoices)
    .set({
      status: body.status,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, id))
    .returning();

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "STATUS_CHANGE",
    entityType: "invoice",
    entityId: id,
    performedBy: body.performedBy || "system",
    changes: JSON.stringify({ newStatus: body.status }),
    performedAt: new Date().toISOString(),
  });

  return c.json({ success: true, data: invoice });
});

// Get invoice statistics
invoicesRoutes.get("/stats/overview", async (c) => {
  const db = getDb(c.env);

  const statusCounts = await db
    .select({
      status: schema.invoices.status,
      count: sql<number>`count(*)`,
    })
    .from(schema.invoices)
    .groupBy(schema.invoices.status);

  const [totalAmount] = await db
    .select({
      total: sql<number>`coalesce(sum(${schema.invoices.totalAmount}), 0)`,
      avg: sql<number>`coalesce(avg(${schema.invoices.totalAmount}), 0)`,
    })
    .from(schema.invoices);

  const [recentActivity] = await db
    .select({
      today: sql<number>`count(case when date(${schema.invoices.createdAt}) = date('now') then 1 end)`,
      week: sql<number>`count(case when date(${schema.invoices.createdAt}) >= date('now', '-7 days') then 1 end)`,
      month: sql<number>`count(case when date(${schema.invoices.createdAt}) >= date('now', '-30 days') then 1 end)`,
    })
    .from(schema.invoices);

  return c.json({
    byStatus: statusCounts,
    totals: totalAmount,
    recentActivity,
  });
});

// Search invoices
invoicesRoutes.get("/search", async (c) => {
  const db = getDb(c.env);
  const query = c.req.query("q");

  if (!query || query.length < 2) {
    return c.json({ error: "Search query must be at least 2 characters" }, 400);
  }

  const results = await db
    .select()
    .from(schema.invoices)
    .where(
      or(
        like(schema.invoices.vendorName, `%${query}%`),
        like(schema.invoices.invoiceNumber, `%${query}%`),
        like(schema.invoices.rawContent, `%${query}%`)
      )
    )
    .limit(20);

  return c.json({ data: results });
});

// Approve/reject invoice (HITL workflow endpoint)
// POST /api/v1/invoices/:id/approve
invoicesRoutes.post("/:id/approve", async (c) => {
  const db = getDb(c.env);
  const id = c.req.param("id");
  const body = await c.req.json<{
    decision: "approved" | "rejected";
    comments?: string;
    performedBy?: string;
  }>();

  // Validate decision
  if (!body.decision || !["approved", "rejected"].includes(body.decision)) {
    return c.json({ error: "Invalid decision. Must be 'approved' or 'rejected'" }, 400);
  }

  // Get invoice
  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, id))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  const now = new Date().toISOString();
  const newStatus = body.decision === "approved" ? "APPROVED" : "REJECTED";

  // Update invoice status
  const [updated] = await db
    .update(schema.invoices)
    .set({
      status: newStatus,
      updatedAt: now,
    })
    .where(eq(schema.invoices.id, id))
    .returning();

  // Create approval record
  const approvalId = uuidv4();
  await db.insert(schema.approvals).values({
    id: approvalId,
    invoiceId: id,
    approverEmail: body.performedBy || "admin",
    status: body.decision === "approved" ? "APPROVED" : "REJECTED",
    comments: body.comments,
    createdAt: now,
  });

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: `HITL_${body.decision.toUpperCase()}`,
    entityType: "invoice",
    entityId: id,
    performedBy: body.performedBy || "human",
    changes: JSON.stringify({
      decision: body.decision,
      comments: body.comments,
      previousStatus: invoice.status,
      newStatus,
    }),
    performedAt: now,
  });

  return c.json({
    success: true,
    data: {
      id: updated.id,
      status: newStatus,
      approvalId,
    },
  });
});

export { invoicesRoutes };
