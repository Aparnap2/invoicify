/**
 * Redpanda Producer Unit Tests
 *
 * Run with: pnpm test -- test/lib/redpanda.test.ts
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  RedpandaProducer,
  getRedpandaProducer,
  resetRedpandaProducer,
  publishInvoiceUploaded,
  publishInvoiceExtracted,
  publishInvoiceRiskScored,
  publishInvoiceDecision,
  publishInvoiceSynced,
  type InvoiceStatusEvent,
  type InvoiceState,
} from './redpanda.js';

describe('RedpandaProducer', () => {
  let producer: RedpandaProducer;

  beforeEach(() => {
    resetRedpandaProducer();
    producer = new RedpandaProducer({
      baseUrl: 'http://localhost:8082',
      mockMode: true,
    });
  });

  describe('Initialization', () => {
    it('should initialize with default config', () => {
      const p = new RedpandaProducer();
      expect(p.topic).toBe('invoice.status');
      expect(p.isConfigured()).toBe(true);
    });

    it('should initialize in mock mode', () => {
      const p = new RedpandaProducer({ mockMode: true });
      expect(p.topic).toBe('invoice.status');
    });

    it('should use environment variables', () => {
      vi.stubEnv('REDPANDA_BASE_URL', 'http://redpanda:8082');
      const p = new RedpandaProducer();
      expect(p.isConfigured()).toBe(true);
      vi.unstubAllEnvs();
    });
  });

  describe('Topic', () => {
    it('should return correct topic name', () => {
      expect(producer.topic).toBe('invoice.status');
    });
  });

  describe('Publish', () => {
    it('should publish event in mock mode', async () => {
      const event: InvoiceStatusEvent = {
        invoiceId: 'inv-001',
        tenantId: 'tenant-001',
        state: 'uploaded',
        timestamp: new Date().toISOString(),
        traceId: 'trace-001',
      };

      const result = await producer.publish(event);

      expect(result.success).toBe(true);
      expect(result.topic).toBe('invoice.status');
      expect(result.partition).toBe(0);
      expect(result.offset).toBeDefined();
    });

    it('should publish with all fields', async () => {
      const event: InvoiceStatusEvent = {
        invoiceId: 'inv-002',
        tenantId: 'tenant-001',
        state: 'extracted',
        timestamp: new Date().toISOString(),
        traceId: 'trace-002',
        vendorId: 'vendor-001',
        invoiceNumber: 'INV-002',
        totalAmount: 1500.00,
        currency: 'USD',
      };

      const result = await producer.publish(event);

      expect(result.success).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should publish risk_scored state', async () => {
      const event: InvoiceStatusEvent = {
        invoiceId: 'inv-003',
        tenantId: 'tenant-001',
        state: 'risk_scored',
        timestamp: new Date().toISOString(),
        traceId: 'trace-003',
        vendorId: 'vendor-001',
        riskScore: 0.25,
        riskLevel: 'LOW',
      };

      const result = await producer.publish(event);

      expect(result.success).toBe(true);
      expect(event.state).toBe('risk_scored');
      expect(event.riskScore).toBe(0.25);
      expect(event.riskLevel).toBe('LOW');
    });
  });

  describe('Publish Batch', () => {
    it('should publish multiple events', async () => {
      const events: InvoiceStatusEvent[] = [
        {
          invoiceId: 'inv-001',
          tenantId: 'tenant-001',
          state: 'uploaded',
          timestamp: new Date().toISOString(),
          traceId: 'trace-001',
        },
        {
          invoiceId: 'inv-002',
          tenantId: 'tenant-001',
          state: 'uploaded',
          timestamp: new Date().toISOString(),
          traceId: 'trace-002',
        },
        {
          invoiceId: 'inv-003',
          tenantId: 'tenant-001',
          state: 'uploaded',
          timestamp: new Date().toISOString(),
          traceId: 'trace-003',
        },
      ];

      const results = await producer.publishBatch(events);

      expect(results).toHaveLength(3);
      expect(results.every((r) => r.success)).toBe(true);
    });
  });

  describe('Ensure Topic', () => {
    it('should return true in mock mode', async () => {
      const result = await producer.ensureTopic(3, 1);
      expect(result).toBe(true);
    });
  });
});

describe('Convenience Functions', () => {
  beforeEach(() => {
    resetRedpandaProducer();
  });

  it('should publish invoice uploaded event', async () => {
    const result = await publishInvoiceUploaded('inv-001', 'tenant-001', 'trace-001', 'vendor-001');

    expect(result.success).toBe(true);
    expect(result.topic).toBe('invoice.status');
  });

  it('should publish invoice extracted event', async () => {
    const result = await publishInvoiceExtracted(
      'inv-002',
      'tenant-001',
      'trace-002',
      'vendor-001',
      'INV-002',
      1500.00,
      'USD'
    );

    expect(result.success).toBe(true);
  });

  it('should publish invoice risk scored event', async () => {
    const result = await publishInvoiceRiskScored(
      'inv-003',
      'tenant-001',
      'trace-003',
      'vendor-001',
      0.35,
      'MEDIUM'
    );

    expect(result.success).toBe(true);
  });

  it('should publish invoice approved event', async () => {
    const result = await publishInvoiceDecision(
      'inv-004',
      'tenant-001',
      'trace-004',
      'vendor-001',
      500.00,
      'USD',
      'approved'
    );

    expect(result.success).toBe(true);
  });

  it('should publish invoice rejected event', async () => {
    const result = await publishInvoiceDecision(
      'inv-005',
      'tenant-001',
      'trace-005',
      'vendor-001',
      10000.00,
      'USD',
      'rejected'
    );

    expect(result.success).toBe(true);
  });

  it('should publish invoice synced event', async () => {
    const result = await publishInvoiceSynced('inv-006', 'tenant-001', 'trace-006', 'quickbooks');

    expect(result.success).toBe(true);
  });
});

describe('Singleton', () => {
  beforeEach(() => {
    resetRedpandaProducer();
  });

  it('should return same instance', () => {
    const instance1 = getRedpandaProducer({ mockMode: true });
    const instance2 = getRedpandaProducer();

    expect(instance1).toBe(instance2);
  });

  it('should create new instance after reset', () => {
    const instance1 = getRedpandaProducer({ mockMode: true });
    resetRedpandaProducer();
    const instance2 = getRedpandaProducer({ mockMode: true });

    expect(instance1).not.toBe(instance2);
  });
});

describe('InvoiceState Validation', () => {
  it('should accept all valid states', () => {
    const validStates: InvoiceState[] = [
      'uploaded',
      'extracted',
      'risk_scored',
      'approved',
      'rejected',
      'synced',
    ];

    expect(validStates).toHaveLength(6);
  });
});
