/**
 * Schema Mapping and Sync Service
 *
 * Handles mapping between invoice fields and Google Sheets columns,
 * data transformation, and batch sync operations.
 *
 * Run tests with: pnpm test -- test/lib/google/schema-mapper.test.ts
 */

import type {
  ColumnMapping,
  SheetSchema,
  InvoiceFieldType,
  DetectedSchema,
  FieldMetadata,
  FieldTransform,
} from './types.js';
import { columnIndexToA1, columnA1ToIndex } from './sheets.js';

// ============================================================================
// Field Name Patterns for Auto-Detection
// ============================================================================

const FIELD_PATTERNS: Record<InvoiceFieldType, string[]> = {
  id: ['id', 'invoice id', 'invoice_id', 'doc id'],
  vendor_name: ['vendor', 'supplier', 'merchant', 'payee', 'company'],
  vendor_id: ['vendor id', 'supplier id', 'vendor_id'],
  total_amount: [
    'amount',
    'total',
    'total amount',
    'invoice amount',
    'sum',
    'grand total',
    'balance due',
  ],
  invoice_date: [
    'date',
    'invoice date',
    'invoice_date',
    'bill date',
    'invoice issued',
    'doc date',
  ],
  due_date: ['due date', 'due_date', 'payment due', 'pay by'],
  invoice_number: [
    'invoice #',
    'invoice_number',
    'invoice number',
    'invoice no',
    'inv #',
    'inv number',
  ],
  currency: ['currency', 'currency code', 'ccy'],
  status: ['status', 'state', 'payment status'],
  confidence_score: ['confidence', 'confidence score', 'accuracy'],
  risk_score: ['risk', 'risk score', 'risk_score'],
  risk_level: ['risk level', 'risk_level', 'risk rating'],
  line_items: ['line items', 'line_items', 'items', 'description'],
  payment_terms: ['payment terms', 'payment_terms', 'terms', 'net terms'],
  po_number: ['po', 'po number', 'purchase order', 'po_number', 'order #'],
  notes: ['notes', 'comments', 'memo', 'description', 'remarks'],
};

// ============================================================================
// Column Mapping Logic
// ============================================================================

/**
 * Detect invoice field type from header name
 * Prefers longer, more specific pattern matches
 */
export function detectFieldType(headerName: string): InvoiceFieldType | null {
  const normalizedHeader = headerName.toLowerCase().trim();

  // Collect all matches with their pattern lengths
  const matches: Array<{ fieldType: InvoiceFieldType; pattern: string; length: number }> = [];

  for (const [fieldType, patterns] of Object.entries(FIELD_PATTERNS)) {
    for (const pattern of patterns) {
      if (normalizedHeader.includes(pattern)) {
        matches.push({
          fieldType: fieldType as InvoiceFieldType,
          pattern,
          length: pattern.length,
        });
      }
    }
  }

  // Sort by pattern length (longest first) to prefer more specific matches
  matches.sort((a, b) => b.length - a.length);

  // Return the match with the longest pattern
  return matches.length > 0 ? matches[0].fieldType : null;
}

/**
 * Create column mapping from header
 */
export function createMappingFromHeader(
  headerName: string,
  columnIndex: number
): ColumnMapping | null {
  const fieldType = detectFieldType(headerName);
  if (!fieldType) return null;

  const columnLetter = columnIndexToA1(columnIndex);

  return {
    invoiceField: fieldType,
    sheetColumn: columnLetter,
    columnIndex,
  };
}

/**
 * Detect schema from sheet headers
 */
export function detectSchema(headers: string[]): DetectedSchema {
  const suggestedMappings: ColumnMapping[] = [];

  for (let i = 0; i < headers.length; i++) {
    const mapping = createMappingFromHeader(headers[i], i);
    if (mapping) {
      suggestedMappings.push(mapping);
    }
  }

  // Calculate confidence based on coverage
  const matchedFields = suggestedMappings.length;
  const totalFields = headers.length;
  const confidence = totalFields > 0 ? matchedFields / totalFields : 0;

  return {
    headers,
    columnCount: headers.length,
    rowCount: 0, // Will be updated when fetching data
    suggestedMappings,
    confidence,
  };
}

// ============================================================================
// Data Transformation
// ============================================================================

/**
 * Transform invoice field value based on mapping
 */
export function transformValue(
  value: unknown,
  mapping: ColumnMapping
): unknown {
  if (value === null || value === undefined) {
    return '';
  }

  if (!mapping.transform) {
    return value;
  }

  const { type, format } = mapping.transform;

  switch (type) {
    case 'date_format':
      return formatDate(value, format || 'MM/dd/yyyy');

    case 'currency_format':
      return formatCurrency(value, format || 'USD');

    case 'uppercase':
      return String(value).toUpperCase();

    case 'lowercase':
      return String(value).toLowerCase();

    case 'custom':
      // Custom format handling (implementation specific)
      return value;

    default:
      return value;
  }
}

/**
 * Format date value
 */
function formatDate(value: unknown, format: string): string {
  if (value instanceof Date) {
    const d = value;
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const year = d.getFullYear();

    return format
      .replace('MM', month)
      .replace('dd', day)
      .replace('yyyy', String(year));
  }

  // If already a string, try to parse and reformat
  const date = new Date(value as string);
  if (!isNaN(date.getTime())) {
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const year = date.getFullYear();

    return format
      .replace('MM', month)
      .replace('dd', day)
      .replace('yyyy', String(year));
  }

  return String(value);
}

/**
 * Format currency value
 */
function formatCurrency(value: unknown, currency: string): string {
  const numValue = typeof value === 'number' ? value : parseFloat(String(value));

  if (isNaN(numValue)) {
    return String(value);
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(numValue);
}

// ============================================================================
// Invoice to Row Conversion
// ============================================================================

/**
 * Convert invoice object to row array based on schema mapping
 */
export function invoiceToRow(
  invoice: Record<string, unknown>,
  schema: SheetSchema
): unknown[] {
  const row: unknown[] = new Array(schema.columnMappings.length);

  for (const mapping of schema.columnMappings) {
    const value = invoice[mapping.invoiceField];
    row[mapping.columnIndex] = transformValue(value, mapping);
  }

  return row;
}

/**
 * Convert multiple invoices to rows
 */
export function invoicesToRows(
  invoices: Record<string, unknown>[],
  schema: SheetSchema
): unknown[][] {
  return invoices.map((invoice) => invoiceToRow(invoice, schema));
}

// ============================================================================
// Schema Validation
// ============================================================================

/**
 * Validate column mappings
 */
export function validateMappings(mappings: ColumnMapping[]): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];
  const usedIndices = new Set<number>();
  const usedFields = new Set<string>();

  for (let i = 0; i < mappings.length; i++) {
    const mapping = mappings[i];

    // Check for duplicate column indices
    if (usedIndices.has(mapping.columnIndex)) {
      errors.push(`Duplicate column index ${mapping.columnIndex}`);
    }
    usedIndices.add(mapping.columnIndex);

    // Check for duplicate invoice fields
    if (usedFields.has(mapping.invoiceField)) {
      errors.push(`Duplicate invoice field '${mapping.invoiceField}'`);
    }
    usedFields.add(mapping.invoiceField);

    // Validate field type
    if (!FIELD_PATTERNS[mapping.invoiceField as InvoiceFieldType]) {
      errors.push(`Invalid invoice field '${mapping.invoiceField}'`);
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Check if schema has all required fields
 */
export function hasRequiredFields(
  schema: SheetSchema,
  requiredFields: InvoiceFieldType[]
): boolean {
  const mappedFields = schema.columnMappings.map((m) => m.invoiceField);

  return requiredFields.every((field) => mappedFields.includes(field));
}

// ============================================================================
// Export
// ============================================================================

export {
  FIELD_PATTERNS,
  type ColumnMapping,
  type InvoiceFieldType,
  type DetectedSchema,
};
