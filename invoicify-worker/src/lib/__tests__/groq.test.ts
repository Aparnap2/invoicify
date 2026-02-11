import { describe, it, expect, vi, beforeEach } from 'vitest';
import { extractInvoiceWithGroq, extractInvoiceWithOllama } from '../groq';

// Mock global fetch
global.fetch = vi.fn();

describe('Groq API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('extractInvoiceWithGroq', () => {
    it('should extract invoice data successfully', async () => {
      const mockResponse = {
        choices: [{
          message: {
            content: JSON.stringify({
              vendorName: 'Acme Corp',
              invoiceNumber: 'INV-001',
              amount: 1500.00,
              currency: 'USD',
              invoiceDate: '2025-02-01',
              lineItems: [],
              confidence: 0.95
            })
          }
        }]
      };

      (fetch as any).mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue(mockResponse)
      });

      const result = await extractInvoiceWithGroq('base64pdf', 'test-key');

      expect(fetch).toHaveBeenCalledWith(
        'https://api.groq.com/openai/v1/chat/completions',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-key',
            'Content-Type': 'application/json'
          })
        })
      );
      expect(result.vendorName).toBe('Acme Corp');
      expect(result.amount).toBe(1500.00);
    });

    it('should throw error on API failure', async () => {
      (fetch as any).mockResolvedValue({
        ok: false,
        statusText: 'Rate Limited',
        text: vi.fn().mockResolvedValue('Too many requests')
      });

      await expect(
        extractInvoiceWithGroq('base64pdf', 'test-key')
      ).rejects.toThrow('Groq API error');
    });

    it('should throw error on invalid JSON response', async () => {
      (fetch as any).mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          choices: []
        })
      });

      await expect(
        extractInvoiceWithGroq('base64pdf', 'test-key')
      ).rejects.toThrow('no choices');
    });

    it('should throw error on missing required fields', async () => {
      (fetch as any).mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          choices: [{
            message: {
              content: JSON.stringify({ vendorName: 'Test' }) // Missing amount
            }
          }]
        })
      });

      await expect(
        extractInvoiceWithGroq('base64pdf', 'test-key')
      ).rejects.toThrow('Missing required fields');
    });
  });

  describe('extractInvoiceWithOllama', () => {
    it('should extract using local Ollama', async () => {
      const mockResponse = {
        response: JSON.stringify({
          vendorName: 'Acme Corp',
          invoiceNumber: 'INV-001',
          amount: 1500.00,
          currency: 'USD',
          invoiceDate: '2025-02-01',
          lineItems: [],
          confidence: 0.90
        })
      };

      (fetch as any).mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue(mockResponse)
      });

      const result = await extractInvoiceWithOllama('base64pdf', 'http://localhost:11434', 'llava');

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:11434/api/generate',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('llava')
        })
      );
      expect(result.vendorName).toBe('Acme Corp');
    });

    it('should throw error on non-JSON response', async () => {
      (fetch as any).mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          response: 'This is not JSON'
        })
      });

      await expect(
        extractInvoiceWithOllama('base64pdf')
      ).rejects.toThrow('non-JSON response');
    });
  });
});
