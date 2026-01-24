/**
 * Google Sheets Client Unit Tests
 *
 * Run with: pnpm test -- test/lib/google/sheets.test.ts
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  GoogleSheetsClient,
  columnIndexToA1,
  columnA1ToIndex,
  buildRange,
} from './sheets.js';

describe('GoogleSheetsClient', () => {
  let client: GoogleSheetsClient;

  beforeEach(() => {
    // Initialize in mock mode
    client = new GoogleSheetsClient('mock_access_token', {
      mockMode: true,
      mockSheetsEndpoint: 'http://localhost:3002/v4',
    });
  });

  describe('constructor', () => {
    it('should initialize in mock mode without token', () => {
      expect(client).toBeInstanceOf(GoogleSheetsClient);
    });

    it('should use provided access token', () => {
      const customClient = new GoogleSheetsClient('real-token-123');

      expect(customClient).toBeInstanceOf(GoogleSheetsClient);
    });
  });

  describe('getSpreadsheet', () => {
    it('should return mock spreadsheet data', async () => {
      const result = await client.getSpreadsheet('spreadsheet-123');

      expect(result.success).toBe(true);
      expect(result.data?.spreadsheetId).toBe('spreadsheet-123');
      expect(result.data?.properties.title).toBeDefined();
      expect(result.data?.sheets).toHaveLength(2);
      expect(result.data?.sheets[0].properties.title).toBe('Invoices');
    });

    it('should include spreadsheet properties', async () => {
      const result = await client.getSpreadsheet('test-id');

      expect(result.data?.properties.locale).toBe('en_US');
      expect(result.data?.properties.timeZone).toBe('America/New_York');
    });
  });

  describe('getValues', () => {
    it('should return mock values', async () => {
      const result = await client.getValues('spreadsheet-123', 'Sheet1!A1:E5');

      expect(result.success).toBe(true);
      expect(result.data?.range).toBe('Sheet1!A1:E5');
      expect(result.data?.majorDimension).toBe('ROWS');
      expect(result.data?.values).toHaveLength(4); // Header + 3 data rows
      expect(result.data?.values[0]).toEqual([
        'Invoice #',
        'Vendor',
        'Amount',
        'Date',
        'Status',
      ]);
    });

    it('should return data rows with correct values', async () => {
      const result = await client.getValues('spreadsheet-123', 'Invoices');

      expect(result.data?.values[1]).toContain('INV001');
      expect(result.data?.values[1]).toContain('Acme Corp');
    });
  });

  describe('appendValues', () => {
    it('should append values and return response', async () => {
      const request = {
        values: [
          ['INV004', 'Delta Co', '3000.00', '2024-01-18', 'Pending'],
          ['INV005', 'Epsilon Inc', '4500.00', '2024-01-19', 'Approved'],
        ],
      };

      const result = await client.appendValues(
        'spreadsheet-123',
        'Sheet1!A:E',
        request
      );

      expect(result.success).toBe(true);
      expect(result.data?.spreadsheetId).toBe('spreadsheet-123');
      expect(result.data?.updates.updatedRows).toBe(2);
      expect(result.data?.updates.updatedCells).toBe(10);
      expect(result.data?.updates.updatedRange).toContain('A4');
    });

    it('should handle single row append', async () => {
      const request = {
        values: [['INV006', 'Zeta LLC', '1200.00', '2024-01-20', 'Approved']],
      };

      const result = await client.appendValues('spreadsheet-123', 'Invoices!A:E', request);

      expect(result.success).toBe(true);
      expect(result.data?.updates.updatedRows).toBe(1);
      expect(result.data?.updates.updatedCells).toBe(5);
    });

    it('should support custom value input option', async () => {
      const request = { values: [['test']] };

      const result = await client.appendValues('spreadsheet-123', 'Test', request, {
        valueInputOption: 'RAW',
      });

      expect(result.success).toBe(true);
    });
  });

  describe('updateValues', () => {
    it('should update values and return response', async () => {
      const values = [
        ['INV001', 'Updated Vendor', '2000.00', '2024-01-15', 'Approved'],
      ];

      const result = await client.updateValues('spreadsheet-123', 'Sheet1!A2:E2', values);

      expect(result.success).toBe(true);
      expect(result.data?.updates.updatedRows).toBe(1);
    });

    it('should handle multiple rows update', async () => {
      const values = [
        ['INV001', 'Vendor A', '100'],
        ['INV002', 'Vendor B', '200'],
      ];

      const result = await client.updateValues('spreadsheet-123', 'Sheet1!A2:B3', values);

      expect(result.success).toBe(true);
      expect(result.data?.updates.updatedRows).toBe(2);
    });
  });

  describe('clearValues', () => {
    it('should clear values and return cleared range', async () => {
      const result = await client.clearValues('spreadsheet-123', 'Sheet1!A1:E10');

      expect(result.success).toBe(true);
      expect(result.data?.spreadsheetId).toBe('spreadsheet-123');
      expect(result.data?.clearedRange).toBe('Sheet1!A1:E10');
    });
  });
});

describe('Helper Functions', () => {
  describe('columnIndexToA1', () => {
    it('should convert index 0 to A', () => {
      expect(columnIndexToA1(0)).toBe('A');
    });

    it('should convert index 25 to Z', () => {
      expect(columnIndexToA1(25)).toBe('Z');
    });

    it('should convert index 26 to AA', () => {
      expect(columnIndexToA1(26)).toBe('AA');
    });

    it('should convert index 27 to AB', () => {
      expect(columnIndexToA1(27)).toBe('AB');
    });

    it('should convert index 51 to AZ', () => {
      expect(columnIndexToA1(51)).toBe('AZ');
    });

    it('should convert index 52 to BA', () => {
      expect(columnIndexToA1(52)).toBe('BA');
    });

    it('should convert index 701 to ZZ', () => {
      expect(columnIndexToA1(701)).toBe('ZZ');
    });

    it('should convert index 702 to AAA', () => {
      expect(columnIndexToA1(702)).toBe('AAA');
    });
  });

  describe('columnA1ToIndex', () => {
    it('should convert A to index 0', () => {
      expect(columnA1ToIndex('A')).toBe(0);
    });

    it('should convert Z to index 25', () => {
      expect(columnA1ToIndex('Z')).toBe(25);
    });

    it('should convert AA to index 26', () => {
      expect(columnA1ToIndex('AA')).toBe(26);
    });

    it('should convert AB to index 27', () => {
      expect(columnA1ToIndex('AB')).toBe(27);
    });

    it('should convert AZ to index 51', () => {
      expect(columnA1ToIndex('AZ')).toBe(51);
    });

    it('should convert BA to index 52', () => {
      expect(columnA1ToIndex('BA')).toBe(52);
    });

    it('should convert ZZ to index 701', () => {
      expect(columnA1ToIndex('ZZ')).toBe(701);
    });

    it('should convert AAA to index 702', () => {
      expect(columnA1ToIndex('AAA')).toBe(702);
    });
  });

  describe('buildRange', () => {
    it('should build range with start and end cell', () => {
      expect(buildRange('Sheet1', 'A1', 'E10')).toBe('Sheet1!A1:E10');
    });

    it('should build range with only start cell', () => {
      expect(buildRange('Sheet1', 'A1')).toBe('Sheet1!A1');
    });

    it('should handle sheet names with spaces', () => {
      expect(buildRange('Invoice Data', 'A1', 'Z100')).toBe('Invoice Data!A1:Z100');
    });
  });

  describe('A1 conversion roundtrip', () => {
    it('should roundtrip indices correctly', () => {
      const indices = [0, 1, 25, 26, 27, 52, 701, 702, 1000, 2000];

      for (const index of indices) {
        const a1 = columnIndexToA1(index);
        const backToIndex = columnA1ToIndex(a1);
        expect(backToIndex).toBe(index);
      }
    });
  });
});
