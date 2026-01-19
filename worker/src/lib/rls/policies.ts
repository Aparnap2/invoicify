/**
 * Row-Level Security (RLS) Policy Engine
 *
 * Implements access control policies for Invoicify invoice processing.
 * Uses a deny-by-default approach with explicit allow policies.
 */

import type {
  RLSContext,
  RLSResource,
  RLSPolicyResult,
  PermissionResult,
  UserRole,
  InvoiceStatus,
} from './types.js';
import {
  ROLE_HIERARCHY,
  ROLE_PERMISSIONS,
} from './types.js';

// ============================================================================
// Permission Checks
// ============================================================================

/**
 * Check if user has a specific permission
 */
export function hasPermission(
  context: RLSContext,
  permission: string
): PermissionResult {
  const rolePermissions = ROLE_PERMISSIONS[context.role] || [];

  // Check for wildcard permissions (admin level)
  if (rolePermissions.some((p) => p.endsWith(':*'))) {
    const resourceType = permission.split(':')[0];
    if (rolePermissions.some((p) => p === `${resourceType}:*`)) {
      return { allowed: true };
    }
  }

  // Check for specific permission
  if (rolePermissions.includes(permission)) {
    return { allowed: true };
  }

  // Check for write permission implies read
  if (
    permission.endsWith(':read') &&
    rolePermissions.includes(permission.replace(':read', ':write'))
  ) {
    return { allowed: true };
  }

  return {
    allowed: false,
    reason: `Role '${context.role}' does not have '${permission}' permission`,
  };
}

/**
 * Check if user has minimum required role
 */
export function hasRole(
  context: RLSContext,
  requiredRole: UserRole
): PermissionResult {
  const userLevel = ROLE_HIERARCHY[context.role] || 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;

  if (userLevel >= requiredLevel) {
    return { allowed: true };
  }

  return {
    allowed: false,
    reason: `Requires '${requiredRole}' role or higher`,
  };
}

// ============================================================================
// Invoice Access Policies
// ============================================================================

/**
 * Check if user can view a specific invoice
 */
export function canViewInvoice(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Admins and Finance can view all invoices
  if (context.role === 'ADMIN' || context.role === 'FINANCE') {
    return { allowed: true };
  }

  // Approvers can view pending invoices
  if (context.role === 'APPROVER' && resource.status === 'PENDING') {
    return { allowed: true };
  }

  // Users can view approved, rejected, paid invoices
  if (
    context.role === 'USER' &&
    ['APPROVED', 'REJECTED', 'PAID'].includes(resource.status || '')
  ) {
    return { allowed: true };
  }

  // Tenant isolation - users can only view their tenant's invoices
  if (resource.tenantId && resource.tenantId !== context.tenantId) {
    return {
      allowed: false,
      reason: 'Access denied: Invoice belongs to different organization',
    };
  }

  return {
    allowed: false,
    reason: `Cannot view invoice with status '${resource.status}'`,
  };
}

/**
 * Check if user can create invoices
 */
export function canCreateInvoice(context: RLSContext): PermissionResult {
  return hasPermission(context, 'invoices:create');
}

/**
 * Check if user can update a specific invoice
 */
export function canUpdateInvoice(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Only admins and finance can update invoices
  if (context.role === 'ADMIN' || context.role === 'FINANCE') {
    return { allowed: true };
  }

  // Cannot update invoices that are already approved or paid
  if (['APPROVED', 'PAID', 'SYNCED'].includes(resource.status || '')) {
    return {
      allowed: false,
      reason: `Cannot update invoice with status '${resource.status}'`,
    };
  }

  // Tenant isolation
  if (resource.tenantId && resource.tenantId !== context.tenantId) {
    return {
      allowed: false,
      reason: 'Access denied: Invoice belongs to different organization',
    };
  }

  return hasPermission(context, 'invoices:write');
}

/**
 * Check if user can approve an invoice
 */
export function canApproveInvoice(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Only approvers, finance, and admin can approve
  if (!['APPROVER', 'FINANCE', 'ADMIN'].includes(context.role)) {
    return {
      allowed: false,
      reason: 'Only approvers can approve invoices',
    };
  }

  // Can only approve pending invoices
  if (resource.status !== 'PENDING') {
    return {
      allowed: false,
      reason: `Cannot approve invoice with status '${resource.status}'`,
    };
  }

  // Check approval limit for non-admin/finance
  if (
    context.role === 'APPROVER' &&
    context.approvalLimit &&
    resource.amount &&
    resource.amount > context.approvalLimit
  ) {
    return {
      allowed: false,
      reason: `Invoice amount $${resource.amount} exceeds approval limit $${context.approvalLimit}`,
    };
  }

  // Tenant isolation
  if (resource.tenantId && resource.tenantId !== context.tenantId) {
    return {
      allowed: false,
      reason: 'Access denied: Invoice belongs to different organization',
    };
  }

  return { allowed: true };
}

/**
 * Check if user can delete an invoice
 */
export function canDeleteInvoice(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Only admins can delete
  if (context.role !== 'ADMIN') {
    return {
      allowed: false,
      reason: 'Only admins can delete invoices',
    };
  }

  // Cannot delete approved or paid invoices
  if (['APPROVED', 'PAID'].includes(resource.status || '')) {
    return {
      allowed: false,
      reason: `Cannot delete invoice with status '${resource.status}'`,
    };
  }

  return { allowed: true };
}

// ============================================================================
// Vendor Access Policies
// ============================================================================

/**
 * Check if user can view a vendor
 */
export function canViewVendor(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Admins and finance can view all vendors
  if (context.role === 'ADMIN' || context.role === 'FINANCE') {
    return { allowed: true };
  }

  // Regular users can only view verified vendors
  if (resource.isVerified) {
    return { allowed: true };
  }

  return {
    allowed: false,
    reason: 'Can only view verified vendors',
  };
}

/**
 * Check if user can manage vendors
 */
export function canManageVendor(context: RLSContext): PermissionResult {
  return hasPermission(context, 'vendors:write');
}

// ============================================================================
// Audit Log Access Policies
// ============================================================================

/**
 * Check if user can view audit logs
 */
export function canViewAuditLogs(context: RLSContext): PermissionResult {
  return hasPermission(context, 'audit_logs:read');
}

// ============================================================================
// Data Masking
// ============================================================================

/**
 * Mask sensitive PII data based on user role
 */
export function maskSensitiveData(
  fieldName: string,
  fieldValue: string,
  userRole: UserRole
): string {
  // Admins see full data
  if (userRole === 'ADMIN') {
    return fieldValue;
  }

  switch (fieldName) {
    case 'ssn':
      // Mask SSN: XXX-XX-1234
      if (fieldValue.length >= 4) {
        return `XXX-XX-${fieldValue.slice(-4)}`;
      }
      return 'XXX-XX-XXXX';

    case 'bank_account':
      // Mask bank account: XXXX1234
      if (fieldValue.length >= 4) {
        return `XXXX${fieldValue.slice(-4)}`;
      }
      return 'XXXX';

    case 'routing_number':
      return 'XXXXXXXX';

    case 'email':
      // Mask email: j***@example.com
      const atIndex = fieldValue.indexOf('@');
      if (atIndex > 1) {
        return `${fieldValue[0]}***${fieldValue.slice(atIndex)}`;
      }
      return '***@***';

    case 'phone':
      // Mask phone: (XXX) XXX-1234
      const digits = fieldValue.replace(/\D/g, '');
      if (digits.length >= 4) {
        return `(XXX) XXX-${digits.slice(-4)}`;
      }
      return '(XXX) XXX-XXXX';

    default:
      return fieldValue;
  }
}

/**
 * Apply data masking to an object based on user role
 */
export function maskData(
  data: Record<string, unknown>,
  sensitiveFields: string[],
  userRole: UserRole
): Record<string, unknown> {
  const masked = { ...data };

  for (const field of sensitiveFields) {
    if (masked[field] && typeof masked[field] === 'string') {
      masked[field] = maskSensitiveData(field, masked[field] as string, userRole);
    }
  }

  return masked;
}

// ============================================================================
// Query Filtering
// ============================================================================

/**
 * Build WHERE clause conditions based on RLS context
 * Returns a function that filters invoice results
 */
export function buildInvoiceFilter(context: RLSContext) {
  return (invoice: Record<string, unknown>): boolean => {
    // Tenant isolation
    if (invoice.tenantId && invoice.tenantId !== context.tenantId) {
      return false;
    }

    // Role-based filtering
    switch (context.role) {
      case 'ADMIN':
      case 'FINANCE':
        return true; // Can see all

      case 'APPROVER':
        return invoice.status === 'PENDING';

      case 'USER':
        return ['APPROVED', 'REJECTED', 'PAID'].includes(
          invoice.status as InvoiceStatus
        );

      case 'VIEWER':
        return ['APPROVED', 'PAID'].includes(invoice.status as InvoiceStatus);

      default:
        return false;
    }
  };
}

/**
 * Filter a list of records based on RLS context
 */
export function filterByRLS<T extends Record<string, unknown>>(
  records: T[],
  context: RLSContext,
  resourceType: RLSResource['type']
): T[] {
  const filter = buildInvoiceFilter(context);
  return records.filter((record) => {
    const resource: RLSResource = {
      type: resourceType,
      id: record.id,
      tenantId: record.tenantId,
      status: record.status,
      amount: record.amount,
      isVerified: record.isVerified,
    };

    const result = canViewInvoice(context, resource);
    return result.allowed;
  });
}

// ============================================================================
// Export
// ============================================================================

export * from './types.js';
