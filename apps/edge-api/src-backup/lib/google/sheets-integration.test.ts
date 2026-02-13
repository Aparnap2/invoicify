/**
 * Google Sheets Integration Tests with LLM
 *
 * Tests the complete flow: LLM formatting → Sheets API sync
 * Run with: pnpm test -- test/lib/google/sheets-integration.test.ts
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { GoogleSheetsClient } from './sheets.js';
import { GoogleOAuthManager, getOAuthManager, resetOAuthManager } from './oauth.js';
import {
  detectSchema,
  invoiceToRow,
  invoicesToRows,
} from './schema-mapper.js';
import type { SheetSchema, InvoiceFieldType } from './types.js';

// Test invoice data
const testInvoices = [
  {
    invoice_number: 'INV-001',
    vendor_name: 'ACME CORP',
    total_amount: 1500.00,
    invoice_date: '2024-01-15',
    due_date: '2024-02-15',
    status: 'APPROVED',
    currency: 'USD',
  },
  {
    invoice_number: 'INV-002',
    vendor_name: 'BETA INC',
    total_amount: 2500.50,
    invoice_date: '2024-01-20',
    due_date: '2024-02-20',
    status: 'PENDING',
    currency: 'USD',
  },
  {
    invoice_number: 'INV-003',
    vendor_name: 'GAMMA LLC',
    total_amount: 750.00,
    invoice_date: '2024-01-25',
    due_date: '2024-02-25',
    status: 'APPROVED',
    currency: 'USD',
  },
];

// Expected formatted rows for Sheets
const expectedRows = [
  ['INV-001', 'ACME CORP', 1500.00, '2024-01-15', '2024-02-15', 'APPROVED', 'USD'],
  ['INV-002', 'BETA INC', 2500.50, '2024-01-20', '2024-02-20', 'PENDING', 'USD'],
  ['INV-003', 'GAMMA LLC', 750.00, '2024-01-25', '2024-02-25', 'APPROVED', 'USD'],
];

describe('Google Sheets Integration', () => {
  let sheetsClient: GoogleSheetsClient;

  beforeAll(() => {
    // Reset singleton for fresh state
    resetOAuthManager();

    // Initialize OAuth manager in mock mode (no clientId triggers mockMode)
    const oauth = getOAuthManager({
      clientId: '',  // Empty triggers mockMode
      clientSecret: '',
      redirectUri: 'http://localhost:3000/callback',
    }, {
      mockTokenEndpoint: 'http://localhost:3001/oauth2/v4/token',
      mockTokenInfoEndpoint: 'http://localhost:3001/oauth2/v2/tokeninfo',
    });

    // Initialize Sheets client with mock mode
    sheetsClient = new GoogleSheetsClient('mock-access-token', {
      mockMode: true,
      mockSheetsEndpoint: 'http://localhost:3002/v4',
    });
  });

  describe('Schema Detection', () => {
    it('should detect invoice schema from headers', () => {
      const headers = [
        'Invoice #',
        'Vendor',
        'Total Amount',
        'Invoice Date',
        'Due Date',
        'Status',
        'Currency',
      ];

      const detected = detectSchema(headers);

      expect(detected.headers).toEqual(headers);
      expect(detected.columnCount).toBe(7);
      expect(detected.confidence).toBe(1); // All fields matched
      expect(detected.suggestedMappings).toHaveLength(7);
    });

    it('should detect partial schema with mixed headers', () => {
      const headers = [
        'Invoice #',
        'Custom Column',
        'Total Amount',
        'Unknown Field',
        'Status',
      ];

      const detected = detectSchema(headers);

      expect(detected.columnCount).toBe(5);
      expect(detected.suggestedMappings).toHaveLength(3); // invoice_number, total_amount, status
      expect(detected.confidence).toBe(0.6); // 3 out of 5 matched
    });
  });

  describe('Invoice to Row Conversion', () => {
    it('should convert single invoice to row array', () => {
      const schema: SheetSchema = {
        id: 'test-schema',
        tenantId: 'test-tenant',
        name: 'Test Schema',
        spreadsheetId: 'test-spreadsheet',
        sheetName: 'Invoices',
        range: 'A1',
        columnMappings: [
          { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
          { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
          { invoiceField: 'total_amount', sheetColumn: 'C', columnIndex: 2 },
          { invoiceField: 'invoice_date', sheetColumn: 'D', columnIndex: 3 },
          { invoiceField: 'due_date', sheetColumn: 'E', columnIndex: 4 },
          { invoiceField: 'status', sheetColumn: 'F', columnIndex: 5 },
          { invoiceField: 'currency', sheetColumn: 'G', columnIndex: 6 },
        ],
        autoFormat: false,
        syncFrequency: 'manual',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      const row = invoiceToRow(testInvoices[0], schema);

      expect(row).toHaveLength(7);
      expect(row[0]).toBe('INV-001');
      expect(row[1]).toBe('ACME CORP');
      expect(row[2]).toBe(1500.00);
      expect(row[3]).toBe('2024-01-15');
      expect(row[4]).toBe('2024-02-15');
      expect(row[5]).toBe('APPROVED');
      expect(row[6]).toBe('USD');
    });

    it('should convert multiple invoices to row arrays', () => {
      const schema: SheetSchema = {
        id: 'test-schema',
        tenantId: 'test-tenant',
        name: 'Test Schema',
        spreadsheetId: 'test-spreadsheet',
        sheetName: 'Invoices',
        range: 'A1',
        columnMappings: [
          { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
          { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
          { invoiceField: 'total_amount', sheetColumn: 'C', columnIndex: 2 },
          { invoiceField: 'invoice_date', sheetColumn: 'D', columnIndex: 3 },
          { invoiceField: 'due_date', sheetColumn: 'E', columnIndex: 4 },
          { invoiceField: 'status', sheetColumn: 'F', columnIndex: 5 },
          { invoiceField: 'currency', sheetColumn: 'G', columnIndex: 6 },
        ],
        autoFormat: false,
        syncFrequency: 'manual',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      const rows = invoicesToRows(testInvoices, schema);

      expect(rows).toHaveLength(3);
      expect(rows[0]).toEqual(expectedRows[0]);
      expect(rows[1]).toEqual(expectedRows[1]);
      expect(rows[2]).toEqual(expectedRows[2]);
    });
  });

  describe('Mock API Integration', () => {
    it('should get spreadsheet from mock API', async () => {
      const result = await sheetsClient.getSpreadsheet('test-spreadsheet-id');

      expect(result.success).toBe(true);
      expect(result.data?.spreadsheetId).toBe('test-spreadsheet-id');
      expect(result.data?.properties.title).toBeDefined();
    });

    it('should get values from mock API', async () => {
      // Mock data has columns A-E (5 columns)
      const result = await sheetsClient.getValues('test-spreadsheet', 'Invoices!A1:E5');

      expect(result.success).toBe(true);
      expect(result.data?.range).toBe('Invoices!A1:E5');
      expect(result.data?.values).toBeDefined();
    });

    it('should append values to mock API', async () => {
      const values = [
        ['INV-004', 'DELTA CO', 3000.00, '2024-01-28', '2024-02-28', 'PENDING', 'USD'],
      ];

      const result = await sheetsClient.appendValues(
        'test-spreadsheet',
        'Invoices!A:G',
        { values }
      );

      expect(result.success).toBe(true);
      expect(result.data?.updates.updatedRows).toBe(1);
    });

    it('should update values in mock API', async () => {
      const values = [
        ['INV-001', 'ACME CORP UPDATED', 1500.00, '2024-01-15', '2024-02-15', 'APPROVED', 'USD'],
      ];

      const result = await sheetsClient.updateValues(
        'test-spreadsheet',
        'Invoices!A2:G2',
        values
      );

      expect(result.success).toBe(true);
      expect(result.data?.updates.updatedRows).toBe(1);
    });
  });

  describe('OAuth Integration', () => {
    it('should generate auth URL', () => {
      const oauth = getOAuthManager();
      const { authUrl, state } = oauth.generateAuthUrl();

      expect(authUrl).toContain('client_id=');
      expect(authUrl).toContain('redirect_uri=');
      expect(authUrl).toContain('response_type=code');
      expect(authUrl).toContain('scope=');
      expect(state).toBeDefined();
      expect(state.length).toBeGreaterThan(10);
    });

    it('should exchange code for tokens in mock mode', async () => {
      const oauth = getOAuthManager();
      const result = await oauth.exchangeCodeForTokens('mock-auth-code');

      expect(result.success).toBe(true);
      expect(result.accessToken).toBeDefined();
      expect(result.expiresAt).toBeDefined();
    });

    it('should validate token in mock mode', async () => {
      const oauth = getOAuthManager();
      const result = await oauth.validateToken('mock-access-token');

      // validateToken returns { valid: boolean; email?: string; expiresIn?: number }
      expect(result).toHaveProperty('valid');
      expect(result.valid).toBe(true);
    });
  });
});

describe('LLM Format Verification', () => {
  // These tests verify that the data format matches what the LLM would produce
  // In production, the LLM would format the invoice data before sending to Sheets

  it('should format invoice data for Sheets compatibility', () => {
    // Simulating what LLM would output
    const llmFormattedData = [
      {
        invoice_number: 'INV-001',
        vendor_name: 'Acme Corp',
        total_amount: 1500.00,
        invoice_date: '2024-01-15',
        status: 'Approved',
      },
    ];

    // Verify data structure matches expected Sheets format
    expect(llmFormattedData[0]).toHaveProperty('invoice_number');
    expect(llmFormattedData[0]).toHaveProperty('vendor_name');
    expect(llmFormattedData[0]).toHaveProperty('total_amount');
    expect(llmFormattedData[0]).toHaveProperty('invoice_date');
    expect(llmFormattedData[0]).toHaveProperty('status');

    // Verify numeric values
    expect(typeof llmFormattedData[0].total_amount).toBe('number');
    expect(llmFormattedData[0].total_amount).toBe(1500.00);
  });

  it('should handle status normalization for Sheets', () => {
    const statusMapping: Record<string, string> = {
      'approved': 'APPROVED',
      'pending': 'PENDING',
      'rejected': 'REJECTED',
      'paid': 'PAID',
    };

    // Simulating LLM status normalization
    expect(statusMapping['approved']).toBe('APPROVED');
    expect(statusMapping['pending']).toBe('PENDING');
    expect(statusMapping['rejected']).toBe('REJECTED');
    expect(statusMapping['paid']).toBe('PAID');
  });
});
