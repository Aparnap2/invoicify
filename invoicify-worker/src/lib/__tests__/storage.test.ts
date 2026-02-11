import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  uploadInvoicePDF,
  downloadInvoicePDF,
  storeProcessedResult,
  getProcessedResult,
  generateRawKey,
  generateProcessedKey
} from '../storage';

describe('Storage Utilities', () => {
  const mockBucket = {
    put: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    list: vi.fn()
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('generateRawKey', () => {
    it('should generate key with date and traceId', () => {
      const key = generateRawKey('abc-123');
      
      expect(key).toMatch(/raw\/\d{4}-\d{2}-\d{2}\/abc-123\.pdf/);
    });
  });

  describe('generateProcessedKey', () => {
    it('should generate processed key with date and traceId', () => {
      const key = generateProcessedKey('abc-123');
      
      expect(key).toMatch(/processed\/\d{4}-\d{2}-\d{2}\/abc-123\.json/);
    });
  });

  describe('uploadInvoicePDF', () => {
    it('should upload PDF to R2', async () => {
      const data = new ArrayBuffer(100);
      mockBucket.put.mockResolvedValue({ etag: '"abc123"' });

      const result = await uploadInvoicePDF(mockBucket as any, 'test-123', data);

      expect(mockBucket.put).toHaveBeenCalledWith(
        expect.stringContaining('test-123.pdf'),
        data,
        expect.objectContaining({
          httpMetadata: { contentType: 'application/pdf' },
          customMetadata: expect.objectContaining({
            traceId: 'test-123',
            uploadedAt: expect.any(String)
          })
        })
      );
      expect(result.size).toBe(100);
      expect(result.etag).toBe('"abc123"');
    });

    it('should throw error on upload failure', async () => {
      mockBucket.put.mockResolvedValue(null);

      await expect(
        uploadInvoicePDF(mockBucket as any, 'test-123', new ArrayBuffer(100))
      ).rejects.toThrow('Failed to upload PDF');
    });
  });

  describe('downloadInvoicePDF', () => {
    it('should download PDF from R2', async () => {
      const data = new ArrayBuffer(100);
      mockBucket.get.mockResolvedValue({
        arrayBuffer: vi.fn().mockResolvedValue(data)
      });

      const result = await downloadInvoicePDF(mockBucket as any, 'raw/test.pdf');

      expect(mockBucket.get).toHaveBeenCalledWith('raw/test.pdf');
      expect(result).toBe(data);
    });

    it('should return null if object not found', async () => {
      mockBucket.get.mockResolvedValue(null);

      const result = await downloadInvoicePDF(mockBucket as any, 'raw/test.pdf');

      expect(result).toBeNull();
    });
  });

  describe('storeProcessedResult', () => {
    it('should store JSON result', async () => {
      const data = { vendorName: 'Test', amount: 100 };
      mockBucket.put.mockResolvedValue({ etag: '"def456"' });

      const result = await storeProcessedResult(mockBucket as any, 'test-123', data);

      expect(mockBucket.put).toHaveBeenCalledWith(
        expect.stringContaining('test-123.json'),
        expect.any(Uint8Array),
        expect.objectContaining({
          httpMetadata: { contentType: 'application/json' }
        })
      );
      expect(result.etag).toBe('"def456"');
    });
  });

  describe('getProcessedResult', () => {
    it('should retrieve and parse JSON', async () => {
      const data = { vendorName: 'Test', amount: 100 };
      mockBucket.get.mockResolvedValue({
        text: vi.fn().mockResolvedValue(JSON.stringify(data))
      });

      const result = await getProcessedResult(mockBucket as any, 'processed/test.json');

      expect(result).toEqual(data);
    });

    it('should return null if object not found', async () => {
      mockBucket.get.mockResolvedValue(null);

      const result = await getProcessedResult(mockBucket as any, 'processed/test.json');

      expect(result).toBeNull();
    });

    it('should return null on JSON parse error', async () => {
      mockBucket.get.mockResolvedValue({
        text: vi.fn().mockResolvedValue('invalid json')
      });

      const result = await getProcessedResult(mockBucket as any, 'processed/test.json');

      expect(result).toBeNull();
    });
  });
});
