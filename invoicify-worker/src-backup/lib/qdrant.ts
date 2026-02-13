/**
 * Qdrant Vector Database Client for Cloudflare Workers
 *
 * Provides semantic search for invoices using Qdrant vector database.
 * Uses REST API for Cloudflare Workers compatibility.
 */

import { logger } from "./logger.js";

// ============================================================================
// Types
// ============================================================================

export interface QdrantConfig {
  /** Qdrant server URL */
  url: string;
  /** API key (optional) */
  apiKey?: string;
  /** Collection name */
  collectionName: string;
}

export interface SearchOptions {
  limit?: number;
  minScore?: number;
  tenantId?: string;
  status?: string;
  vendorName?: string;
}

export interface SearchResult {
  invoice_id: string;
  score: number;
  vendor_name: string;
  invoice_number: string;
  total_amount: number;
  invoice_date: string | null;
  status: string;
}

export interface InvoiceDocument {
  invoice_id: string;
  tenant_id: string;
  vendor_name: string;
  invoice_number: string;
  total_amount: number;
  currency: string;
  invoice_date?: string;
  due_date?: string;
  status: string;
  extracted_text: string;
}

export interface SearchResponse {
  success: boolean;
  results?: SearchResult[];
  error?: string;
}

export interface UpsertResponse {
  success: boolean;
  points_upserted?: number;
  error?: string;
}

// ============================================================================
// Qdrant Client
// ============================================================================

export class QdrantClient {
  private config: QdrantConfig;
  private embeddingEndpoint: string;
  private mockMode: boolean;

  constructor(config?: Partial<QdrantConfig>) {
    this.config = {
      url: config?.url || process.env.QDRANT_URL || "http://localhost:6333",
      apiKey: config?.apiKey || process.env.QDRANT_API_KEY,
      collectionName: config?.collectionName || "invoices",
    };
    this.embeddingEndpoint = process.env.OLLAMA_EMBEDDING_URL || "http://localhost:11434/api/embeddings";
    this.mockMode = config?.mockMode || process.env.MOCK_MODE === "true" || false;
  }

  /**
   * Get collection info
   */
  async getCollection(): Promise<{ exists: boolean; pointsCount?: number }> {
    if (this.mockMode) {
      return { exists: true, pointsCount: 100 };
    }

    try {
      const response = await fetch(`${this.config.url}/collections/${this.config.collectionName}`);

      if (!response.ok) {
        if (response.status === 404) {
          return { exists: false };
        }
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      return {
        exists: true,
        pointsCount: data.result?.points_count || 0,
      };
    } catch (error) {
      logger.error("Failed to get collection", { error });
      return { exists: false };
    }
  }

  /**
   * Create collection if it doesn't exist
   */
  async ensureCollection(): Promise<boolean> {
    if (this.mockMode) {
      logger.info("Mock: collection ensured", { collection: this.config.collectionName });
      return true;
    }

    try {
      const { exists } = await this.getCollection();

      if (exists) {
        return true;
      }

      // Create collection with BGE-small embedding dimensions (384)
      const response = await fetch(`${this.config.url}/collections`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: this.config.collectionName,
          vectors: {
            size: 384,
            distance: "Cosine",
          },
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        logger.error("Failed to create collection", { error });
        return false;
      }

      // Create payload indexes
      await this.createPayloadIndexes();

      logger.info("Collection created", { collection: this.config.collectionName });
      return true;
    } catch (error) {
      logger.error("Failed to ensure collection", { error });
      return false;
    }
  }

  /**
   * Create payload indexes for filtering
   */
  private async createPayloadIndexes(): Promise<void> {
    const indexes = ["tenant_id", "vendor_name", "status", "invoice_date"];

    for (const field of indexes) {
      try {
        await fetch(
          `${this.config.url}/collections/${this.config.collectionName}/index`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              field_name: field,
              field_schema: "keyword",
            }),
          }
        );
      } catch (error) {
        logger.warn("Failed to create index", { field, error });
      }
    }
  }

  /**
   * Generate embedding using Ollama
   */
  async generateEmbedding(text: string): Promise<number[]> {
    if (this.mockMode) {
      // Return random embedding for testing
      return Array.from({ length: 384 }, () => Math.random() * 2 - 1);
    }

    try {
      const response = await fetch(this.embeddingEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "nomic-embed-text:latest",
          prompt: text,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      return data.embedding || data.embeddings?.[0] || [];
    } catch (error) {
      logger.error("Failed to generate embedding", { error });
      throw error;
    }
  }

  /**
   * Generate embeddings for multiple texts
   */
  async generateEmbeddingsBatch(texts: string[]): Promise<number[][]> {
    if (this.mockMode) {
      return texts.map(() =>
        Array.from({ length: 384 }, () => Math.random() * 2 - 1)
      );
    }

    // Generate in parallel
    const embeddings = await Promise.all(
      texts.map((text) => this.generateEmbedding(text))
    );
    return embeddings;
  }

  /**
   * Upsert a single invoice document
   */
  async upsertInvoice(document: InvoiceDocument): Promise<UpsertResponse> {
    try {
      const embedding = await this.generateEmbedding(document.extracted_text);

      await this.ensureCollection();

      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            points: [
              {
                id: document.invoice_id,
                vector: embedding,
                payload: {
                  tenant_id: document.tenant_id,
                  vendor_name: document.vendor_name,
                  invoice_number: document.invoice_number,
                  total_amount: document.total_amount,
                  currency: document.currency,
                  invoice_date: document.invoice_date,
                  due_date: document.due_date,
                  status: document.status,
                  extracted_text_preview: document.extracted_text.slice(0, 500),
                },
              },
            ],
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return { success: true, points_upserted: 1 };
    } catch (error) {
      logger.error("Failed to upsert invoice", { invoiceId: document.invoice_id, error });
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  /**
   * Upsert multiple invoices
   */
  async upsertInvoices(documents: InvoiceDocument[]): Promise<UpsertResponse> {
    try {
      const texts = documents.map((d) => d.extracted_text);
      const embeddings = await this.generateEmbeddingsBatch(texts);

      await this.ensureCollection();

      const points = documents.map((doc, i) => ({
        id: doc.invoice_id,
        vector: embeddings[i],
        payload: {
          tenant_id: doc.tenant_id,
          vendor_name: doc.vendor_name,
          invoice_number: doc.invoice_number,
          total_amount: doc.total_amount,
          currency: doc.currency,
          invoice_date: doc.invoice_date,
          due_date: doc.due_date,
          status: doc.status,
          extracted_text_preview: doc.extracted_text.slice(0, 500),
        },
      }));

      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ points }),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return { success: true, points_upserted: documents.length };
    } catch (error) {
      logger.error("Failed to upsert invoices", { count: documents.length, error });
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  /**
   * Semantic search for invoices
   */
  async semanticSearch(query: string, options: SearchOptions = {}): Promise<SearchResult[]> {
    try {
      const embedding = await this.generateEmbedding(query);

      await this.ensureCollection();

      const { limit = 10, minScore = 0.5, tenantId, status, vendorName } = options;

      // Build filter
      const filterConditions: Record<string, unknown>[] = [];
      if (tenantId) filterConditions.push({ key: "tenant_id", match: { value: tenantId } });
      if (status) filterConditions.push({ key: "status", match: { value: status } });
      if (vendorName) filterConditions.push({ key: "vendor_name", match: { value: vendorName } });

      const body: Record<string, unknown> = {
        query_vector: embedding,
        limit,
        score_threshold: minScore,
      };

      if (filterConditions.length > 0) {
        body.filter = { must: filterConditions };
      }

      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points/search`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const results: SearchResult[] = (data.result?.points || []).map(
        (point: Record<string, unknown>) => ({
          invoice_id: point.id as string,
          score: point.score as number,
          vendor_name: (point.payload as Record<string, unknown>)?.vendor_name as string || "",
          invoice_number: (point.payload as Record<string, unknown>)?.invoice_number as string || "",
          total_amount: (point.payload as Record<string, unknown>)?.total_amount as number || 0,
          invoice_date: (point.payload as Record<string, unknown>)?.invoice_date as string | null,
          status: (point.payload as Record<string, unknown>)?.status as string || "",
        })
      );

      logger.info("Search completed", { query, results: results.length });
      return results;
    } catch (error) {
      logger.error("Search failed", { query, error });
      throw error;
    }
  }

  /**
   * Get invoice by ID
   */
  async getInvoice(invoiceId: string): Promise<SearchResult | null> {
    try {
      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points/${invoiceId}`
      );

      if (!response.ok) {
        if (response.status === 404) return null;
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const point = data.result;

      return {
        invoice_id: point.id,
        score: 1.0,
        vendor_name: point.payload?.vendor_name || "",
        invoice_number: point.payload?.invoice_number || "",
        total_amount: point.payload?.total_amount || 0,
        invoice_date: point.payload?.invoice_date || null,
        status: point.payload?.status || "",
      };
    } catch (error) {
      logger.error("Failed to get invoice", { invoiceId, error });
      return null;
    }
  }

  /**
   * Delete invoice by ID
   */
  async deleteInvoice(invoiceId: string): Promise<boolean> {
    try {
      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points/${invoiceId}`,
        { method: "DELETE" }
      );

      return response.ok;
    } catch (error) {
      logger.error("Failed to delete invoice", { invoiceId, error });
      return false;
    }
  }

  /**
   * Count invoices
   */
  async countInvoices(tenantId?: string): Promise<number> {
    try {
      const filter = tenantId
        ? { must: [{ key: "tenant_id", match: { value: tenantId } }] }
        : undefined;

      const response = await fetch(
        `${this.config.url}/collections/${this.config.collectionName}/points/count`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filter }),
        }
      );

      if (!response.ok) return 0;

      const data = await response.json();
      return data.result?.count || 0;
    } catch (error) {
      return 0;
    }
  }
}

// ============================================================================
// Singleton
// ============================================================================

let client: QdrantClient | null = null;

export function getQdrantClient(config?: Partial<QdrantConfig>): QdrantClient {
  if (!client) {
    client = new QdrantClient(config);
  }
  return client;
}

export function resetQdrantClient(): void {
  client = null;
}
