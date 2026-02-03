/**
 * Upstash Kafka Producer
 *
 * Publishes invoice events to Kafka topics for async processing.
 * Uses @upstash/kafka - HTTP-based Kafka client for Cloudflare Workers.
 *
 * Topics:
 * - invoice.uploaded: New invoice file uploaded
 * - invoice.processed: AI processing completed
 *
 * Run tests with: pnpm test -- test/lib/kafka-producer.test.ts
 */

import { Kafka } from "@upstash/kafka";

// ============================================================================
// Types
// ============================================================================

/**
 * Invoice uploaded event payload
 */
export interface InvoiceUploadedEvent {
  /** Unique invoice identifier */
  invoiceId: string;
  /** User/tenant ID for multi-tenancy */
  userId: string;
  /** R2 storage key */
  fileKey: string;
  /** Original file name */
  fileName: string;
  /** MIME type of the file */
  mimeType: string;
  /** File size in bytes */
  fileSize: number;
  /** SHA256 checksum */
  checksum: string;
  /** Trace ID for distributed tracing */
  traceId: string;
  /** Timestamp of the event */
  timestamp: string;
  /** Optional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Invoice processed event payload
 */
export interface InvoiceProcessedEvent {
  /** Unique invoice identifier */
  invoiceId: string;
  /** User/tenant ID */
  userId: string;
  /** Processing status */
  status: "success" | "failed";
  /** Extracted data (if successful) */
  extractedData?: Record<string, unknown>;
  /** Error message (if failed) */
  error?: string;
  /** Processing duration in milliseconds */
  durationMs: number;
  /** Trace ID for distributed tracing */
  traceId: string;
  /** Timestamp of the event */
  timestamp: string;
}

/**
 * Kafka producer configuration
 */
export interface KafkaConfig {
  /** Upstash Kafka REST URL */
  url: string;
  /** Upstash Kafka REST username */
  username: string;
  /** Upstash Kafka REST password */
  password: string;
}

/**
 * Publish result
 */
export interface PublishResult {
  success: boolean;
  topic: string;
  partition?: number;
  offset?: number;
  error?: string;
}

// ============================================================================
// Kafka Producer
// ============================================================================

/**
 * Kafka Event Producer for Invoice Lifecycle
 *
 * Publishes events to Upstash Kafka for async processing by Python worker.
 */
export class KafkaProducer {
  private client: Kafka | null = null;
  private mockMode: boolean;

  constructor(config?: Partial<KafkaConfig>) {
    this.mockMode = config?.url === "mock";

    if (!this.mockMode) {
      this.client = new Kafka({
        url: config?.url || process.env.UPSTASH_KAFKA_REST_URL || "",
        username: config?.username || process.env.UPSTASH_KAFKA_REST_USERNAME || "",
        password: config?.password || process.env.UPSTASH_KAFKA_REST_PASSWORD || "",
      });
    }
  }

  /**
   * Get the producer instance
   */
  private getProducer() {
    if (!this.client) {
      throw new Error("Kafka client not initialized. Check environment variables.");
    }
    return this.client.producer();
  }

  /**
   * Check if producer is configured
   */
  isConfigured(): boolean {
    return !this.mockMode && !!this.client;
  }

  /**
   * Publish an invoice uploaded event
   *
   * @param event - The invoice uploaded event
   * @returns PublishResult indicating success or failure
   */
  async publishInvoiceUploaded(event: InvoiceUploadedEvent): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish("invoice.uploaded", event, startTime);
    }

    try {
      const producer = this.getProducer();
      const result = await producer.produce("invoice.uploaded", {
        key: event.invoiceId,
        value: event,
        headers: {
          "trace-id": event.traceId,
          "user-id": event.userId,
          "content-type": event.mimeType,
        },
      });

      const duration = Date.now() - startTime;

      console.log(`[kafka] Published invoice.uploaded event`, {
        invoiceId: event.invoiceId,
        partition: result.partition,
        offset: result.baseOffset,
        duration_ms: duration,
      });

      return {
        success: true,
        topic: "invoice.uploaded",
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : "Unknown error";

      console.error(`[kafka] Failed to publish invoice.uploaded event:`, {
        invoiceId: event.invoiceId,
        error: errorMessage,
        duration_ms: duration,
      });

      return {
        success: false,
        topic: "invoice.uploaded",
        error: errorMessage,
      };
    }
  }

  /**
   * Publish an invoice processed event
   *
   * @param event - The invoice processed event
   * @returns PublishResult indicating success or failure
   */
  async publishInvoiceProcessed(event: InvoiceProcessedEvent): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish("invoice.processed", event, startTime);
    }

    try {
      const producer = this.getProducer();
      const result = await producer.produce("invoice.processed", {
        key: event.invoiceId,
        value: event,
        headers: {
          "trace-id": event.traceId,
          "status": event.status,
        },
      });

      const duration = Date.now() - startTime;

      console.log(`[kafka] Published invoice.processed event`, {
        invoiceId: event.invoiceId,
        status: event.status,
        partition: result.partition,
        offset: result.baseOffset,
        duration_ms: duration,
      });

      return {
        success: true,
        topic: "invoice.processed",
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : "Unknown error";

      console.error(`[kafka] Failed to publish invoice.processed event:`, {
        invoiceId: event.invoiceId,
        error: errorMessage,
        duration_ms: duration,
      });

      return {
        success: false,
        topic: "invoice.processed",
        error: errorMessage,
      };
    }
  }

  /**
   * Publish any event to a topic
   *
   * @param topic - The Kafka topic
   * @param key - The message key
   * @param value - The message value
   * @returns PublishResult indicating success or failure
   */
  async publish(topic: string, key: string, value: unknown): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish(topic, value, startTime);
    }

    try {
      const producer = this.getProducer();
      const result = await producer.produce(topic, {
        key,
        value: value as Record<string, unknown>,
      });

      return {
        success: true,
        topic,
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error";

      return {
        success: false,
        topic,
        error: errorMessage,
      };
    }
  }

  /**
   * Mock publish for testing
   */
  private mockPublish(topic: string, value: unknown, startTime: number): PublishResult {
    const duration = Date.now() - startTime;

    console.log(`[kafka] Mock: published to ${topic}`, {
      value,
      duration_ms: duration,
    });

    return {
      success: true,
      topic,
      partition: 0,
      offset: Math.floor(Math.random() * 10000),
    };
  }
}

// ============================================================================
// Singleton
// ============================================================================

let producer: KafkaProducer | null = null;

/**
 * Get the singleton Kafka producer instance
 */
export function getKafkaProducer(config?: Partial<KafkaConfig>): KafkaProducer {
  if (!producer) {
    producer = new KafkaProducer(config);
  }
  return producer;
}

/**
 * Reset the singleton (for testing)
 */
export function resetKafkaProducer(): void {
  producer = null;
}

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Publish invoice uploaded event
 */
export async function publishInvoiceUploaded(
  invoiceId: string,
  userId: string,
  fileKey: string,
  fileName: string,
  mimeType: string,
  fileSize: number,
  checksum: string,
  traceId: string,
  metadata?: Record<string, unknown>
): Promise<PublishResult> {
  const kafkaProducer = getKafkaProducer();
  return kafkaProducer.publishInvoiceUploaded({
    invoiceId,
    userId,
    fileKey,
    fileName,
    mimeType,
    fileSize,
    checksum,
    traceId,
    timestamp: new Date().toISOString(),
    metadata,
  });
}

/**
 * Publish invoice processed event
 */
export async function publishInvoiceProcessed(
  invoiceId: string,
  userId: string,
  status: "success" | "failed",
  extractedData?: Record<string, unknown>,
  error?: string,
  durationMs?: number,
  traceId?: string
): Promise<PublishResult> {
  const kafkaProducer = getKafkaProducer();
  return kafkaProducer.publishInvoiceProcessed({
    invoiceId,
    userId,
    status,
    extractedData,
    error,
    durationMs,
    traceId: traceId || "",
    timestamp: new Date().toISOString(),
  });
}
