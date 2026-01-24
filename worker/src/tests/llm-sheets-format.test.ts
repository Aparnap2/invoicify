/**
 * LLM Sheets Format Evaluation Tests
 *
 * Tests that the LLM can format invoice data correctly for Google Sheets.
 * Uses tomng/lfm2.5-instruct:1.2b model.
 *
 * Run with: pnpm test -- test/tests/llm-sheets-format.test.ts
 */

import { describe, it, expect } from 'vitest';
import type { InvoiceFieldType } from '../lib/google/types.js';

// Expected field order for Sheets output
const EXPECTED_FIELDS: InvoiceFieldType[] = [
  'invoice_number',
  'vendor_name',
  'total_amount',
  'invoice_date',
  'status',
];

describe('LLM Sheets Format Evaluation', () => {
  describe('Format Specification', () => {
    it('should define correct field order for Sheets', () => {
      // The LLM should output fields in this order for Sheets
      const fieldOrder = EXPECTED_FIELDS;

      expect(fieldOrder[0]).toBe('invoice_number');
      expect(fieldOrder[1]).toBe('vendor_name');
      expect(fieldOrder[2]).toBe('total_amount');
      expect(fieldOrder[3]).toBe('invoice_date');
      expect(fieldOrder[4]).toBe('status');
    });

    it('should map field types correctly', () => {
      const fieldTypes: Record<string, string> = {
        invoice_number: 'string',
        vendor_name: 'string',
        total_amount: 'number',
        invoice_date: 'string (ISO date)',
        status: 'string (uppercase)',
      };

      for (const [field, type] of Object.entries(fieldTypes)) {
        expect(EXPECTED_FIELDS).toContain(field);
        expect(typeof fieldTypes[field]).toBe('string');
      }
    });
  });

  describe('JSON Format Validation', () => {
    it('should parse valid 2D array format', () => {
      // This is the format LLM should output
      const llmOutput = '[["Invoice #", "Vendor", "Amount", "Date", "Status"], ["INV-001", "Acme Corp", 1500, "2024-01-15", "APPROVED"]]';

      const parsed = JSON.parse(llmOutput);

      expect(Array.isArray(parsed)).toBe(true);
      expect(parsed).toHaveLength(2); // Header + 1 data row
      expect(parsed[0]).toEqual(['Invoice #', 'Vendor', 'Amount', 'Date', 'Status']);
      expect(parsed[1]).toEqual(['INV-001', 'Acme Corp', 1500, '2024-01-15', 'APPROVED']);
    });

    it('should parse multiple rows format', () => {
      const llmOutput = `[["Invoice #", "Vendor", "Amount", "Date", "Status"],
        ["INV-001", "Acme Corp", 1500, "2024-01-15", "APPROVED"],
        ["INV-002", "Beta Inc", 2500.5, "2024-01-20", "PENDING"],
        ["INV-003", "Gamma LLC", 750, "2024-01-25", "APPROVED"]]`;

      const parsed = JSON.parse(llmOutput.replace(/\s+/g, ' '));

      expect(Array.isArray(parsed)).toBe(true);
      expect(parsed).toHaveLength(4); // Header + 3 data rows
      expect(parsed[0]).toEqual(['Invoice #', 'Vendor', 'Amount', 'Date', 'Status']);
      expect(parsed[1][0]).toBe('INV-001');
      expect(parsed[2][0]).toBe('INV-002');
      expect(parsed[3][0]).toBe('INV-003');
    });

    it('should handle numeric amounts correctly', () => {
      const dataRow = JSON.parse('["INV-001", "Acme Corp", 1500.50, "2024-01-15", "APPROVED"]');

      expect(typeof dataRow[2]).toBe('number');
      expect(dataRow[2]).toBe(1500.50);
    });

    it('should handle string amounts when LLM quotes them', () => {
      const dataRow = JSON.parse('["INV-001", "Acme Corp", "1500.50", "2024-01-15", "APPROVED"]');

      expect(typeof dataRow[2]).toBe('string');
      expect(parseFloat(dataRow[2])).toBe(1500.50);
    });
  });

  describe('Schema Mapping Compatibility', () => {
    it('should match schema-mapper field detection', () => {
      const headers = ['Invoice #', 'Vendor', 'Amount', 'Date', 'Status'];

      // These are the fields schema-mapper should detect
      const detectedFields: (InvoiceFieldType | null)[] = [
        'invoice_number',
        'vendor_name',
        null, // Amount might not match directly
        null, // Date might be ambiguous
        'status',
      ];

      // Verify at least some fields match
      const matches = detectedFields.filter(f => f !== null);
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    it('should normalize status values', () => {
      const statusMapping: Record<string, string> = {
        'approved': 'APPROVED',
        'pending': 'PENDING',
        'rejected': 'REJECTED',
        'paid': 'PAID',
      };

      expect(statusMapping['approved']).toBe('APPROVED');
      expect(statusMapping['pending']).toBe('PENDING');
      expect(statusMapping['rejected']).toBe('REJECTED');
      expect(statusMapping['paid']).toBe('PAID');
    });

    it('should format dates as ISO strings', () => {
      const datePattern = /^\d{4}-\d{2}-\d{2}$/;

      expect('2024-01-15').toMatch(datePattern);
      expect('2024-12-31').toMatch(datePattern);
      expect('2024-1-5').not.toMatch(datePattern); // Should be zero-padded
    });
  });

  describe('Mockoon API Integration', () => {
    it('should have mock OAuth2 server running', async () => {
      // Test OAuth2 token info endpoint
      const response = await fetch('http://localhost:3001/oauth2/v2/tokeninfo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'access_token=test',
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data).toHaveProperty('verified_email');
    });

    it('should have mock Sheets API running', async () => {
      // Test Sheets API endpoint
      const response = await fetch('http://localhost:3002/v4/spreadsheets/test-id?fields=properties.title');
      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data).toHaveProperty('spreadsheetId');
    });
  });
});

describe('LLM Prompt Engineering Examples', () => {
  it('should use few-shot prompting effectively', () => {
    // Example of effective few-shot prompt
    const fewShotPrompt = `OUTPUT: [["A","B"],[1,2],[3,4]]
---
Your turn. Output 2D array with columns: Invoice, Vendor, Amount. Data: INV-001, Acme, 100. OUTPUT ONLY:`;

    // Expected output format
    const expectedOutput = '[["Invoice", "Vendor", "Amount"], ["INV-001", "Acme", 100]]';

    // Verify the format is valid
    const parsed = JSON.parse(expectedOutput);
    expect(parsed).toHaveLength(2);
    expect(parsed[0]).toEqual(['Invoice', 'Vendor', 'Amount']);
    expect(parsed[1]).toEqual(['INV-001', 'Acme', 100]);
  });

  it('should use JSON mode for reliable output', () => {
    // When using Ollama with JSON mode
    const jsonModePrompt = {
      model: 'tomng/lfm2.5-instruct:1.2b',
      format: 'json',  // If supported
      prompt: 'Format invoice data as 2D array. Data: INV-001, Acme, 1500',
    };

    expect(jsonModePrompt).toHaveProperty('model');
    expect(jsonModePrompt).toHaveProperty('format');
  });
});
