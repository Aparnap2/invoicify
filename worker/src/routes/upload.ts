import { Hono } from "hono";
import { getDb, schema } from "../db";
import {
  uploadBase64ToR2,
  downloadFromR2,
  deleteFromR2,
  generateStorageKey,
  generateFileChecksum,
  getPublicUrl,
  fileExistsInR2,
  type UploadResult,
} from "../lib/r2-storage";
import { eq } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { Env } from "../db";

// R2 bucket name from wrangler.toml configuration
const R2_BUCKET_NAME = "invoicify-files";

const uploadRoutes = new Hono<{ Bindings: Env }>();

/**
 * Upload invoice file
 * POST /api/v1/upload
 */
uploadRoutes.post("/", async (c) => {
  const env = c.env;
  const body = await c.req.json();

  if (!body.file) {
    return c.json({ error: "File data is required" }, 400);
  }

  if (!body.invoiceId) {
    return c.json({ error: "Invoice ID is required" }, 400);
  }

  const mimeType = body.mimeType || "application/octet-stream";
  const fileName = body.fileName || "invoice";
  const invoiceId = body.invoiceId;

  // Generate storage key
  const key = generateStorageKey(invoiceId, fileName, mimeType);

  // Upload to R2
  const uploadResult = await uploadBase64ToR2(env, key, body.file, mimeType, {
    invoiceId,
    fileName,
    uploadedAt: new Date().toISOString(),
  });

  if (!uploadResult.success) {
    return c.json(
      { error: uploadResult.error },
      500
    );
  }

  // Generate checksum
  const binary = Buffer.from(body.file, "base64");
  const arrayBuffer = binary.buffer.slice(
    binary.byteOffset,
    binary.byteOffset + binary.byteLength
  );
  const checksum = await generateFileChecksum(arrayBuffer);

  // Update invoice with file URL
  const db = getDb(env);
  await db
    .update(schema.invoices)
    .set({
      fileUrl: key,
      fileName,
      mimeType,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, invoiceId));

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "FILE_UPLOAD",
    entityType: "invoice",
    entityId: invoiceId,
    performedBy: body.performedBy || "system",
    changes: JSON.stringify({
      fileName,
      mimeType,
      size: binary.length,
      key,
    }),
    performedAt: new Date().toISOString(),
  });

  return c.json({
    success: true,
    data: {
      key,
      url: uploadResult.url,
      fileName,
      mimeType,
      size: binary.length,
      checksum,
    },
  });
});

/**
 * Get upload status for an invoice
 * GET /api/v1/upload/:invoiceId/status
 */
uploadRoutes.get("/:invoiceId/status", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  if (!invoice.fileUrl) {
    return c.json({ uploaded: false, message: "No file uploaded" });
  }

  // Check if file exists
  const exists = await fileExistsInR2(env, invoice.fileUrl);

  return c.json({
    uploaded: true,
    fileName: invoice.fileName,
    mimeType: invoice.mimeType,
    url: getPublicUrl(invoice.fileUrl, R2_BUCKET_NAME),
    exists,
    uploadedAt: invoice.createdAt,
  });
});

/**
 * Download invoice file
 * GET /api/v1/upload/:invoiceId/download
 */
uploadRoutes.get("/:invoiceId/download", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  if (!invoice.fileUrl) {
    return c.json({ error: "No file uploaded for this invoice" }, 404);
  }

  // Download from R2
  const result = await downloadFromR2(env, invoice.fileUrl);

  if (!result.data) {
    return c.json({ error: result.error || "File not found" }, 404);
  }

  // Return file as response
  return new Response(result.data, {
    headers: {
      "Content-Type": invoice.mimeType || "application/octet-stream",
      "Content-Disposition": `attachment; filename="${invoice.fileName}"`,
    },
  });
});

/**
 * Delete invoice file
 * DELETE /api/v1/upload/:invoiceId
 */
uploadRoutes.delete("/:invoiceId", async (c) => {
  const env = c.env;
  const invoiceId = c.req.param("invoiceId");
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  if (!invoice.fileUrl) {
    return c.json({ error: "No file to delete" }, 400);
  }

  // Delete from R2
  const deleteResult = await deleteFromR2(env, invoice.fileUrl);

  if (!deleteResult.success) {
    return c.json({ error: deleteResult.error }, 500);
  }

  // Update invoice
  await db
    .update(schema.invoices)
    .set({
      fileUrl: null,
      fileName: null,
      mimeType: null,
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, invoiceId));

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "FILE_DELETE",
    entityType: "invoice",
    entityId: invoiceId,
    performedBy: "system",
    changes: JSON.stringify({ key: invoice.fileUrl }),
    performedAt: new Date().toISOString(),
  });

  return c.json({ success: true });
});

export { uploadRoutes };
