import type { Env } from "../db";
import { getDb, schema } from "../db";
import { eq, and, sql } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";

/**
 * QuickBooks OAuth tokens
 */
export interface QuickBooksTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  realmId: string;
}

/**
 * QuickBooks vendor record
 */
export interface QuickBooksVendor {
  id: string;
  displayName: string;
  companyName?: string;
  email?: string;
  phone?: string;
  balance?: number;
}

/**
 * QuickBooks bill record
 */
export interface QuickBooksBill {
  id: string;
  vendorRef: { value: string; name?: string };
  txnDate: string;
  dueDate: string;
  totalAmt: number;
  docNumber?: string;
  balance?: number;
}

/**
 * QuickBooks configuration
 */
const QB_CONFIG = {
  clientId: "${QUICKBOOKS_CLIENT_ID}",
  clientSecret: "${QUICKBOOKS_CLIENT_SECRET}",
  redirectUri: "${QUICKBOOKS_REDIRECT_URI}",
  environment: "sandbox" as const, // or "production"
  baseUrlSandbox: "https://sandbox-quickbooks.api.intuit.com",
  baseUrlProduction: "https://quickbooks.api.intuit.com",
};

/**
 * Get authorization URL for QuickBooks OAuth
 */
export function getAuthorizationUrl(state: string): string {
  const params = new URLSearchParams({
    client_id: QB_CONFIG.clientId,
    redirect_uri: QB_CONFIG.redirectUri,
    response_type: "code",
    scope: "com.intuit.quickbooks.accounting",
    state,
  });

  return `https://appcenter.intuit.com/connect/oauth2?${params.toString()}`;
}

/**
 * Exchange authorization code for tokens
 */
export async function exchangeCodeForTokens(
  code: string
): Promise<QuickBooksTokens | null> {
  const tokenUrl = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer";

  const credentials = Buffer.from(
    `${QB_CONFIG.clientId}:${QB_CONFIG.clientSecret}`
  ).toString("base64");

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: QB_CONFIG.redirectUri,
    }),
  });

  if (!response.ok) {
    console.error("Token exchange failed:", await response.text());
    return null;
  }

  const data = await response.json() as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    realmId: string;
  };
  const now = Date.now();

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: now + data.expires_in * 1000,
    realmId: data.realmId || "",
  };
}

/**
 * Refresh access token
 */
export async function refreshAccessToken(
  refreshToken: string
): Promise<QuickBooksTokens | null> {
  const tokenUrl = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer";

  const credentials = Buffer.from(
    `${QB_CONFIG.clientId}:${QB_CONFIG.clientSecret}`
  ).toString("base64");

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    }),
  });

  if (!response.ok) {
    console.error("Token refresh failed:", await response.text());
    return null;
  }

  const data = await response.json() as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    realmId: string;
  };
  const now = Date.now();

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: now + data.expires_in * 1000,
    realmId: data.realmId || "",
  };
}

/**
 * Get base URL for API calls
 */
function getBaseUrl(): string {
  return QB_CONFIG.environment === "sandbox"
    ? QB_CONFIG.baseUrlSandbox
    : QB_CONFIG.baseUrlProduction;
}

/**
 * QuickBooks API client
 */
export class QuickBooksClient {
  private accessToken: string;
  private realmId: string;
  private baseUrl: string;

  constructor(tokens: QuickBooksTokens) {
    this.accessToken = tokens.accessToken;
    this.realmId = tokens.realmId;
    this.baseUrl = getBaseUrl();
  }

  /**
   * Make authenticated API request
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T | null> {
    const url = `${this.baseUrl}/v3/company/${this.realmId}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        Authorization: `Bearer ${this.accessToken}`,
        "Content-Type": "application/json",
        Accept: "application/json",
        ...options.headers,
      },
    });

    if (response.status === 401) {
      // Token expired - caller should refresh
      return null;
    }

    if (!response.ok) {
      console.error("QB API error:", await response.text());
      return null;
    }

    return response.json();
  }

  /**
   * Get company info
   */
  async getCompanyInfo(): Promise<any | null> {
    return this.request("/companyinfo/" + this.realmId);
  }

  /**
   * Query vendors
   */
  async queryVendors(name?: string): Promise<QuickBooksVendor[]> {
    let query = "SELECT * FROM Vendor";
    if (name) {
      query += ` WHERE DisplayName = '${name.replace(/'/g, "\\'")}'`;
    }
    query += " MAXRESULTS 100";

    const result = await this.request<{ QueryResponse: { Vendor: any[] } }>(
      `/query?query=${encodeURIComponent(query)}`
    );

    if (!result) return [];

    return (result.QueryResponse.Vendor || []).map((v) => ({
      id: v.Id,
      displayName: v.DisplayName,
      companyName: v.CompanyName,
      email: v.PrimaryEmailAddr?.Address,
      phone: v.PrimaryPhone?.FreeFormNumber,
      balance: v.Balance,
    }));
  }

  /**
   * Create vendor
   */
  async createVendor(
    name: string,
    email?: string,
    phone?: string
  ): Promise<QuickBooksVendor | null> {
    const vendor = {
      DisplayName: name,
      CompanyName: name,
      PrimaryEmailAddr: email ? { Address: email } : undefined,
      PrimaryPhone: phone ? { FreeFormNumber: phone } : undefined,
    };

    const result = await this.request<{ Vendor: any }>("/vendor", {
      method: "POST",
      body: JSON.stringify(vendor),
    });

    if (!result) return null;

    return {
      id: result.Vendor.Id,
      displayName: result.Vendor.DisplayName,
      companyName: result.Vendor.CompanyName,
      email: result.Vendor.PrimaryEmailAddr?.Address,
      phone: result.Vendor.PrimaryPhone?.FreeFormNumber,
    };
  }

  /**
   * Get or create vendor
   */
  async getOrCreateVendor(
    name: string,
    email?: string,
    phone?: string
  ): Promise<QuickBooksVendor> {
    const existing = await this.queryVendors(name);
    if (existing.length > 0) {
      return existing[0];
    }
    const created = await this.createVendor(name, email, phone);
    if (created) return created;

    throw new Error("Failed to get or create vendor");
  }

  /**
   * Create bill from invoice
   */
  async createBill(invoice: {
    vendorId: string;
    invoiceNumber: string;
    invoiceDate: string;
    dueDate: string;
    totalAmount: number;
    lineItems: Array<{
      description: string;
      amount: number;
      glCode?: string;
    }>;
  }): Promise<QuickBooksBill | null> {
    const bill = {
      VendorRef: { value: invoice.vendorId },
      TxnDate: invoice.invoiceDate,
      DueDate: invoice.dueDate,
      DocNumber: invoice.invoiceNumber,
      Line: invoice.lineItems.map((item, index) => ({
        LineNum: index + 1,
        Description: item.description,
        Amount: item.amount,
        DetailType: "AccountBasedExpenseLineDetail",
        AccountBasedExpenseLineDetail: {
          AccountRef: item.glCode
            ? { value: item.glCode }
            : { value: "1" }, // Default expense account
        },
      })),
    };

    const result = await this.request<{ Bill: any }>("/bill", {
      method: "POST",
      body: JSON.stringify(bill),
    });

    if (!result) return null;

    return {
      id: result.Bill.Id,
      vendorRef: {
        value: result.Bill.VendorRef?.value,
        name: result.Bill.VendorRef?.name,
      },
      txnDate: result.Bill.TxnDate,
      dueDate: result.Bill.DueDate,
      totalAmt: result.Bill.TotalAmt,
      docNumber: result.Bill.DocNumber,
    };
  }

  /**
   * Query bills
   */
  async queryBills(vendorId?: string): Promise<QuickBooksBill[]> {
    let query = "SELECT * FROM Bill";
    if (vendorId) {
      query += ` WHERE VendorRef = '${vendorId}'`;
    }
    query += " ORDERBY TxnDate DESC MAXRESULTS 100";

    const result = await this.request<{ QueryResponse: { Bill: any[] } }>(
      `/query?query=${encodeURIComponent(query)}`
    );

    if (!result) return [];

    return (result.QueryResponse.Bill || []).map((b) => ({
      id: b.Id,
      vendorRef: {
        value: b.VendorRef?.value,
        name: b.VendorRef?.name,
      },
      txnDate: b.TxnDate,
      dueDate: b.DueDate,
      totalAmt: b.TotalAmt,
      docNumber: b.DocNumber,
      balance: b.Balance,
    }));
  }
}

/**
 * Sync invoice to QuickBooks
 */
export async function syncInvoiceToQuickBooks(
  env: Env,
  invoiceId: string
): Promise<{ success: boolean; quickbooksId?: string; error?: string }> {
  const db = getDb(env);

  const [invoice] = await db
    .select()
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice) {
    return { success: false, error: "Invoice not found" };
  }

  // Get line items
  const lineItems = await db
    .select()
    .from(schema.lineItems)
    .where(eq(schema.lineItems.invoiceId, invoiceId));

  // For demo, return mock response - in production, use real OAuth tokens
  // In production, you would:
  // 1. Get stored tokens from database
  // 2. Refresh if needed
  // 3. Create client and sync

  // Check if already synced
  if (invoice.quickbooksId) {
    return {
      success: true,
      quickbooksId: invoice.quickbooksId,
    };
  }

  // Mock implementation - simulate QB bill creation
  const mockQuickbooksId = `QB-${uuidv4().slice(0, 8)}`;

  // Update invoice with QB ID
  await db
    .update(schema.invoices)
    .set({
      quickbooksId: mockQuickbooksId,
      quickbooksSyncedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
    .where(eq(schema.invoices.id, invoiceId));

  // Create audit log
  await db.insert(schema.auditLogs).values({
    id: uuidv4(),
    action: "QUICKBOOKS_SYNC",
    entityType: "invoice",
    entityId: invoiceId,
    performedBy: "system",
    changes: JSON.stringify({
      quickbooksId: mockQuickbooksId,
      vendorName: invoice.vendorName,
      amount: invoice.totalAmount,
    }),
    performedAt: new Date().toISOString(),
  });

  return {
    success: true,
    quickbooksId: mockQuickbooksId,
  };
}

/**
 * Get sync status for invoice
 */
export async function getQuickBooksSyncStatus(
  env: Env,
  invoiceId: string
): Promise<{ synced: boolean; quickbooksId?: string; syncedAt?: string }> {
  const db = getDb(env);

  const [invoice] = await db
    .select({
      quickbooksId: schema.invoices.quickbooksId,
      quickbooksSyncedAt: schema.invoices.quickbooksSyncedAt,
    })
    .from(schema.invoices)
    .where(eq(schema.invoices.id, invoiceId))
    .limit(1);

  if (!invoice || !invoice.quickbooksId) {
    return { synced: false };
  }

  return {
    synced: true,
    quickbooksId: invoice.quickbooksId,
    syncedAt: invoice.quickbooksSyncedAt || undefined,
  };
}

/**
 * Queue invoice for QuickBooks sync
 */
export async function queueForSync(
  env: Env,
  invoiceId: string
): Promise<{ success: boolean }> {
  const db = getDb(env);

  // Check if already queued
  const [existing] = await db
    .select()
    .from(schema.syncQueue)
    .where(
      and(
        eq(schema.syncQueue.entityType, "invoice"),
        eq(schema.syncQueue.entityId, invoiceId),
        eq(schema.syncQueue.status, "PENDING")
      )
    )
    .limit(1);

  if (existing) {
    return { success: true };
  }

  await db.insert(schema.syncQueue).values({
    id: uuidv4(),
    entityType: "invoice",
    entityId: invoiceId,
    action: "CREATE",
    status: "PENDING",
    scheduledAt: new Date().toISOString(),
  });

  return { success: true };
}
