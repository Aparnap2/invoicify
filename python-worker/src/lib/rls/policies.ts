/**
 * Row-Level Security (RLS) Policy Engine
 *
 * Implements access control policies for Invoicify invoice processing.
 * Uses a deny-by-default approach with explicit allow policies.
 * Supports multi-tenant isolation via organizationId.
 */

import type {
  RLSContext,
  RLSResource,
  RLSPolicyResult,
  PermissionResult,
  OrgRole,
  RoleHierarchyValue,
} from './types.js';
import { ROLE_HIERARCHY, ROLE_PERMISSIONS } from './types.js';

// ============================================================================
// Constants
// ============================================================================

/**
 * Role hierarchy constant for permission inheritance across roles
 */
export const ROLE_HIERARCHY_CONST = {
  VIEWER: 1,
  USER: 2,
  APPROVER: 3,
  FINANCE: 4,
  ADMIN: 5,
  OWNER: 6,
} as const;

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get the role level from the hierarchy
 */
function getRoleLevel(role: OrgRole): RoleHierarchyValue {
  return ROLE_HIERARCHY[role] ?? 0;
}

/**
 * Check if user role has at least the required level in the hierarchy
 */
function hasMinimumRole(
  context: RLSContext,
  requiredRole: OrgRole
): boolean {
  const userLevel = getRoleLevel(context.role);
  const requiredLevel = getRoleLevel(requiredRole);
  return userLevel >= requiredLevel;
}

/**
 * Check organization isolation - ensures resource belongs to user's org
 */
function checkOrganizationIsolation(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  const resourceOrgId = resource.organizationId ?? resource.tenantId;
  const userOrgId = context.organizationId ?? context.tenantId;

  if (resourceOrgId && resourceOrgId !== userOrgId) {
    return {
      allowed: false,
      reason: 'Access denied: Resource belongs to different organization',
    };
  }

  return { allowed: true };
}

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
  // Check scopes first for fine-grained access control (if scopes exist)
  if (context.scopes && (context.scopes.includes(permission) || context.scopes.includes('*'))) {
    return { allowed: true };
  }

  const rolePermissions = ROLE_PERMISSIONS[context.role] ?? [];

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
  requiredRole: OrgRole
): PermissionResult {
  if (hasMinimumRole(context, requiredRole)) {
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
  // Organization isolation check first
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Admins and Finance can view all invoices in their organization
  if (context.role === 'ADMIN' || context.role === 'FINANCE') {
    return { allowed: true };
  }

  // Owner can view all invoices in their organization
  if (context.role === 'OWNER') {
    return { allowed: true };
  }

  // Approvers can view pending invoices for approval
  if (context.role === 'APPROVER' && resource.status === 'PENDING') {
    return { allowed: true };
  }

  // Users can view approved, rejected, paid invoices
  if (
    context.role === 'USER' &&
    ['APPROVED', 'REJECTED', 'PAID'].includes(resource.status ?? '')
  ) {
    return { allowed: true };
  }

  // Viewers can only view approved and paid invoices
  if (
    context.role === 'VIEWER' &&
    ['APPROVED', 'PAID'].includes(resource.status ?? '')
  ) {
    return { allowed: true };
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
  // Organization isolation - must have organizationId
  if (!context.organizationId && !context.tenantId) {
    return {
      allowed: false,
      reason: 'User must belong to an organization to create invoices',
    };
  }

  // Only USER role and above can create invoices
  if (!hasMinimumRole(context, 'USER')) {
    return {
      allowed: false,
      reason: 'Insufficient role to create invoices',
    };
  }

  return hasPermission(context, 'invoices:create');
}

/**
 * Check if user can update a specific invoice
 */
export function canUpdateInvoice(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Organization isolation check
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Admins, Finance, and Owner can update invoices
  if (
    context.role === 'ADMIN' ||
    context.role === 'FINANCE' ||
    context.role === 'OWNER'
  ) {
    return { allowed: true };
  }

  // Cannot update invoices that are already approved or paid or synced
  if (['APPROVED', 'PAID', 'SYNCED'].includes(resource.status ?? '')) {
    return {
      allowed: false,
      reason: `Cannot update invoice with status '${resource.status}'`,
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
  // Organization isolation check
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Only approvers, finance, admin, and owner can approve
  if (!['APPROVER', 'FINANCE', 'ADMIN', 'OWNER'].includes(context.role)) {
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

  // Check approval limit for APPROVER role (not for FINANCE, ADMIN, OWNER)
  if (
    context.role === 'APPROVER' &&
    context.approvalLimit !== undefined &&
    resource.amount !== undefined &&
    resource.amount > context.approvalLimit
  ) {
    return {
      allowed: false,
      reason: `Invoice amount $${resource.amount} exceeds approval limit $${context.approvalLimit}`,
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
  // Organization isolation check
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Only admins and owners can delete invoices
  if (!['ADMIN', 'OWNER'].includes(context.role)) {
    return {
      allowed: false,
      reason: 'Only admins can delete invoices',
    };
  }

  // Cannot delete approved or paid invoices
  if (['APPROVED', 'PAID'].includes(resource.status ?? '')) {
    return {
      allowed: false,
      reason: `Cannot delete invoice with status '${resource.status}'`,
    };
  }

  return { allowed: true };
}

// ============================================================================
// Multi-Tenant / Organization Policies
// ============================================================================

/**
 * Check if user can invite new users to the organization
 * Only ADMIN and OWNER roles can invite users
 */
export function canInviteUser(context: RLSContext): PermissionResult {
  if (!hasMinimumRole(context, 'ADMIN')) {
    return {
      allowed: false,
      reason: 'Only administrators can invite new users',
    };
  }

  return hasPermission(context, 'users:invite');
}

/**
 * Check if user can manage billing for the organization
 * Only OWNER and ADMIN roles can manage billing
 */
export function canManageBilling(context: RLSContext): PermissionResult {
  // Only OWNER and ADMIN can manage billing
  if (!['OWNER', 'ADMIN'].includes(context.role)) {
    return {
      allowed: false,
      reason: 'Only owners and administrators can manage billing',
    };
  }

  return hasPermission(context, 'billing:manage');
}

/**
 * Check if user can view other users in the organization
 * Based on role hierarchy - higher roles can view lower roles
 */
export function canViewOtherUsers(
  context: RLSContext,
  targetUserRole?: OrgRole
): PermissionResult {
  // Organization isolation is handled at the service level
  // This policy checks role-based access within the organization

  // Admins and owners can view all users
  if (['ADMIN', 'OWNER'].includes(context.role)) {
    return { allowed: true };
  }

  // Finance can view users with roles below FINANCE
  if (context.role === 'FINANCE') {
    if (!targetUserRole || getRoleLevel(targetUserRole) <= getRoleLevel('FINANCE')) {
      return { allowed: true };
    }
    return {
      allowed: false,
      reason: 'Cannot view users with higher privileges',
    };
  }

  // Approvers can view basic user info
  if (context.role === 'APPROVER') {
    if (!targetUserRole || getRoleLevel(targetUserRole) <= getRoleLevel('USER')) {
      return { allowed: true };
    }
    return {
      allowed: false,
      reason: 'Cannot view users with higher privileges',
    };
  }

  return {
    allowed: false,
    reason: 'Insufficient role to view other users',
  };
}

/**
 * Check if user can delete an API key
 * Only ADMIN and OWNER roles can delete API keys
 */
export function canDeleteApiKey(
  context: RLSContext,
  resource: RLSResource
): RLSPolicyResult {
  // Organization isolation check
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Only ADMIN and OWNER can delete API keys
  if (!['ADMIN', 'OWNER'].includes(context.role)) {
    return {
      allowed: false,
      reason: 'Only administrators can delete API keys',
    };
  }

  return hasPermission(context, 'api_keys:delete');
}

/**
 * Check if user can manage organization settings
 * Only OWNER and ADMIN roles can manage settings
 */
export function canManageSettings(context: RLSContext): PermissionResult {
  if (!['ADMIN', 'OWNER'].includes(context.role)) {
    return {
      allowed: false,
      reason: 'Only administrators can manage organization settings',
    };
  }

  return hasPermission(context, 'settings:manage');
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
  // Organization isolation check
  const orgCheck = checkOrganizationIsolation(context, resource);
  if (!orgCheck.allowed) {
    return orgCheck;
  }

  // Admins, finance, and owner can view all vendors
  if (['ADMIN', 'FINANCE', 'OWNER'].includes(context.role)) {
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
  // Organization isolation
  if (!context.organizationId && !context.tenantId) {
    return {
      allowed: false,
      reason: 'User must belong to an organization to manage vendors',
    };
  }

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
  userRole: OrgRole
): string {
  // Admins and owners see full data
  if (userRole === 'ADMIN' || userRole === 'OWNER') {
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
  userRole: OrgRole
): Record<string, unknown> {
  const masked = { ...data };

  for (const field of sensitiveFields) {
    if (masked[field] && typeof masked[field] === 'string') {
      masked[field] = maskSensitiveData(
        field,
        masked[field] as string,
        userRole
      );
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
  const userOrgId = context.organizationId ?? context.tenantId;

  return (invoice: Record<string, unknown>): boolean => {
    // Admin and owner can see all invoices in their organization
    if (context.role === 'ADMIN' || context.role === 'OWNER') {
      return invoice.organizationId === userOrgId || invoice.tenantId === userOrgId;
    }

    // Finance can see all invoices in their organization
    if (context.role === 'FINANCE') {
      return invoice.organizationId === userOrgId || invoice.tenantId === userOrgId;
    }

    // Tenant isolation for other roles
    if (
      invoice.organizationId &&
      invoice.organizationId !== userOrgId
    ) {
      return false;
    }
    if (invoice.tenantId && invoice.tenantId !== userOrgId) {
      return false;
    }

    // Role-based filtering
    switch (context.role) {
      case 'APPROVER':
        return invoice.status === 'PENDING';

      case 'USER':
        return ['APPROVED', 'REJECTED', 'PAID'].includes(
          invoice.status as string
        );

      case 'VIEWER':
        return ['APPROVED', 'PAID'].includes(invoice.status as string);

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
      id: record.id as string | undefined,
      organizationId: record.organizationId as string | undefined,
      tenantId: record.tenantId as string | undefined,
      status: record.status as string | undefined,
      amount: record.amount as number | undefined,
      isVerified: record.isVerified as boolean | undefined,
    };

    const result = canViewInvoice(context, resource);
    return result.allowed;
  });
}

// ============================================================================
// Export
// ============================================================================

export * from './types.js';
