/**
 * Row-Level Security (RLS) Types
 *
 * Defines user roles, permissions, and access control types for the Invoicify API.
 */

// User roles with ascending privilege order
export type UserRole = 'VIEWER' | 'USER' | 'APPROVER' | 'FINANCE' | 'ADMIN';

// Role hierarchy for permission inheritance
export const ROLE_HIERARCHY: Record<UserRole, number> = {
  VIEWER: 1,
  USER: 2,
  APPROVER: 3,
  FINANCE: 4,
  ADMIN: 5,
};

// Role permissions mapping
export const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
  VIEWER: ['invoices:read', 'vendors:read'],
  USER: ['invoices:read', 'invoices:create', 'vendors:read'],
  APPROVER: ['invoices:read', 'invoices:approve', 'approvals:read', 'approvals:update'],
  FINANCE: [
    'invoices:read',
    'invoices:write',
    'invoices:approve',
    'invoices:delete',
    'vendors:read',
    'vendors:write',
    'approvals:read',
    'approvals:update',
    'reports:read',
    'reports:export',
  ],
  ADMIN: [
    'invoices:*',
    'vendors:*',
    'approvals:*',
    'audit_logs:read',
    'users:*',
    'settings:*',
    'reports:*',
  ],
};

// Invoice statuses
export type InvoiceStatus =
  | 'NEW'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'PAID'
  | 'SYNCED'
  | 'ARCHIVED';

// Risk levels
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// User context for RLS checks
export interface RLSContext {
  userId: string;
  role: UserRole;
  tenantId: string;
  email?: string;
  approvalLimit?: number;
}

// Resource definition for RLS evaluation
export interface RLSResource {
  type: 'invoice' | 'vendor' | 'approval' | 'audit_log' | 'report' | 'setting';
  id?: string;
  ownerId?: string;
  tenantId?: string;
  status?: InvoiceStatus;
  amount?: number;
  isVerified?: boolean;
}

// RLS policy evaluation result
export interface RLSPolicyResult {
  allowed: boolean;
  reason?: string;
  maskedFields?: Record<string, string>;
}

// Permission check result
export interface PermissionResult {
  allowed: boolean;
  reason?: string;
}
