export interface ExtractedInvoice {
  vendorName: string;
  invoiceNumber: string;
  amount: number;
  currency: string;
  invoiceDate: string;
  dueDate?: string;
  lineItems: Array<{
    description: string;
    quantity: number;
    unitPrice: number;
    total: number;
  }>;
  confidence: number;
}

export interface Invoice {
  id: string;
  vendorId?: string;
  vendorName: string;
  invoiceNumber?: string;
  amount: number;
  currency: string;
  invoiceDate?: string;
  dueDate?: string;
  status: 'PENDING' | 'EXTRACTED' | 'HITL_REQUIRED' | 'APPROVED' | 'REJECTED' | 'FAILED';
  riskScore?: number;
  confidence?: number;
  r2KeyRaw?: string;
  r2KeyProcessed?: string;
  decisionReason?: string;
  createdAt: string;
  updatedAt: string;
}

export interface Vendor {
  id: string;
  name: string;
  trustLevel: number;
  consecutiveAccurate: number;
  consecutiveErrors: number;
  totalInvoices: number;
  totalAmount: number;
  createdAt: string;
}

export interface AuditLog {
  id: string;
  invoiceId: string;
  action: string;
  actor: string;
  metadata?: object;
  createdAt: string;
}

export interface Env {
  DB: D1Database;
  R2_BUCKET: R2Bucket;
  INVOICE_QUEUE: Queue;
  INVOICE_PROCESSOR: DurableObjectNamespace;
  CACHE: KVNamespace;
  GROQ_API_KEY: string;
  QUICKBOOKS_CLIENT_ID: string;
  QUICKBOOKS_CLIENT_SECRET: string;
  ENVIRONMENT: string;
}
