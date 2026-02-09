import { Hono } from "hono";
import { getDb, schema } from "../db";
import { extractInvoiceWithVision, type ExtractedInvoiceData } from "../lib/vision-ocr";
import { validateExtraction, generateValidationReport, type ValidationSignal } from "../lib/critic";
import { eq } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { publishInvoiceExtracted, publishInvoiceRiskScored } from "../lib/redpanda";
import type { Env } from "../db";

const extractRoutes = new Hono<{ Bindings: Env }>();

/**
 * Extract invoice data from uploaded image
 * POST /api/v1/extract
 */
extractRoutes.post("/", async (c) => {
  const env = c.env;
  const body = await c.req.json();

  if (!body.image) {
    return c.json({ error: "Image data is required" }, 400);
  }

  // Extract using Llama Vision
  const result = await extractInvoiceWithVision(
    env,
    body.image,
    body.mimeType || "image/jpeg"
  );

  if (!result.success) {
    return c.json(
      { error: result.error, confidence: result.confidence },
      422
    );
  }

  // Create invoice with extracted data
  const db = getDb(env);
  const id = uuidv4();
  const now = new Date().toISOString();
  const extracted = result.data!;

  // ================================================================
  // CRITIC VALIDATION - Hard math validation (deterministic)
  // ================================================================
  const criticResult = validateExtraction({
    vendorName: extracted.vendorName,
    invoiceNumber: extracted.invoiceNumber,
    invoiceDate: extracted.invoiceDate,
    dueDate: extracted.dueDate,
    totalAmount: extracted.totalAmount,
    subtotal: extracted.subtotal,
    tax: extracted.tax,
    lineItems: extracted.lineItems,
    currency: extracted.currency,
  });

  // Store validation signals in the database
  if (criticResult.signals.length > 0) {
    await db.insert(schema.riskIndicators).values(
      criticResult.signals.map((signal) => ({
        id: uuidv4(),
        invoiceId: id,
        indicatorType: signal.type,
        severity: signal.severity.toLowerCase() as "low" | "medium" | "high" | "critical",
        description: signal.description,
        scoreContribution: signal.scoreContribution,
        metadata: JSON.stringify({
          field: signal.field,
          expected: signal.expected,
          actual: signal.actual,
        }),
        createdAt: now,
      }))
    );
  }

  // Create checksum for duplicate detection
  const checksum = await generateChecksum(extracted);

  // Check for duplicates before inserting
  const [existingDuplicate] = await db
    .select()
    .from(schema.duplicateChecks)
    .where(eq(schema.duplicateChecks.checksum, checksum))
    .limit(1);

  if (existingDuplicate) {
    return c.json({
      success: true,
      data: {
        invoiceId: existingDuplicate.invoiceId,
        isDuplicate: true,
        duplicateOf: existingDuplicate.invoiceId,
      },
      confidence: result.confidence,
      processingTime: result.processingTime,
    });
  }

  // Insert invoice
  const [invoice] = await db
    .insert(schema.invoices)
    .values({
      id,
      vendorName: extracted.vendorName,
      invoiceNumber: extracted.invoiceNumber,
      totalAmount: extracted.totalAmount,
      currency: extracted.currency || "USD",
      status: schema.InvoiceStatus.EXTRACTED,
      dueDate: extracted.dueDate,
      invoiceDate: extracted.invoiceDate,
      extractedData: JSON.stringify(extracted),
      confidenceScore: result.confidence,
      fileUrl: body.fileUrl,
      fileName: body.fileName,
      mimeType: body.mimeType,
      createdAt: now,
      updatedAt: now,
    })
    .returning();

  // Insert line items
  if (extracted.lineItems && extracted.lineItems.length > 0) {
    const lineItems = extracted.lineItems.map((item) => ({
      id: uuidv4(),
      invoiceId: id,
      description: item.description,
      quantity: item.quantity,
      unitPrice: item.unitPrice,
      amount: item.amount,
      glCode: item.glCode,
    }));

    await db.insert(schema.lineItems).values(lineItems);
  }

  // Record duplicate check
  await db.insert(schema.duplicateChecks).values({
    id: uuidv4(),
    invoiceId: id,
    checksum,
    isDuplicate: false,
    confidence: result.confidence,
    createdAt: now,
  });

  // Publish event to Redpanda - invoice extracted successfully
  const tenantId = "default"; // TODO: Get from auth context
  const traceId = uuidv4();

  await publishInvoiceExtracted(
    id,
    tenantId,
    traceId,
    extracted.vendorName,
    extracted.invoiceNumber,
    extracted.totalAmount,
    extracted.currency || "USD"
  ).catch((err) => {
    console.error("Failed to publish extraction event:", err);
  });

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "EXTRACT",
    entityType: "invoice",
    entityId: id,
    performedBy: "system",
    changes: JSON.stringify({
      vendorName: extracted.vendorName,
      invoiceNumber: extracted.invoiceNumber,
      totalAmount: extracted.totalAmount,
      lineItemsCount: extracted.lineItems.length,
    }),
    performedAt: now,
  });

  return c.json({
    success: true,
    data: {
      invoiceId: id,
      vendorName: extracted.vendorName,
      invoiceNumber: extracted.invoiceNumber,
      totalAmount: extracted.totalAmount,
      currency: extracted.currency,
      dueDate: extracted.dueDate,
      lineItems: extracted.lineItems,
      confidence: result.confidence,
    },
    // Critic validation results
    critic: {
      valid: criticResult.valid,
      errors: criticResult.errors,
      signals: criticResult.signals.map(s => ({
        type: s.type,
        severity: s.severity,
        description: s.description,
        scoreContribution: s.scoreContribution,
      })),
      report: generateValidationReport(criticResult),
    },
    confidence: result.confidence,
    processingTime: result.processingTime,
  });
});

/**
 * Get extraction status for an invoice
 * GET /api/v1/extract/:invoiceId
 */
extractRoutes.get("/:invoiceId", async (c) => {
  const db = getDb(c.env);
  const invoiceId = c.req.param("invoiceId");

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  return c.json({
    invoiceId,
    status: invoice.status,
    confidence: invoice.confidenceScore,
    extractedData: invoice.extractedData
      ? JSON.parse(invoice.extractedData)
      : null,
    rawContent: invoice.rawContent,
  });
});

/**
 * Re-extract data for an invoice (useful when OCR fails)
 * POST /api/v1/extract/:invoiceId/retry
 */
extractRoutes.post("/:invoiceId/retry", async (c) => {
  const env = c.env;
  const db = getDb(env);
  const invoiceId = c.req.param("invoiceId");

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return c.json({ error: "Invoice not found" }, 404);
  }

  // Get the original file if available
  if (!invoice.fileUrl) {
    return c.json(
      { error: "No file available for re-extraction" },
      400
    );
  }

  // Fetch the image from R2
  const object = await env.INVOICE_BUCKET.get(invoice.fileUrl);

  if (!object) {
    return c.json({ error: "File not found in storage" }, 404);
  }

  const arrayBuffer = await object.arrayBuffer();
  const base64 = Buffer.from(arrayBuffer).toString("base64");

  // Re-extract
  const result = await extractInvoiceWithVision(env, base64, invoice.mimeType || "image/jpeg");

  if (!result.success) {
    return c.json(
      { error: result.error, confidence: result.confidence },
      422
    );
  }

  const extracted = result.data!;
  const now = new Date().toISOString();

  // Update invoice with new data
  await db
    .update(schema.invoices)
    .set({
      vendorName: extracted.vendorName,
      invoiceNumber: extracted.invoiceNumber,
      totalAmount: extracted.totalAmount,
      currency: extracted.currency || invoice.currency,
      dueDate: extracted.dueDate || invoice.dueDate,
      invoiceDate: extracted.invoiceDate || invoice.invoiceDate,
      extractedData: JSON.stringify(extracted),
      confidenceScore: result.confidence,
      status: schema.InvoiceStatus.EXTRACTED,
      updatedAt: now,
    })
    .where(eq(schema.invoices.id, invoiceId));

  return c.json({
    success: true,
    data: extracted,
    confidence: result.confidence,
    processingTime: result.processingTime,
  });
});

/**
 * Generate checksum for duplicate detection
 */
async function generateChecksum(data: ExtractedInvoiceData): Promise<string> {
  const str = `${data.vendorName}|${data.invoiceNumber}|${data.totalAmount}|${data.invoiceDate || ""}`;
  const encoder = new TextEncoder();
  const dataBuffer = encoder.encode(str);
  const hashBuffer = await crypto.subtle.digest("SHA-256", dataBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export { extractRoutes };
