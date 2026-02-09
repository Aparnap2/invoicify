/**
 * Row-Level Security (RLS) Types
 *
 * Defines user roles, permissions, and access control types for the Invoicify API.
 */

// Organization roles with ascending privilege order
export type OrgRole =
  | 'VIEWER'
  | 'USER'
  | 'APPROVER'
  | 'FINANCE'
  | 'ADMIN'
  | 'OWNER';

// User roles (alias for backward compatibility)
export type UserRole = OrgRole;

// Role hierarchy for permission inheritance
export const ROLE_HIERARCHY = {
  VIEWER: 1,
  USER: 2,
  APPROVER: 3,
  FINANCE: 4,
  ADMIN: 5,
  OWNER: 6,
} as const;

// Type inference for ROLE_HIERARCHY values
export type RoleHierarchyValue = (typeof ROLE_HIERARCHY)[keyof typeof ROLE_HIERARCHY];

// Role permissions mapping
export const ROLE_PERMISSIONS: Record<OrgRole, string[]> = {
  VIEWER: ['invoices:read', 'vendors:read'],
  USER: ['invoices:read', 'invoices:create', 'vendors:read'],
  APPROVER: [
    'invoices:read',
    'invoices:approve',
    'approvals:read',
    'approvals:update',
  ],
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
    'api_keys:*',
    'billing:read',
  ],
  OWNER: [
    'invoices:*',
    'vendors:*',
    'approvals:*',
    'audit_logs:*',
    'users:*',
    'settings:*',
    'reports:*',
    'api_keys:*',
    'billing:*',
    'organization:*',
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
  // User identification
  userId: string;

  // Organization context for tenant isolation
  organizationId: string;

  // User role within the organization
  role: OrgRole;

  // Permission scopes for fine-grained access control
  scopes: string[];

  // Optional email for audit purposes
  email?: string;

  // Approval limit for APPROVER role (amount in cents)
  approvalLimit?: number;

  // Optional tenant ID for backward compatibility
  tenantId?: string;
}

// Resource definition for RLS evaluation
export interface RLSResource {
  type:
    | 'invoice'
    | 'vendor'
    | 'approval'
    | 'audit_log'
    | 'report'
    | 'setting'
    | 'user'
    | 'api_key'
    | 'billing';
  id?: string;
  ownerId?: string;
  organizationId?: string;
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

// Helper type for role-based access control
export interface RBACConfig {
  minRole: OrgRole;
  requiredPermissions?: string[];
  denyPermissions?: string[];
}

// Organization membership types
export interface OrgMembership {
  userId: string;
  organizationId: string;
  role: OrgRole;
  joinedAt: Date;
  invitedBy: string;
}

// API Key types
export interface ApiKey {
  id: string;
  organizationId: string;
  name: string;
  hashedKey: string;
  createdAt: Date;
  lastUsedAt?: Date;
  expiresAt?: Date;
  scopes: string[];
  isActive: boolean;
}
