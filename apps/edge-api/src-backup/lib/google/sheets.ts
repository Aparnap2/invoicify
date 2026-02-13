/**
 * Google Sheets API Client
 *
 * Handles all Google Sheets API v4 operations:
 * - Read values from spreadsheets
 * - Write/update values
 * - Append rows
 * - Get spreadsheet metadata
 *
 * Run tests with: pnpm test -- test/lib/google/sheets.test.ts
 */

import type {
  SheetValueRange,
  GetValuesResponse,
  AppendValuesRequest,
  AppendValuesResponse,
  Spreadsheet,
  Sheet,
  ValueInputOption,
  ValueRenderOption,
  GoogleApiResponse,
} from './types.js';

const DEFAULT_API_BASE = 'https://sheets.googleapis.com/v4';

/**
 * Google Sheets API Client
 */
export class GoogleSheetsClient {
  private accessToken: string;
  private apiBase: string;
  private mockMode: boolean;
  private mockSheetsEndpoint: string;

  constructor(
    accessToken: string,
    options?: { apiBase?: string; mockMode?: boolean; mockSheetsEndpoint?: string }
  ) {
    this.accessToken = accessToken;
    this.apiBase = options?.apiBase || DEFAULT_API_BASE;
    this.mockMode = options?.mockMode || !accessToken || accessToken.startsWith('mock_');
    this.mockSheetsEndpoint = options?.mockSheetsEndpoint || 'http://localhost:3002/v4';
  }

  /**
   * Get spreadsheet metadata
   */
  async getSpreadsheet(spreadsheetId: string): Promise<GoogleApiResponse<Spreadsheet>> {
    if (this.mockMode) {
      return this.mockGetSpreadsheet(spreadsheetId);
    }

    try {
      const response = await fetch(`${this.apiBase}/spreadsheets/${spreadsheetId}`, {
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
        },
      });

      if (!response.ok) {
        return {
          success: false,
          error: { code: response.status, message: `HTTP ${response.status}` },
        };
      }

      const data: Spreadsheet = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: { code: 500, message: (error as Error).message },
      };
    }
  }

  /**
   * Get values from a range
   */
  async getValues(
    spreadsheetId: string,
    range: string,
    options?: {
      majorDimension?: 'ROWS' | 'COLUMNS';
      valueRenderOption?: ValueRenderOption;
    }
  ): Promise<GoogleApiResponse<GetValuesResponse>> {
    if (this.mockMode) {
      return this.mockGetValues(range);
    }

    try {
      const params = new URLSearchParams();
      if (options?.majorDimension) {
        params.set('majorDimension', options.majorDimension);
      }
      if (options?.valueRenderOption) {
        params.set('valueRenderOption', options.valueRenderOption);
      }

      const url = `${this.apiBase}/spreadsheets/${spreadsheetId}/values/${range}?${params.toString()}`;
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
        },
      });

      if (!response.ok) {
        return {
          success: false,
          error: { code: response.status, message: `HTTP ${response.status}` },
        };
      }

      const data: GetValuesResponse = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: { code: 500, message: (error as Error).message },
      };
    }
  }

  /**
   * Append values to a spreadsheet
   */
  async appendValues(
    spreadsheetId: string,
    range: string,
    request: AppendValuesRequest,
    options?: {
      valueInputOption?: ValueInputOption;
      insertDataOption?: 'OVERWRITE' | 'INSERT_ROWS';
      includeValuesInResponse?: boolean;
    }
  ): Promise<GoogleApiResponse<AppendValuesResponse>> {
    if (this.mockMode) {
      return this.mockAppendValues(spreadsheetId, range, request.values.length);
    }

    try {
      const params = new URLSearchParams();
      params.set('valueInputOption', options?.valueInputOption || 'USER_ENTERED');
      if (options?.insertDataOption) {
        params.set('insertDataOption', options.insertDataOption);
      }
      if (options?.includeValuesInResponse) {
        params.set('includeValuesInResponse', 'true');
      }

      const url = `${this.apiBase}/spreadsheets/${spreadsheetId}/values/${range}:append?${params.toString()}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          values: request.values,
          majorDimension: request.majorDimension || 'ROWS',
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        return {
          success: false,
          error: { code: response.status, message: error || `HTTP ${response.status}` },
        };
      }

      const data: AppendValuesResponse = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: { code: 500, message: (error as Error).message },
      };
    }
  }

  /**
   * Update values in a range
   */
  async updateValues(
    spreadsheetId: string,
    range: string,
    values: unknown[][],
    options?: {
      valueInputOption?: ValueInputOption;
      includeValuesInResponse?: boolean;
    }
  ): Promise<GoogleApiResponse<AppendValuesResponse>> {
    if (this.mockMode) {
      return this.mockUpdateValues(spreadsheetId, range, values.length);
    }

    try {
      const params = new URLSearchParams();
      params.set('valueInputOption', options?.valueInputOption || 'USER_ENTERED');
      if (options?.includeValuesInResponse) {
        params.set('includeValuesInResponse', 'true');
      }

      const url = `${this.apiBase}/spreadsheets/${spreadsheetId}/values/${range}?${params.toString()}`;
      const response = await fetch(url, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          values,
          majorDimension: 'ROWS',
        }),
      });

      if (!response.ok) {
        return {
          success: false,
          error: { code: response.status, message: `HTTP ${response.status}` },
        };
      }

      const data: AppendValuesResponse = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: { code: 500, message: (error as Error).message },
      };
    }
  }

  /**
   * Clear values from a range
   */
  async clearValues(
    spreadsheetId: string,
    range: string
  ): Promise<GoogleApiResponse<{ spreadsheetId: string; clearedRange: string }>> {
    if (this.mockMode) {
      return {
        success: true,
        data: { spreadsheetId, clearedRange: range },
      };
    }

    try {
      const response = await fetch(`${this.apiBase}/spreadsheets/${spreadsheetId}/values/${range}:clear`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        return {
          success: false,
          error: { code: response.status, message: `HTTP ${response.status}` },
        };
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: { code: 500, message: (error as Error).message },
      };
    }
  }

  // ============ Mock Methods for Testing ============

  /**
   * Mock get spreadsheet
   */
  private mockGetSpreadsheet(spreadsheetId: string): GoogleApiResponse<Spreadsheet> {
    const spreadsheet: Spreadsheet = {
      spreadsheetId,
      properties: {
        title: `Mock Spreadsheet ${spreadsheetId.slice(0, 8)}`,
        locale: 'en_US',
        timeZone: 'America/New_York',
      },
      sheets: [
        {
          properties: {
            sheetId: 0,
            title: 'Invoices',
            index: 0,
            sheetType: 'GRID',
            gridProperties: { rowCount: 1000, columnCount: 26 },
          },
        },
        {
          properties: {
            sheetId: 1,
            title: 'Summary',
            index: 1,
            sheetType: 'GRID',
            gridProperties: { rowCount: 100, columnCount: 10 },
          },
        },
      ],
    };
    return { success: true, data: spreadsheet };
  }

  /**
   * Mock get values
   */
  private mockGetValues(range: string): GoogleApiResponse<GetValuesResponse> {
    // Parse range to extract sheet name
    const sheetName = range.split('!')[0] || 'Sheet1';

    const response: GetValuesResponse = {
      range: `${sheetName}!A1:E5`,
      majorDimension: 'ROWS',
      values: [
        ['Invoice #', 'Vendor', 'Amount', 'Date', 'Status'],
        ['INV001', 'Acme Corp', '1500.00', '2024-01-15', 'Approved'],
        ['INV002', 'Beta Inc', '2500.00', '2024-01-16', 'Pending'],
        ['INV003', 'Gamma LLC', '1750.00', '2024-01-17', 'Approved'],
      ],
    };
    return { success: true, data: response };
  }

  /**
   * Mock append values
   */
  private mockAppendValues(
    spreadsheetId: string,
    range: string,
    rowCount: number
  ): GoogleApiResponse<AppendValuesResponse> {
    const sheetName = range.split('!')[0] || 'Sheet1';

    const response: AppendValuesResponse = {
      spreadsheetId,
      tableRange: `${sheetName}!A1:E3`,
      updates: {
        spreadsheetId,
        updatedRange: `${sheetName}!A4:E${3 + rowCount}`,
        updatedRows: rowCount,
        updatedColumns: 5,
        updatedCells: rowCount * 5,
      },
    };
    return { success: true, data: response };
  }

  /**
   * Mock update values
   */
  private mockUpdateValues(
    spreadsheetId: string,
    range: string,
    rowCount: number
  ): GoogleApiResponse<AppendValuesResponse> {
    const sheetName = range.split('!')[0] || 'Sheet1';

    const response: AppendValuesResponse = {
      spreadsheetId,
      tableRange: '',
      updates: {
        spreadsheetId,
        updatedRange: `${sheetName}!${range}`,
        updatedRows: rowCount,
        updatedColumns: 0,
        updatedCells: rowCount,
      },
    };
    return { success: true, data: response };
  }
}

/**
 * Helper to convert column index to A1 notation
 */
export function columnIndexToA1(index: number): string {
  let column = '';
  let num = index + 1; // 1-indexed

  while (num > 0) {
    const remainder = (num - 1) % 26;
    column = String.fromCharCode(65 + remainder) + column;
    num = Math.floor((num - 1) / 26);
  }

  return column;
}

/**
 * Helper to convert A1 notation to column index
 */
export function columnA1ToIndex(a1: string): number {
  let index = 0;
  for (let i = 0; i < a1.length; i++) {
    index = index * 26 + a1.charCodeAt(i) - 64;
  }
  return index - 1;
}

/**
 * Helper to build A1 range from sheet name and cell range
 */
export function buildRange(sheetName: string, startCell: string, endCell?: string): string {
  if (endCell) {
    return `${sheetName}!${startCell}:${endCell}`;
  }
  return `${sheetName}!${startCell}`;
}
