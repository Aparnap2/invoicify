/**
 * Schema Mapper Unit Tests
 *
 * Run with: pnpm test -- test/lib/google/schema-mapper.test.ts
 */

import { describe, it, expect } from 'vitest';
import {
  detectFieldType,
  createMappingFromHeader,
  detectSchema,
  transformValue,
  invoiceToRow,
  invoicesToRows,
  validateMappings,
  hasRequiredFields,
} from './schema-mapper.js';
import type { SheetSchema, ColumnMapping } from './types.js';

describe('Field Detection', () => {
  describe('detectFieldType', () => {
    it('should detect vendor_name field', () => {
      expect(detectFieldType('Vendor')).toBe('vendor_name');
      expect(detectFieldType('vendor')).toBe('vendor_name');
      expect(detectFieldType('Supplier')).toBe('vendor_name');
      expect(detectFieldType('Payee')).toBe('vendor_name');
    });

    it('should detect invoice_number field', () => {
      expect(detectFieldType('Invoice #')).toBe('invoice_number');
      expect(detectFieldType('Invoice Number')).toBe('invoice_number');
      expect(detectFieldType('inv #')).toBe('invoice_number');
      expect(detectFieldType('Invoice No')).toBe('invoice_number');
    });

    it('should detect total_amount field', () => {
      expect(detectFieldType('Total')).toBe('total_amount');
      expect(detectFieldType('Total Amount')).toBe('total_amount');
      expect(detectFieldType('Invoice Amount')).toBe('total_amount');
      expect(detectFieldType('Grand Total')).toBe('total_amount');
      expect(detectFieldType('Balance Due')).toBe('total_amount');
    });

    it('should detect date fields', () => {
      expect(detectFieldType('Invoice Date')).toBe('invoice_date');
      expect(detectFieldType('Due Date')).toBe('due_date');
      expect(detectFieldType('Bill Date')).toBe('invoice_date');
      expect(detectFieldType('Payment Due')).toBe('due_date');
    });

    it('should detect currency field', () => {
      expect(detectFieldType('Currency')).toBe('currency');
      expect(detectFieldType('Currency Code')).toBe('currency');
    });

    it('should detect status field', () => {
      expect(detectFieldType('Status')).toBe('status');
      expect(detectFieldType('Payment Status')).toBe('status');
      expect(detectFieldType('State')).toBe('status');
    });

    it('should return null for unknown fields', () => {
      expect(detectFieldType('Some Random Header')).toBeNull();
      expect(detectFieldType('Custom Field')).toBeNull();
      expect(detectFieldType('XYZ123')).toBeNull();
    });
  });

  describe('createMappingFromHeader', () => {
    it('should create mapping for vendor field', () => {
      const mapping = createMappingFromHeader('Vendor Name', 1);

      expect(mapping).not.toBeNull();
      expect(mapping?.invoiceField).toBe('vendor_name');
      expect(mapping?.sheetColumn).toBe('B');
      expect(mapping?.columnIndex).toBe(1);
    });

    it('should create mapping for invoice number field', () => {
      const mapping = createMappingFromHeader('Invoice #', 0);

      expect(mapping).not.toBeNull();
      expect(mapping?.invoiceField).toBe('invoice_number');
      expect(mapping?.sheetColumn).toBe('A');
      expect(mapping?.columnIndex).toBe(0);
    });

    it('should return null for unknown header', () => {
      const mapping = createMappingFromHeader('Random Field', 5);

      expect(mapping).toBeNull();
    });
  });
});

describe('Schema Detection', () => {
  describe('detectSchema', () => {
    it('should detect schema from headers', () => {
      const headers = ['Invoice #', 'Vendor', 'Amount', 'Date', 'Status'];

      const detected = detectSchema(headers);

      expect(detected.headers).toEqual(headers);
      expect(detected.columnCount).toBe(5);
      expect(detected.suggestedMappings).toHaveLength(5);
      expect(detected.confidence).toBe(1);
    });

    it('should calculate confidence for partial matches', () => {
      const headers = ['Invoice #', 'Custom Field', 'Amount', 'Unknown', 'Status'];

      const detected = detectSchema(headers);

      expect(detected.columnCount).toBe(5);
      expect(detected.suggestedMappings).toHaveLength(3);
      expect(detected.confidence).toBe(0.6); // 3 out of 5
    });

    it('should handle empty headers', () => {
      const detected = detectSchema([]);

      expect(detected.headers).toEqual([]);
      expect(detected.columnCount).toBe(0);
      expect(detected.suggestedMappings).toHaveLength(0);
      expect(detected.confidence).toBe(0);
    });

    it('should include correct field types', () => {
      const headers = ['Invoice #', 'Vendor', 'Total'];

      const detected = detectSchema(headers);

      const fields = detected.suggestedMappings.map((m) => m.invoiceField);
      expect(fields).toContain('invoice_number');
      expect(fields).toContain('vendor_name');
      expect(fields).toContain('total_amount');
    });
  });
});

describe('Data Transformation', () => {
  describe('transformValue', () => {
    it('should return value as-is without transform', () => {
      expect(transformValue('test', { invoiceField: 'vendor_name', sheetColumn: 'A', columnIndex: 0 })).toBe('test');
    });

    it('should uppercase text', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'vendor_name',
        sheetColumn: 'A',
        columnIndex: 0,
        transform: { type: 'uppercase' },
      };
      expect(transformValue('acme corp', mapping)).toBe('ACME CORP');
    });

    it('should lowercase text', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'vendor_name',
        sheetColumn: 'A',
        columnIndex: 0,
        transform: { type: 'lowercase' },
      };
      expect(transformValue('ACME CORP', mapping)).toBe('acme corp');
    });

    it('should handle null values', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'vendor_name',
        sheetColumn: 'A',
        columnIndex: 0,
      };
      expect(transformValue(null, mapping)).toBe('');
      expect(transformValue(undefined, mapping)).toBe('');
    });
  });

  describe('formatDate', () => {
    it('should format date with MM/dd/yyyy', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'invoice_date',
        sheetColumn: 'D',
        columnIndex: 3,
        transform: { type: 'date_format', format: 'MM/dd/yyyy' },
      };

      const result = transformValue('2024-01-15', mapping);
      expect(result).toBe('01/15/2024');
    });

    it('should format date with yyyy-MM-dd', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'invoice_date',
        sheetColumn: 'D',
        columnIndex: 3,
        transform: { type: 'date_format', format: 'yyyy-MM-dd' },
      };

      const result = transformValue('2024-01-15', mapping);
      expect(result).toBe('2024-01-15');
    });
  });

  describe('formatCurrency', () => {
    it('should format as USD by default', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'total_amount',
        sheetColumn: 'C',
        columnIndex: 2,
        transform: { type: 'currency_format' },
      };

      const result = transformValue(1500.5, mapping);
      expect(result).toContain('$');
      expect(result).toContain('1,500');
    });

    it('should format as EUR', () => {
      const mapping: ColumnMapping = {
        invoiceField: 'total_amount',
        sheetColumn: 'C',
        columnIndex: 2,
        transform: { type: 'currency_format', format: 'EUR' },
      };

      const result = transformValue(1000, mapping);
      expect(result).toContain('€');
    });
  });
});

describe('Invoice to Row Conversion', () => {
  it('should convert invoice to row array', () => {
    const schema: SheetSchema = {
      id: 'schema-1',
      tenantId: 'tenant-1',
      name: 'Test Schema',
      spreadsheetId: 'sheet-1',
      sheetName: 'Invoices',
      range: 'A1',
      columnMappings: [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
        { invoiceField: 'total_amount', sheetColumn: 'C', columnIndex: 2 },
      ],
      autoFormat: false,
      syncFrequency: 'manual',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const invoice = {
      invoice_number: 'INV001',
      vendor_name: 'Acme Corp',
      total_amount: 1500.0,
    };

    const row = invoiceToRow(invoice, schema);

    expect(row).toHaveLength(3);
    expect(row[0]).toBe('INV001');
    expect(row[1]).toBe('Acme Corp');
    expect(row[2]).toBe(1500.0);
  });

  it('should handle missing fields', () => {
    const schema: SheetSchema = {
      id: 'schema-1',
      tenantId: 'tenant-1',
      name: 'Test',
      spreadsheetId: 'sheet-1',
      sheetName: 'Invoices',
      range: 'A1',
      columnMappings: [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
      ],
      autoFormat: false,
      syncFrequency: 'manual',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const invoice = {
      invoice_number: 'INV001',
      // vendor_name is missing
    };

    const row = invoiceToRow(invoice, schema);

    expect(row[0]).toBe('INV001');
    expect(row[1]).toBe('');
  });

  it('should apply transformations', () => {
    const schema: SheetSchema = {
      id: 'schema-1',
      tenantId: 'tenant-1',
      name: 'Test',
      spreadsheetId: 'sheet-1',
      sheetName: 'Invoices',
      range: 'A1',
      columnMappings: [
        {
          invoiceField: 'vendor_name',
          sheetColumn: 'A',
          columnIndex: 0,
          transform: { type: 'uppercase' },
        },
      ],
      autoFormat: false,
      syncFrequency: 'manual',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const invoice = { vendor_name: 'acme corp' };
    const row = invoiceToRow(invoice, schema);

    expect(row[0]).toBe('ACME CORP');
  });
});

describe('invoicesToRows', () => {
  it('should convert multiple invoices to rows', () => {
    const schema: SheetSchema = {
      id: 'schema-1',
      tenantId: 'tenant-1',
      name: 'Test',
      spreadsheetId: 'sheet-1',
      sheetName: 'Invoices',
      range: 'A1',
      columnMappings: [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
      ],
      autoFormat: false,
      syncFrequency: 'manual',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const invoices = [
      { invoice_number: 'INV001', vendor_name: 'Acme Corp' },
      { invoice_number: 'INV002', vendor_name: 'Beta Inc' },
    ];

    const rows = invoicesToRows(invoices, schema);

    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual(['INV001', 'Acme Corp']);
    expect(rows[1]).toEqual(['INV002', 'Beta Inc']);
  });

  it('should handle empty array', () => {
    const schema: SheetSchema = {
      id: 'schema-1',
      tenantId: 'tenant-1',
      name: 'Test',
      spreadsheetId: 'sheet-1',
      sheetName: 'Invoices',
      range: 'A1',
      columnMappings: [],
      autoFormat: false,
      syncFrequency: 'manual',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const rows = invoicesToRows([], schema);
    expect(rows).toHaveLength(0);
  });
});

describe('Schema Validation', () => {
  describe('validateMappings', () => {
    it('should validate correct mappings', () => {
      const mappings: ColumnMapping[] = [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
      ];

      const result = validateMappings(mappings);

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect duplicate column indices', () => {
      const mappings: ColumnMapping[] = [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 0 }, // Duplicate
      ];

      const result = validateMappings(mappings);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Duplicate column index 0');
    });

    it('should detect duplicate invoice fields', () => {
      const mappings: ColumnMapping[] = [
        { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        { invoiceField: 'invoice_number', sheetColumn: 'B', columnIndex: 1 }, // Duplicate
      ];

      const result = validateMappings(mappings);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Duplicate invoice field 'invoice_number'");
    });
  });

  describe('hasRequiredFields', () => {
    it('should return true when all required fields present', () => {
      const schema: SheetSchema = {
        id: 'schema-1',
        tenantId: 'tenant-1',
        name: 'Test',
        spreadsheetId: 'sheet-1',
        sheetName: 'Invoices',
        range: 'A1',
        columnMappings: [
          { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
          { invoiceField: 'vendor_name', sheetColumn: 'B', columnIndex: 1 },
          { invoiceField: 'total_amount', sheetColumn: 'C', columnIndex: 2 },
        ],
        autoFormat: false,
        syncFrequency: 'manual',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(hasRequiredFields(schema, ['invoice_number', 'vendor_name'])).toBe(true);
    });

    it('should return false when required field missing', () => {
      const schema: SheetSchema = {
        id: 'schema-1',
        tenantId: 'tenant-1',
        name: 'Test',
        spreadsheetId: 'sheet-1',
        sheetName: 'Invoices',
        range: 'A1',
        columnMappings: [
          { invoiceField: 'invoice_number', sheetColumn: 'A', columnIndex: 0 },
        ],
        autoFormat: false,
        syncFrequency: 'manual',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      expect(hasRequiredFields(schema, ['invoice_number', 'vendor_name'])).toBe(false);
    });
  });
});
