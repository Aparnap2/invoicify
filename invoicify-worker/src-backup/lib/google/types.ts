/**
 * Google OAuth2 and Sheets API Types
 *
 * Type definitions for Google OAuth2 flow and Sheets API v4.
 */

// ============================================================================
// OAuth2 Types
// ============================================================================

/** OAuth2 token response from Google */
export interface GoogleOAuthToken {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  scope: string;
  token_type: 'Bearer';
  id_token?: string;
}

/** OAuth2 refresh request */
export interface GoogleOAuthRefreshRequest {
  client_id: string;
  client_secret: string;
  refresh_token: string;
  grant_type: 'refresh_token';
}

/** OAuth2 token request (authorization code exchange) */
export interface GoogleOAuthTokenRequest {
  client_id: string;
  client_secret: string;
  code: string;
  redirect_uri: string;
  grant_type: 'authorization_code';
}

/** Stored OAuth credentials for a user */
export interface StoredGoogleCredentials {
  userId: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // Unix timestamp
  scope: string;
  createdAt: string;
  updatedAt: string;
}

/** OAuth2 configuration */
export interface GoogleOAuthConfig {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  scopes: string[];
}

/** Authorization URL parameters */
export interface GoogleAuthUrlParams {
  access_type: 'offline' | 'online';
  prompt: 'consent' | 'none' | 'select_account';
  state?: string;
}

// ============================================================================
// Sheets API Types
// ============================================================================

/** Sheet value range for read/write operations */
export interface SheetValueRange {
  range: string; // A1 notation, e.g., "Sheet1!A1:D5"
  majorDimension: 'ROWS' | 'COLUMNS';
  values: unknown[][];
}

/** Append request body */
export interface AppendValuesRequest {
  values: unknown[][];
  majorDimension?: 'ROWS' | 'COLUMNS';
}

/** Append response from Sheets API */
export interface AppendValuesResponse {
  spreadsheetId: string;
  tableRange: string; // Range of the table before append
  updates: {
    spreadsheetId: string;
    updatedRange: string;
    updatedRows: number;
    updatedColumns: number;
    updatedCells: number;
  };
}

/** Get values response */
export interface GetValuesResponse {
  range: string;
  majorDimension: 'ROWS' | 'COLUMNS';
  values: unknown[][];
}

/** Spreadsheet metadata */
export interface Spreadsheet {
  spreadsheetId: string;
  properties: {
    title: string;
    locale: string;
    timeZone: string;
  };
  sheets: Sheet[];
}

/** Individual sheet within a spreadsheet */
export interface Sheet {
  properties: {
    sheetId: number;
    title: string;
    index: number;
    sheetType: 'GRID' | 'OBJECT';
    gridProperties: {
      rowCount: number;
      columnCount: number;
    };
  };
}

/** Value input option for writes */
export type ValueInputOption = 'RAW' | 'USER_ENTERED';

/** Insert data option for appends */
export type InsertDataOption = 'OVERWRITE' | 'INSERT_ROWS';

/** Value render option for reads */
export type ValueRenderOption = 'FORMATTED_VALUE' | 'UNFORMATTED_VALUE' | 'FORMULA';

/** Date time render option */
export type DateTimeRenderOption = 'SERIAL_NUMBER' | 'FORMATTED_STRING';

// ============================================================================
// Schema Mapping Types
// ============================================================================

/** Column mapping between invoice field and sheet column */
export interface ColumnMapping {
  invoiceField: string; // e.g., "vendor_name", "total_amount"
  sheetColumn: string; // e.g., "A", "B", "Vendor Name"
  columnIndex: number; // 0-based index
  transform?: FieldTransform; // Optional transformation
}

/** Field transformation for data formatting */
export interface FieldTransform {
  type: 'date_format' | 'currency_format' | 'uppercase' | 'lowercase' | 'custom';
  format?: string; // e.g., "MM/dd/yyyy" for dates
}

/** Sheet schema configuration */
export interface SheetSchema {
  id: string;
  tenantId: string;
  name: string;
  spreadsheetId: string;
  sheetName: string;
  range: string; // A1 notation of header row
  columnMappings: ColumnMapping[];
  autoFormat: boolean;
  syncFrequency: 'manual' | 'hourly' | 'daily' | 'realtime';
  lastSyncAt?: string;
  createdAt: string;
  updatedAt: string;
}

/** Invoice field type for mapping */
export type InvoiceFieldType =
  | 'id'
  | 'vendor_name'
  | 'vendor_id'
  | 'invoice_number'
  | 'total_amount'
  | 'currency'
  | 'status'
  | 'due_date'
  | 'invoice_date'
  | 'confidence_score'
  | 'risk_score'
  | 'risk_level'
  | 'line_items'
  | 'payment_terms'
  | 'po_number'
  | 'notes';

/** Field metadata for auto-format detection */
export interface FieldMetadata {
  fieldType: InvoiceFieldType;
  required: boolean;
  sampleValues: string[];
  detectedFormat?: string;
}

/** Auto-detected schema from sheet headers */
export interface DetectedSchema {
  headers: string[];
  columnCount: number;
  rowCount: number;
  suggestedMappings: ColumnMapping[];
  confidence: number;
}

// ============================================================================
// Sync Types
// ============================================================================

/** Sync status for a schema */
export type SyncStatus = 'idle' | 'syncing' | 'success' | 'failed';

/** Sync history entry */
export interface SyncHistory {
  id: string;
  schemaId: string;
  status: SyncStatus;
  rowsSynced: number;
  errorMessage?: string;
  startedAt: string;
  completedAt?: string;
}

/** Sync request */
export interface SyncRequest {
  schemaId: string;
  invoiceIds?: string[]; // Specific invoices to sync, or all if undefined
  dryRun?: boolean;
}

// ============================================================================
// API Response Types
// ============================================================================

/** Generic API response */
export interface GoogleApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: number;
    message: string;
    details?: unknown;
  };
}

/** OAuth flow response */
export interface OAuthFlowResponse {
  authUrl: string;
  state: string;
  expiresAt: number;
}

/** Token response */
export interface TokenResponse {
  success: boolean;
  accessToken?: string;
  expiresAt?: number;
  error?: string;
}

/** Schema CRUD response */
export interface SchemaResponse {
  success: boolean;
  schema?: SheetSchema;
  error?: string;
}

/** Sync result */
export interface SyncResult {
  success: boolean;
  rowsSynced: number;
  spreadsheetId: string;
  updatedRange: string;
  error?: string;
}
