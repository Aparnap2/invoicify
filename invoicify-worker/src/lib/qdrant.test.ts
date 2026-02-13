/**
 * Qdrant Client Unit Tests
 *
 * Run with: pnpm test -- test/lib/qdrant.test.ts
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  QdrantClient,
  getQdrantClient,
  resetQdrantClient,
  type InvoiceDocument,
  type SearchOptions,
} from "./qdrant.js";

describe("QdrantClient", () => {
  let client: QdrantClient;

  beforeEach(() => {
    resetQdrantClient();
    client = new QdrantClient({
      url: "http://localhost:6333",
      collectionName: "invoices",
      mockMode: true,
    });
  });

  describe("Initialization", () => {
    it("should initialize with default config", () => {
      const c = new QdrantClient();
      expect(c).toBeInstanceOf(QdrantClient);
    });

    it("should initialize in mock mode", () => {
      const c = new QdrantClient({ mockMode: true });
      expect(c).toBeInstanceOf(QdrantClient);
    });
  });

  describe("getCollection", () => {
    it("should return exists in mock mode", async () => {
      const result = await client.getCollection();
      expect(result.exists).toBe(true);
      expect(result.pointsCount).toBe(100);
    });
  });

  describe("ensureCollection", () => {
    it("should return true in mock mode", async () => {
      const result = await client.ensureCollection();
      expect(result).toBe(true);
    });
  });

  describe("generateEmbedding", () => {
    it("should return embedding in mock mode", async () => {
      const embedding = await client.generateEmbedding("Test invoice text");
      expect(embedding).toHaveLength(384);
      expect(embedding.every((v) => v >= -1 && v <= 1)).toBe(true);
    });

    it("should return consistent embeddings for same text", async () => {
      const emb1 = await client.generateEmbedding("Same text");
      const emb2 = await client.generateEmbedding("Same text");
      expect(emb1).toEqual(emb2);
    });
  });

  describe("generateEmbeddingsBatch", () => {
    it("should generate embeddings for multiple texts", async () => {
      const texts = ["Text 1", "Text 2", "Text 3"];
      const embeddings = await client.generateEmbeddingsBatch(texts);
      expect(embeddings).toHaveLength(3);
      expect(embeddings[0]).toHaveLength(384);
    });
  });

  describe("upsertInvoice", () => {
    it("should upsert invoice in mock mode", async () => {
      const doc: InvoiceDocument = {
        invoice_id: "inv-001",
        tenant_id: "tenant-001",
        vendor_name: "Acme Corp",
        invoice_number: "INV-001",
        total_amount: 1500.00,
        currency: "USD",
        invoice_date: "2024-01-15",
        status: "APPROVED",
        extracted_text: "Invoice from Acme Corp for services rendered",
      };

      const result = await client.upsertInvoice(doc);
      expect(result.success).toBe(true);
      expect(result.points_upserted).toBe(1);
    });
  });

  describe("upsertInvoices", () => {
    it("should upsert multiple invoices in mock mode", async () => {
      const docs: InvoiceDocument[] = [
        {
          invoice_id: "inv-001",
          tenant_id: "tenant-001",
          vendor_name: "Acme Corp",
          invoice_number: "INV-001",
          total_amount: 1500.00,
          currency: "USD",
          status: "APPROVED",
          extracted_text: "First invoice",
        },
        {
          invoice_id: "inv-002",
          tenant_id: "tenant-001",
          vendor_name: "Beta Inc",
          invoice_number: "INV-002",
          total_amount: 2500.00,
          currency: "USD",
          status: "PENDING",
          extracted_text: "Second invoice",
        },
      ];

      const result = await client.upsertInvoices(docs);
      expect(result.success).toBe(true);
      expect(result.points_upserted).toBe(2);
    });
  });

  describe("semanticSearch", () => {
    it("should search in mock mode", async () => {
      const results = await client.semanticSearch("Uber receipts", {
        limit: 10,
        minScore: 0.5,
      });

      expect(Array.isArray(results)).toBe(true);
    });

    it("should filter by tenant", async () => {
      const results = await client.semanticSearch("invoices", {
        limit: 10,
        tenantId: "tenant-001",
      });

      expect(Array.isArray(results)).toBe(true);
    });

    it("should return empty results for no matches", async () => {
      const results = await client.semanticSearch("xyznonexistent123", {
        limit: 5,
        minScore: 0.99,
      });

      expect(results).toHaveLength(0);
    });
  });

  describe("getInvoice", () => {
    it("should return null for non-existent invoice in mock mode", async () => {
      const result = await client.getInvoice("nonexistent-id");
      expect(result).toBeNull();
    });
  });

  describe("deleteInvoice", () => {
    it("should return true in mock mode", async () => {
      const result = await client.deleteInvoice("inv-001");
      expect(result).toBe(true);
    });
  });

  describe("countInvoices", () => {
    it("should return count in mock mode", async () => {
      const count = await client.countInvoices();
      expect(typeof count).toBe("number");
    });

    it("should filter by tenant", async () => {
      const count = await client.countInvoices("tenant-001");
      expect(typeof count).toBe("number");
    });
  });
});

describe("Singleton", () => {
  beforeEach(() => {
    resetQdrantClient();
  });

  it("should return same instance", () => {
    const instance1 = getQdrantClient({ mockMode: true });
    const instance2 = getQdrantClient();

    expect(instance1).toBe(instance2);
  });

  it("should create new instance after reset", () => {
    const instance1 = getQdrantClient({ mockMode: true });
    resetQdrantClient();
    const instance2 = getQdrantClient({ mockMode: true });

    expect(instance1).not.toBe(instance2);
  });
});

describe("InvoiceDocument Validation", () => {
  it("should validate required fields", () => {
    const doc: InvoiceDocument = {
      invoice_id: "inv-001",
      tenant_id: "tenant-001",
      vendor_name: "Acme Corp",
      invoice_number: "INV-001",
      total_amount: 1500.00,
      currency: "USD",
      status: "APPROVED",
      extracted_text: "Test invoice",
    };

    expect(doc.invoice_id).toBe("inv-001");
    expect(doc.total_amount).toBe(1500.00);
  });

  it("should allow optional fields", () => {
    const doc: InvoiceDocument = {
      invoice_id: "inv-001",
      tenant_id: "tenant-001",
      vendor_name: "Acme Corp",
      invoice_number: "INV-001",
      total_amount: 1500.00,
      currency: "USD",
      status: "APPROVED",
      extracted_text: "Test invoice",
      invoice_date: "2024-01-15",
      due_date: "2024-02-15",
      metadata: { category: "services" },
    };

    expect(doc.invoice_date).toBe("2024-01-15");
    expect(doc.metadata).toEqual({ category: "services" });
  });
});

describe("SearchOptions Validation", () => {
  it("should accept valid options", () => {
    const options: SearchOptions = {
      limit: 10,
      minScore: 0.5,
      tenantId: "tenant-001",
      status: "PENDING",
      vendorName: "Acme Corp",
    };

    expect(options.limit).toBe(10);
    expect(options.minScore).toBe(0.5);
  });

  it("should use default values", () => {
    const options: SearchOptions = {};
    expect(options.limit).toBeUndefined();
    expect(options.minScore).toBeUndefined();
  });
});
