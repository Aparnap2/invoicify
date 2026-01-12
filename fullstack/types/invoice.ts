/**
 * Invoice types matching D1 schema
 */
export type InvoiceStatus =
  | "NEW"
  | "EXTRACTED"
  | "VALIDATED"
  | "APPROVED"
  | "REJECTED"
  | "APPROVAL_PENDING"  // HITL pending approval
  | "PENDING"
  | "PAID"
  | "FAILED";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED";

/**
 * Invoice from API
 */
export interface Invoice {
  id: string;
  vendorName: string;
  vendorId?: string;
  invoiceNumber: string;
  totalAmount: number;
  currency: string;
  status: InvoiceStatus;
  dueDate?: string;
  invoiceDate?: string;
  confidenceScore?: number;
  riskScore?: number;
  riskLevel?: RiskLevel;
  fileUrl?: string;
  fileName?: string;
  mimeType?: string;
  quickbooksId?: string;
  createdAt: string;
  updatedAt?: string;
  lineItems?: LineItem[];
  approvals?: Approval[];
  riskIndicators?: RiskIndicator[];
}

/**
 * Line item
 */
export interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  glCode?: string;
}

/**
 * Approval record
 */
export interface Approval {
  id: string;
  invoiceId: string;
  approverEmail: string;
  approverName?: string;
  status: ApprovalStatus;
  comments?: string;
  createdAt: string;
}

/**
 * Risk indicator
 */
export interface RiskIndicator {
  id: string;
  invoiceId: string;
  indicatorType: string;
  severity: RiskLevel;
  description: string;
  scoreContribution: number;
  resolved: boolean;
}

/**
 * Invoice list response
 */
export interface InvoiceListResponse {
  data: Invoice[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

/**
 * Invoice statistics
 */
export interface InvoiceStats {
  byStatus: StatusCount[];
  totals: {
    total: number;
    avg: number;
  };
  recentActivity: {
    today: number;
    week: number;
    month: number;
  };
}

/**
 * Status count for dashboard
 */
export interface StatusCount {
  status: string;
  count: number;
}

/**
 * Risk statistics
 */
export interface RiskStats {
  byRiskLevel: RiskLevelCount[];
  averageRiskScore: number;
  criticalCount: number;
}

/**
 * Risk level count
 */
export interface RiskLevelCount {
  level: RiskLevel;
  count: number;
  totalAmount: number;
}

/**
 * Chart data point
 */
export interface ChartDataPoint {
  date: string;
  count: number;
  amount: number;
}

/**
 * KPI card data
 */
export interface KpiData {
  title: string;
  value: number | string;
  change?: number;
  changeLabel?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
}

/**
 * Audit event from audit trail
 */
export interface AuditEvent {
  action: string;
  performedAt: string;
  performedBy: string;
  details: Record<string, any>;
}

/**
 * Audit trail response
 */
export interface AuditTrailResponse {
  events: AuditEvent[];
}

/**
 * HITL invoice with risk indicators
 */
export interface HitlInvoice extends Omit<Invoice, "riskIndicators"> {
  riskIndicators: RiskIndicator[];
}
