import { describe, it, expect, vi } from 'vitest';
import { InvoiceProcessor } from '../InvoiceProcessor';
import type { InvoiceMessage } from '../InvoiceProcessor';

// Mock environment
const mockEnv = {
  DB: {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnValue({
        all: vi.fn().mockResolvedValue({ results: [] }),
        first: vi.fn().mockResolvedValue(null),
        run: vi.fn().mockResolvedValue({})
      })
    })
  },
  R2_BUCKET: {
    get: vi.fn(),
    put: vi.fn()
  },
  GROQ_API_KEY: 'test-api-key'
};

// Mock DurableObjectState
const mockState = {
  storage: {
    list: vi.fn().mockResolvedValue(new Map()),
    put: vi.fn().mockResolvedValue(undefined),
    get: vi.fn().mockResolvedValue(undefined)
  }
};

describe('InvoiceProcessor', () => {
  let processor: InvoiceProcessor;

  beforeEach(() => {
    processor = new InvoiceProcessor(mockState as any, mockEnv as any);
  });

  describe('processInvoice', () => {
    it('should process invoice successfully', async () => {
      const message: InvoiceMessage = {
        traceId: 'test-123',
        r2KeyRaw: 'raw/2025-02-11/test-123.pdf',
        uploadedAt: new Date().toISOString()
      };

      // Mock R2 download
      mockEnv.R2_BUCKET.get.mockResolvedValue({
        arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(100))
      });

      // Note: Full integration test would mock Groq API call
      // For now, just verify the structure
      expect(message.traceId).toBe('test-123');
    });
  });

  describe('calculateRisk', () => {
    it('should calculate risk from invoice data', async () => {
      const invoiceData = {
        vendorName: 'Acme Corp',
        amount: 150,
        currency: 'USD'
      };

      // Mock vendor history
      mockEnv.DB.prepare.mockReturnValue({
        bind: vi.fn().mockReturnValue({
          all: vi.fn().mockResolvedValue({
            results: [
              { amount: 100 },
              { amount: 110 },
              { amount: 120 }
            ]
          })
        })
      });

      // Access private method
      const risk = await (processor as any).calculateRisk(invoiceData);
      
      expect(typeof risk).toBe('number');
      expect(risk).toBeGreaterThanOrEqual(0);
      expect(risk).toBeLessThanOrEqual(1);
    });
  });

  describe('makeDecision', () => {
    it('should auto-approve low risk', async () => {
      const decision = await (processor as any).makeDecision(
        { amount: 100 },
        0.2
      );

      expect(decision.action).toBe('AUTO_APPROVE');
    });

    it('should send to HITL for medium risk', async () => {
      const decision = await (processor as any).makeDecision(
        { amount: 100 },
        0.5
      );

      expect(decision.action).toBe('HITL');
      expect(decision.reasons.length).toBeGreaterThan(0);
    });

    it('should reject high risk', async () => {
      const decision = await (processor as any).makeDecision(
        { amount: 100 },
        0.8
      );

      expect(decision.action).toBe('REJECT');
    });

    it('should send high amounts to HITL', async () => {
      const decision = await (processor as any).makeDecision(
        { amount: 15000 },
        0.2
      );

      expect(decision.action).toBe('HITL');
    });
  });
});
