/**
 * Google Types Unit Tests
 *
 * Run with: pnpm test -- test/lib/google/types.test.ts
 */

import { describe, it, expect } from 'vitest';
import type {
  GoogleOAuthToken,
  StoredGoogleCredentials,
  SheetValueRange,
  AppendValuesRequest,
  ColumnMapping,
  SheetSchema,
  DetectedSchema,
  SyncHistory,
  InvoiceFieldType,
} from './types';

describe('Google OAuth Types', () => {
  describe('GoogleOAuthToken', () => {
    it('should create a valid token response', () => {
      const token: GoogleOAuthToken = {
        access_token: 'ya29.test123',
        refresh_token: '1//test456',
        expires_in: 3600,
        scope: 'https://www.googleapis.com/auth/spreadsheets',
        token_type: 'Bearer',
      };

      expect(token.access_token).toBeDefined();
      expect(token.refresh_token).toBeDefined();
      expect(token.expires_in).toBe(3600);
      expect(token.token_type).toBe('Bearer');
    });

    it('should allow optional refresh_token', () => {
      const token: GoogleOAuthToken = {
        access_token: 'ya29.test123',
        expires_in: 3600,
        scope: 'https://www.googleapis.com/auth/spreadsheets',
        token_type: 'Bearer',
      };

      expect(token.refresh_token).toBeUndefined();
    });
  });

  describe('StoredGoogleCredentials', () => {
    it('should store all credential fields', () => {
      const credentials: StoredGoogleCredentials = {
        userId: 'user-123',
        accessToken: 'ya29.test',
        refreshToken: '1//test',
        expiresAt: Date.now() + 3600000,
        scope: 'https://www.googleapis.com/auth/spreadsheets',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(credentials.userId).toBe('user-123');
      expect(credentials.expiresAt).toBeGreaterThan(Date.now());
    });
  });
});

describe('Google Sheets Types', () => {
  describe('SheetValueRange', () => {
    it('should create a value range with rows dimension', () => {
      const range: SheetValueRange = {
        range: 'Sheet1!A1:D5',
        majorDimension: 'ROWS',
        values: [
          ['Header1', 'Header2', 'Header3', 'Header4'],
          ['Value1', 'Value2', 'Value3', 'Value4'],
        ],
      };

      expect(range.majorDimension).toBe('ROWS');
      expect(range.values).toHaveLength(2);
      expect(range.values[0]).toHaveLength(4);
    });

    it('should create a value range with columns dimension', () => {
      const range: SheetValueRange = {
        range: 'Sheet1!A1:B4',
        majorDimension: 'COLUMNS',
        values: [
          ['A1', 'A2', 'A3'],
          ['B1', 'B2', 'B3'],
        ],
      };

      expect(range.majorDimension).toBe('COLUMNS');
      expect(range.values).toHaveLength(2);
    });
  });

  describe('AppendValuesRequest', () => {
    it('should create append request with values array', () => {
      const request: AppendValuesRequest = {
        values: [
          ['INV001', 'Acme Corp', '1500.00'],
          ['INV002', 'Beta Inc', '2500.00'],
        ],
      };

      expect(request.values).toHaveLength(2);
      expect(request.values[0]).toContain('INV001');
    });

    it('should allow optional majorDimension', () => {
      const request: AppendValuesRequest = {
        values: [['test']],
        majorDimension: 'COLUMNS',
      };

      expect(request.majorDimension).toBe('COLUMNS');
    });
  });
});

describe('Schema Mapping Types', () => {
  describe('ColumnMapping', () => {
    it('should create a basic column mapping', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'vendor_name',
        sheetColumn: 'B',
        columnIndex: 1,
      };

      expect(mapping.invoiceField).toBe('vendor_name');
      expect(mapping.sheetColumn).toBe('B');
      expect(mapping.columnIndex).toBe(1);
    });

    it('should create mapping with transform', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'invoice_date',
        sheetColumn: 'D',
        columnIndex: 3,
        transform: {
          type: 'date_format',
          format: 'MM/dd/yyyy',
        },
      };

      expect(mapping.transform?.type).toBe('date_format');
      expect(mapping.transform?.format).toBe('MM/dd/yyyy');
    });
  });

  describe('SheetSchema', () => {
    it('should create a full schema configuration', () => {
      const schema: SheetSchema = {
        id: 'schema-123',
        tenantId: 'tenant-456',
        name: 'Monthly Invoices',
        spreadsheetId: 'spreadsheet-789',
        sheetName: 'Invoices',
        range: 'Sheet1!A1',
        columnMappings: [
          { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
          { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
          { invoiceField: 'total_amount', sheetColumn: 'C', columnIndex: 2 },
        ],
        autoFormat: true,
        syncFrequency: 'daily',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(schema.columnMappings).toHaveLength(3);
      expect(schema.autoFormat).toBe(true);
      expect(schema.syncFrequency).toBe('daily');
    });
  });

  describe('DetectedSchema', () => {
    it('should represent auto-detected schema from sheet', () => {
      const detected: DetectedSchema = {
        headers: ['Invoice #', 'Vendor', 'Amount', 'Date'],
        columnCount: 4,
        rowCount: 100,
        suggestedMappings: [],
        confidence: 0.85,
      };

      expect(detected.headers).toHaveLength(4);
      expect(detected.confidence).toBe(0.85);
    });
  });
});

describe('InvoiceFieldType', () => {
  it('should include all expected field types', () => {
    const fields: InvoiceFieldType[] = [
      'id',
      'vendor_name',
      'invoice_number',
      'total_amount',
      'currency',
      'status',
      'due_date',
      'invoice_date',
      'confidence_score',
      'risk_score',
      'risk_level',
      'line_items',
      'payment_terms',
      'po_number',
      'notes',
    ];

    expect(fields).toContain('vendor_name');
    expect(fields).toContain('total_amount');
    expect(fields).toContain('invoice_date');
  });
});

describe('SyncHistory', () => {
  it('should track sync history entries', () => {
    const history: SyncHistory = {
      id: 'sync-123',
      schemaId: 'schema-456',
      status: 'success',
      rowsSynced: 50,
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
    };

    expect(history.status).toBe('success');
    expect(history.rowsSynced).toBe(50);
    expect(history.completedAt).toBeDefined();
  });

  it('should track failed syncs with error message', () => {
    const failedSync: SyncHistory = {
      id: 'sync-fail',
      schemaId: 'schema-456',
      status: 'failed',
      rowsSynced: 0,
      errorMessage: 'Sheet not found',
      startedAt: new Date().toISOString(),
    };

    expect(failedSync.status).toBe('failed');
    expect(failedSync.errorMessage).toBe('Sheet not found');
  });
});
