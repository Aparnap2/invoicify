/**
 * Semantic Search API for Invoice Queries
 *
 * GET /api/v1/search?q=<natural language query>
 *
 * Examples:
 * - "Show me high value Uber receipts"
 * - "What invoices are pending payment?"
 * - "Find travel expenses from last month"
 */

import { Hono } from "hono";
import { getQdrantClient } from "../lib/qdrant.js";
import type { Env } from "../db";

const searchRoutes = new Hono<{ Bindings: Env }>();

/**
 * Semantic search endpoint
 * GET /api/v1/search?q=<query>&limit=<number>&min_score=<0-1>
 */
searchRoutes.get("/", async (c) => {
  const query = c.req.query("q");
  const limit = parseInt(c.req.query("limit") || "10");
  const minScore = parseFloat(c.req.query("min_score") || "0.5");

  if (!query) {
    return c.json(
      { error: "Query parameter 'q' is required" },
      400
    );
  }

  try {
    const qdrant = getQdrantClient();

    const results = await qdrant.semanticSearch(query, {
      limit,
      minScore,
    });

    return c.json({
      success: true,
      query,
      results: results.map((r) => ({
        invoiceId: r.invoice_id,
        score: r.score,
        vendor: r.vendor_name,
        invoiceNumber: r.invoice_number,
        amount: r.total_amount,
        date: r.invoice_date,
        status: r.status,
      })),
      total: results.length,
    });
  } catch (error) {
    console.error("Search error:", error);
    return c.json(
      {
        error: "Search failed",
        message: error instanceof Error ? error.message : "Unknown error",
      },
      500
    );
  }
});

/**
 * Keyword search endpoint (hybrid search fallback)
 * GET /api/v1/search/keyword?q=<keyword>
 */
searchRoutes.get("/keyword", async (c) => {
  const keyword = c.req.query("q");
  const limit = parseInt(c.req.query("limit") || "10");

  if (!keyword) {
    return c.json(
      { error: "Query parameter 'q' is required" },
      400
    );
  }

  // For keyword search, we use a simple filter approach
  // In production, you'd use Qdrant's hybrid search capabilities
  try {
    const qdrant = getQdrantClient();

    // Use semantic search with keyword-enriched query
    const results = await qdrant.semanticSearch(keyword, {
      limit,
      minScore: 0.3,  // Lower threshold for keyword search
    });

    return c.json({
      success: true,
      query: keyword,
      results: results.map((r) => ({
        invoiceId: r.invoice_id,
        score: r.score,
        vendor: r.vendor_name,
        invoiceNumber: r.invoice_number,
        amount: r.total_amount,
        date: r.invoice_date,
        status: r.status,
      })),
      total: results.length,
    });
  } catch (error) {
    console.error("Keyword search error:", error);
    return c.json(
      {
        error: "Search failed",
        message: error instanceof Error ? error.message : "Unknown error",
      },
      500
    );
  }
});

/**
 * Get similar invoices
 * GET /api/v1/search/similar/:invoiceId
 */
searchRoutes.get("/similar/:invoiceId", async (c) => {
  const invoiceId = c.req.param("invoiceId");
  const limit = parseInt(c.req.query("limit") || "5");

  try {
    const qdrant = getQdrantClient();

    // Get the invoice first
    const invoice = qdrant.getInvoice(invoiceId);

    if (!invoice) {
      return c.json({ error: "Invoice not found" }, 404);
    }

    // Search for similar invoices
    const extractedText = invoice.extracted_text_preview || "";
    const results = await qdrant.semanticSearch(extractedText, {
      limit: limit + 1,  // Get extra to exclude self
      minScore: 0.3,
    });

    // Filter out the original invoice
    const similar = results.filter((r) => r.invoice_id !== invoiceId).slice(0, limit);

    return c.json({
      success: true,
      invoiceId,
      results: similar.map((r) => ({
        invoiceId: r.invoice_id,
        score: r.score,
        vendor: r.vendor_name,
        invoiceNumber: r.invoice_number,
        amount: r.total_amount,
        date: r.invoice_date,
        status: r.status,
      })),
      total: similar.length,
    });
  } catch (error) {
    console.error("Similar search error:", error);
    return c.json(
      {
        error: "Search failed",
        message: error instanceof Error ? error.message : "Unknown error",
      },
      500
    );
  }
});

/**
 * Get search suggestions / autocomplete
 * GET /api/v1/search/suggestions?q=<prefix>
 */
searchRoutes.get("/suggestions", async (c) => {
  const prefix = c.req.query("q") || "";

  // Return common search suggestions
  const suggestions = [
    "high value invoices",
    "pending payments",
    "Uber receipts",
    "AWS expenses",
    "travel expenses",
    "software subscriptions",
    "marketing invoices",
    "office supplies",
    "client entertainment",
    "monthly subscriptions",
  ].filter((s) => s.toLowerCase().includes(prefix.toLowerCase()));

  return c.json({
    suggestions: suggestions.slice(0, 5),
  });
});

export { searchRoutes };
