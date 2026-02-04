/**
 * Upstash Kafka Producer
 *
 * Publishes invoice events to Kafka topics for async processing.
 * Uses @upstash/kafka - HTTP-based Kafka client for Cloudflare Workers.
 *
 * Topics:
 * - invoice.uploaded: New invoice file uploaded
 * - invoice.processed: AI processing completed
 * - invoice.uploaded.dlq: Dead Letter Queue for failed uploads
 *
 * Run tests with: pnpm test -- test/lib/kafka-producer.test.ts
 */

import { Kafka } from "@upstash/kafka";
import { logger } from "./logger";

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
  /** Enable mock mode for testing (default: false) */
  mockMode?: boolean;
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
// Retry Logic with Exponential Backoff
// ============================================================================

/**
 * Retry a function with exponential backoff
 *
 * @param fn - The async function to retry
 * @param options - Retry configuration options
 * @returns The result of the function
 */
async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxRetries?: number; minTimeout?: number; maxTimeout?: number } = {}
): Promise<T> {
  const maxRetries = options.maxRetries ?? 3;
  const minTimeout = options.minTimeout ?? 100;
  const maxTimeout = options.maxTimeout ?? 5000;

  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      if (attempt > maxRetries) {
        throw lastError;
      }

      // Exponential backoff with jitter
      const baseDelay = Math.min(minTimeout * Math.pow(2, attempt - 1), maxTimeout);
      const jitter = Math.random() * 100; // Add jitter to prevent thundering herd
      const delay = baseDelay + jitter;

      logger.warn("Kafka publish retry", {
        attempt,
        maxRetries,
        delay_ms: Math.round(delay),
        error: lastError.message,
      });

      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError!;
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
    // Check for explicit mock mode via config or environment variable
    if (config?.mockMode || process.env.KAFKA_MOCK_MODE === "true") {
      this.mockMode = true;
      return;
    }

    // Fallback: check for magic string (backwards compatibility)
    if (config?.url === "mock") {
      this.mockMode = true;
      return;
    }

    // Fail-fast: validate required environment variables
    const url = config?.url || process.env.UPSTASH_KAFKA_REST_URL;
    const username = config?.username || process.env.UPSTASH_KAFKA_REST_USERNAME;
    const password = config?.password || process.env.UPSTASH_KAFKA_REST_PASSWORD;

    if (!url || !username || !password) {
      const missingVars: string[] = [];
      if (!url) missingVars.push("UPSTASH_KAFKA_REST_URL");
      if (!username) missingVars.push("UPSTASH_KAFKA_REST_USERNAME");
      if (!password) missingVars.push("UPSTASH_KAFKA_REST_PASSWORD");

      throw new Error(
        `[KafkaProducer] Configuration incomplete. Missing environment variables: ${missingVars.join(", ")}`
      );
    }

    this.mockMode = false;
    this.client = new Kafka({ url, username, password });
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
   * Check if producer is configured for real Kafka
   */
  isConfigured(): boolean {
    return !this.mockMode && !!this.client;
  }

  /**
   * Publish to Dead Letter Queue
   *
   * @param topic - The original topic name (will have .dlq appended)
   * @param value - The failed message payload
   * @param error - The error that caused the failure
   */
  async publishToDLQ(
    topic: string,
    value: unknown,
    error: string
  ): Promise<PublishResult> {
    const dlqTopic = topic.endsWith(".dlq") ? topic : `${topic}.dlq`;

    if (this.mockMode) {
      logger.info("Mock: published to DLQ", {
        dlqTopic,
        originalTopic: topic,
        error,
      });
      return { success: true, topic: dlqTopic, partition: 0, offset: -1 };
    }

    try {
      const producer = this.getProducer();
      const result = await producer.produce(dlqTopic, {
        key: (value as { invoiceId?: string }).invoiceId || "unknown",
        value: {
          original: value,
          error,
          failedAt: new Date().toISOString(),
          traceId: (value as { traceId?: string }).traceId || "unknown",
        },
        headers: {
          "x-dlq": "true",
          "x-original-error": error.substring(0, 256), // Limit header size
        },
      });

      logger.warn("Message sent to Dead Letter Queue", {
        dlqTopic,
        originalTopic: topic,
        key: (value as { invoiceId?: string }).invoiceId || "unknown",
        error,
      });

      return {
        success: true,
        topic: dlqTopic,
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (dlqError) {
      const dlqErrorMessage =
        dlqError instanceof Error ? dlqError.message : "Unknown error";

      logger.error("Failed to publish to DLQ", {
        dlqTopic,
        dlqError: dlqErrorMessage,
      });

      return {
        success: false,
        topic: dlqTopic,
        error: `DLQ publish failed: ${dlqErrorMessage}`,
      };
    }
  }

  /**
   * Publish an invoice uploaded event
   *
   * @param event - The invoice uploaded event
   * @returns PublishResult indicating success or failure
   */
  async publishInvoiceUploaded(
    event: InvoiceUploadedEvent
  ): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish("invoice.uploaded", event, startTime);
    }

    try {
      const result = await withRetry(
        async () => {
          const producer = this.getProducer();
          return producer.produce("invoice.uploaded", {
            key: event.invoiceId,
            value: event,
            headers: {
              "trace-id": event.traceId,
              "user-id": event.userId,
              "content-type": event.mimeType,
            },
          });
        },
        { maxRetries: 3, minTimeout: 100, maxTimeout: 5000 }
      );

      const duration = Date.now() - startTime;

      logger.info("Published invoice.uploaded event", {
        invoiceId: event.invoiceId,
        userId: event.userId,
        traceId: event.traceId,
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
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";

      logger.error("Failed to publish invoice.uploaded event", {
        invoiceId: event.invoiceId,
        userId: event.userId,
        traceId: event.traceId,
        error: errorMessage,
        duration_ms: duration,
      });

      // On final failure, attempt to send to DLQ
      const dlqResult = await this.publishToDLQ(
        "invoice.uploaded",
        event,
        errorMessage
      );

      // Return original failure result, not DLQ result
      return {
        success: false,
        topic: "invoice.uploaded",
        error: `${errorMessage} (DLQ: ${dlqResult.success ? "sent" : "failed"})`,
      };
    }
  }

  /**
   * Publish an invoice processed event
   *
   * @param event - The invoice processed event
   * @returns PublishResult indicating success or failure
   */
  async publishInvoiceProcessed(
    event: InvoiceProcessedEvent
  ): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish("invoice.processed", event, startTime);
    }

    try {
      const result = await withRetry(
        async () => {
          const producer = this.getProducer();
          return producer.produce("invoice.processed", {
            key: event.invoiceId,
            value: event,
            headers: {
              "trace-id": event.traceId,
              status: event.status,
            },
          });
        },
        { maxRetries: 3, minTimeout: 100, maxTimeout: 5000 }
      );

      const duration = Date.now() - startTime;

      logger.info("Published invoice.processed event", {
        invoiceId: event.invoiceId,
        userId: event.userId,
        status: event.status,
        traceId: event.traceId,
        duration_ms: duration,
        partition: result.partition,
        offset: result.baseOffset,
      });

      return {
        success: true,
        topic: "invoice.processed",
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";

      logger.error("Failed to publish invoice.processed event", {
        invoiceId: event.invoiceId,
        userId: event.userId,
        status: event.status,
        traceId: event.traceId,
        error: errorMessage,
        duration_ms: duration,
      });

      // On final failure, attempt to send to DLQ
      const dlqResult = await this.publishToDLQ(
        "invoice.processed",
        event,
        errorMessage
      );

      return {
        success: false,
        topic: "invoice.processed",
        error: `${errorMessage} (DLQ: ${dlqResult.success ? "sent" : "failed"})`,
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
  async publish(
    topic: string,
    key: string,
    value: unknown
  ): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish(topic, value, startTime);
    }

    try {
      const result = await withRetry(
        async () => {
          const producer = this.getProducer();
          return producer.produce(topic, {
            key,
            value: value as Record<string, unknown>,
          });
        },
        { maxRetries: 3, minTimeout: 100, maxTimeout: 5000 }
      );

      const duration = Date.now() - startTime;

      logger.info("Published event to topic", {
        topic,
        key,
        duration_ms: duration,
        partition: result.partition,
        offset: result.baseOffset,
      });

      return {
        success: true,
        topic,
        partition: result.partition,
        offset: Number(result.baseOffset),
      };
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";

      logger.error("Failed to publish event", {
        topic,
        key,
        error: errorMessage,
      });

      const dlqResult = await this.publishToDLQ(topic, value, errorMessage);

      return {
        success: false,
        topic,
        error: `${errorMessage} (DLQ: ${dlqResult.success ? "sent" : "failed"})`,
      };
    }
  }

  /**
   * Mock publish for testing (deterministic offsets)
   */
  private mockPublish(
    topic: string,
    value: unknown,
    startTime: number
  ): PublishResult {
    const duration = Date.now() - startTime;

    const invoiceId = (value as InvoiceUploadedEvent)?.invoiceId ||
      (value as InvoiceProcessedEvent)?.invoiceId ||
      "unknown";

    logger.info("Mock: published to topic", {
      topic,
      invoiceId,
      duration_ms: duration,
    });

    return {
      success: true,
      topic,
      partition: 0,
      offset: 1, // Deterministic offset for reliable tests
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
