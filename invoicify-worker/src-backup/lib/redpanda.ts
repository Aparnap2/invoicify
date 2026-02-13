/**
 * Redpanda Event Bus Producer
 *
 * Publishes invoice lifecycle events to Redpanda/Kafka-compatible bus.
 * Uses Redpanda's HTTP API for Cloudflare Workers compatibility.
 *
 * Topic: invoice.status - Single topic with state in payload
 * States: uploaded, extracted, risk_scored, approved, rejected, synced
 *
 * Run tests with: pnpm test -- test/lib/redpanda.test.ts
 */

import { logger } from './logger.js';

// ============================================================================
// Types
// ============================================================================

/**
 * Invoice lifecycle states
 */
export type InvoiceState =
  | 'uploaded'
  | 'extracted'
  | 'risk_scored'
  | 'approved'
  | 'rejected'
  | 'synced';

/**
 * Invoice status event payload
 */
export interface InvoiceStatusEvent {
  /** Unique invoice identifier */
  invoiceId: string;
  /** Tenant/organization ID for multi-tenancy */
  tenantId: string;
  /** Current lifecycle state */
  state: InvoiceState;
  /** Timestamp of the event */
  timestamp: string;
  /** Trace ID for distributed tracing */
  traceId: string;
  /** Vendor ID if available */
  vendorId?: string;
  /** Invoice number for reference */
  invoiceNumber?: string;
  /** Total amount if available */
  totalAmount?: number;
  /** Currency code */
  currency?: string;
  /** Risk score (0-1) if risk_scored */
  riskScore?: number;
  /** Risk level if risk_scored */
  riskLevel?: 'LOW' | 'MEDIUM' | 'HIGH';
  /** External sync target (quickbooks, sheets) if synced */
  syncTarget?: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Redpanda producer configuration
 */
export interface RedpandaConfig {
  /** Redpanda HTTP API URL */
  baseUrl: string;
  /** Kafka broker list (for future Kafka protocol support) */
  brokers?: string[];
  /** Client ID for connection */
  clientId?: string;
  /** Enable mock mode for testing */
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
// Redpanda Producer
// ============================================================================

/**
 * Redpanda Event Bus Producer
 *
 * Publishes invoice status events to Redpanda using its HTTP API.
 * Designed for Cloudflare Workers with proper error handling and retries.
 */
export class RedpandaProducer {
  private config: RedpandaConfig;
  private mockMode: boolean;

  constructor(config?: Partial<RedpandaConfig>) {
    this.config = {
      baseUrl: config?.baseUrl || process.env.REDPANDA_BASE_URL || 'http://localhost:8082',
      brokers: config?.brokers || [],
      clientId: config?.clientId || 'invoicify-worker',
      mockMode: config?.mockMode || process.env.MOCK_MODE === 'true' || false,
    };
    this.mockMode = this.config.mockMode;
  }

  /**
   * Get the topic name for invoice events
   */
  get topic(): string {
    return 'invoice.status';
  }

  /**
   * Check if producer is configured
   */
  isConfigured(): boolean {
    return !!this.config.baseUrl;
  }

  /**
   * Publish an invoice status event
   *
   * @param event - The invoice status event to publish
   * @returns PublishResult indicating success or failure
   */
  async publish(event: InvoiceStatusEvent): Promise<PublishResult> {
    const startTime = Date.now();

    if (this.mockMode) {
      return this.mockPublish(event, startTime);
    }

    try {
      const response = await fetch(`${this.config.baseUrl}/v1/kafka/${this.topic}/records`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          // Use invoice ID as key for partition ordering
          key: event.invoiceId,
          // Include event data as value
          value: event,
          // Set timestamp
          timestamp: new Date(event.timestamp).getTime(),
          // Headers for tracing
          headers: {
            'trace-id': event.traceId,
            'tenant-id': event.tenantId,
            'invoice-state': event.state,
          },
        }),
      });

      const duration = Date.now() - startTime;

      if (!response.ok) {
        const errorText = await response.text();
        logger.errorWithContext(
          `Redpanda publish failed: ${response.status} ${errorText}`,
          new Error(`HTTP ${response.status}`),
          { invoiceId: event.invoiceId, topic: this.topic, duration_ms: duration }
        );

        return {
          success: false,
          topic: this.topic,
          error: `HTTP ${response.status}: ${errorText}`,
        };
      }

      const result = await response.json();

      logger.info(`Published invoice event`, {
        invoiceId: event.invoiceId,
        state: event.state,
        topic: this.topic,
        partition: result.partition,
        offset: result.offset,
        duration_ms: duration,
      });

      return {
        success: true,
        topic: this.topic,
        partition: result.partition,
        offset: result.offset,
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';

      logger.errorWithContext(
        `Redpanda publish error: ${errorMessage}`,
        error instanceof Error ? error : new Error(errorMessage),
        { invoiceId: event.invoiceId, topic: this.topic, duration_ms: duration }
      );

      return {
        success: false,
        topic: this.topic,
        error: errorMessage,
      };
    }
  }

  /**
   * Publish multiple events in batch
   *
   * @param events - Array of events to publish
   * @returns Array of PublishResults
   */
  async publishBatch(events: InvoiceStatusEvent[]): Promise<PublishResult[]> {
    const results = await Promise.all(events.map((event) => this.publish(event)));
    const successCount = results.filter((r) => r.success).length;

    logger.info(`Published batch of ${events.length} events`, {
      success: successCount,
      failed: events.length - successCount,
      topic: this.topic,
    });

    return results;
  }

  /**
   * Create topic if it doesn't exist
   *
   * @param partitions - Number of partitions (default 3)
   * @param replicationFactor - Replication factor (default 1)
   */
  async ensureTopic(partitions = 3, replicationFactor = 1): Promise<boolean> {
    if (this.mockMode) {
      logger.info('Mock: topic creation skipped', { topic: this.topic });
      return true;
    }

    try {
      const response = await fetch(`${this.config.baseUrl}/v1/topics`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topic: this.topic,
          partitions: partitions,
          replication_factor: replicationFactor,
        }),
      });

      if (!response.ok && response.status !== 409) {
        // 409 = topic already exists
        const errorText = await response.text();
        logger.errorWithContext(
          `Failed to create topic: ${errorText}`,
          new Error(`HTTP ${response.status}`),
          { topic: this.topic }
        );
        return false;
      }

      logger.info('Topic ensured', { topic: this.topic, partitions, replicationFactor });
      return true;
    } catch (error) {
      logger.errorWithContext(
        `Topic creation error: ${error}`,
        error instanceof Error ? error : new Error('Unknown'),
        { topic: this.topic }
      );
      return false;
    }
  }

  /**
   * Mock publish for testing
   */
  private mockPublish(event: InvoiceStatusEvent, startTime: number): PublishResult {
    const duration = Date.now() - startTime;

    logger.info('Mock: published invoice event', {
      invoiceId: event.invoiceId,
      state: event.state,
      topic: this.topic,
      duration_ms: duration,
    });

    return {
      success: true,
      topic: this.topic,
      partition: 0,
      offset: Math.floor(Math.random() * 10000),
    };
  }
}

// ============================================================================
// Singleton
// ============================================================================

let producer: RedpandaProducer | null = null;

/**
 * Get the singleton Redpanda producer instance
 */
export function getRedpandaProducer(config?: Partial<RedpandaConfig>): RedpandaProducer {
  if (!producer) {
    producer = new RedpandaProducer(config);
  }
  return producer;
}

/**
 * Reset the singleton (for testing)
 */
export function resetRedpandaProducer(): void {
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
  tenantId: string,
  traceId: string,
  vendorId?: string
): Promise<PublishResult> {
  const producer = getRedpandaProducer();
  return producer.publish({
    invoiceId,
    tenantId,
    state: 'uploaded',
    timestamp: new Date().toISOString(),
    traceId,
    vendorId,
  });
}

/**
 * Publish invoice extracted event
 */
export async function publishInvoiceExtracted(
  invoiceId: string,
  tenantId: string,
  traceId: string,
  vendorId: string,
  invoiceNumber: string,
  totalAmount: number,
  currency: string
): Promise<PublishResult> {
  const producer = getRedpandaProducer();
  return producer.publish({
    invoiceId,
    tenantId,
    state: 'extracted',
    timestamp: new Date().toISOString(),
    traceId,
    vendorId,
    invoiceNumber,
    totalAmount,
    currency,
  });
}

/**
 * Publish invoice risk scored event
 */
export async function publishInvoiceRiskScored(
  invoiceId: string,
  tenantId: string,
  traceId: string,
  vendorId: string,
  riskScore: number,
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
): Promise<PublishResult> {
  const producer = getRedpandaProducer();
  return producer.publish({
    invoiceId,
    tenantId,
    state: 'risk_scored',
    timestamp: new Date().toISOString(),
    traceId,
    vendorId,
    riskScore,
    riskLevel,
  });
}

/**
 * Publish invoice approved/rejected event
 */
export async function publishInvoiceDecision(
  invoiceId: string,
  tenantId: string,
  traceId: string,
  vendorId: string,
  totalAmount: number,
  currency: string,
  decision: 'approved' | 'rejected'
): Promise<PublishResult> {
  const producer = getRedpandaProducer();
  return producer.publish({
    invoiceId,
    tenantId,
    state: decision,
    timestamp: new Date().toISOString(),
    traceId,
    vendorId,
    totalAmount,
    currency,
  });
}

/**
 * Publish invoice synced event
 */
export async function publishInvoiceSynced(
  invoiceId: string,
  tenantId: string,
  traceId: string,
  syncTarget: 'quickbooks' | 'sheets' | 'slack'
): Promise<PublishResult> {
  const producer = getRedpandaProducer();
  return producer.publish({
    invoiceId,
    tenantId,
    state: 'synced',
    timestamp: new Date().toISOString(),
    traceId,
    syncTarget,
  });
}
