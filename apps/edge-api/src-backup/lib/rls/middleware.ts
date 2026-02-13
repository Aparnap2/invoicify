/**
 * RLS Middleware for Cloudflare Worker
 *
 * Wraps API handlers with Row-Level Security checks.
 */

import type { Context, Env } from 'hono';
import type { RLSContext, RLSPolicyResult } from './types.js';
import {
  canViewInvoice,
  canViewVendor,
  canViewAuditLogs,
  canApproveInvoice,
  canCreateInvoice,
  canUpdateInvoice,
  canDeleteInvoice,
  canManageVendor,
  filterByRLS,
  maskData,
  hasPermission,
} from './policies.js';
import type { RLSBindings } from './bindings.js';

/**
 * Extract user context from request
 */
export function extractRLSContext(c: Context<Env>): RLSContext {
  // Get user from JWT or session (implementation depends on auth setup)
  const user = c.get('user') as {
    id: string;
    role: RLSContext['role'];
    tenantId: string;
    email?: string;
    approvalLimit?: number;
  } | null;

  if (!user) {
    // Default to VIEWER for unauthenticated requests
    return {
      userId: 'anonymous',
      role: 'VIEWER',
      tenantId: c.get('tenantId') || 'default',
    };
  }

  return {
    userId: user.id,
    role: user.role || 'VIEWER',
    tenantId: user.tenantId || c.get('tenantId') || 'default',
    email: user.email,
    approvalLimit: user.approvalLimit,
  };
}

/**
 * Create RLS-aware database query options
 */
export function applyRLS<T extends Record<string, unknown>>(
  context: RLSContext,
  resourceType: 'invoice' | 'vendor' | 'approval' | 'audit_log'
): {
  filter: (record: T) => boolean;
  mask: (data: Record<string, unknown>) => Record<string, unknown>;
} {
  const sensitiveFields: Record<string, string[]> = {
    invoice: ['bank_account', 'routing_number'],
    vendor: ['tax_id', 'bank_account', 'bank_routing', 'email', 'phone'],
    approval: [],
    audit_log: ['ip_address'],
  };

  return {
    filter: (record: T) => {
      // For invoices, use the canViewInvoice policy
      if (resourceType === 'invoice') {
        const result = canViewInvoice(context, {
          type: 'invoice',
          id: record.id,
          tenantId: record.tenantId,
          status: record.status,
          amount: record.amount,
        });
        return result.allowed;
      }

      // For vendors, use canViewVendor policy
      if (resourceType === 'vendor') {
        const result = canViewVendor(context, {
          type: 'vendor',
          id: record.id,
          tenantId: record.tenantId,
          isVerified: record.isVerified,
        });
        return result.allowed;
      }

      return true;
    },
    mask: (data: Record<string, unknown>) =>
      maskData(data, sensitiveFields[resourceType], context.role),
  };
}

/**
 * Check RLS for invoice operations
 */
export function checkInvoiceRLS(
  context: RLSContext,
  operation: 'create' | 'read' | 'update' | 'delete' | 'approve',
  resource?: {
    id?: string;
    tenantId?: string;
    status?: string;
    amount?: number;
  }
): RLSPolicyResult {
  switch (operation) {
    case 'create':
      const createResult = canCreateInvoice(context);
      return { allowed: createResult.allowed, reason: createResult.reason };

    case 'read':
      if (!resource) return { allowed: true };
      return canViewInvoice(context, {
        type: 'invoice',
        id: resource.id,
        tenantId: resource.tenantId,
        status: resource.status as RLSPolicyResult['allowed'] extends boolean
          ? never
          : string,
        amount: resource.amount,
      });

    case 'update':
      if (!resource) return { allowed: false, reason: 'Resource required' };
      return canUpdateInvoice(context, {
        type: 'invoice',
        id: resource.id,
        tenantId: resource.tenantId,
        status: resource.status as RLSPolicyResult['allowed'] extends boolean
          ? never
          : string,
      });

    case 'delete':
      if (!resource) return { allowed: false, reason: 'Resource required' };
      return canDeleteInvoice(context, {
        type: 'invoice',
        id: resource.id,
        tenantId: resource.tenantId,
        status: resource.status as RLSPolicyResult['allowed'] extends boolean
          ? never
          : string,
      });

    case 'approve':
      if (!resource) return { allowed: false, reason: 'Resource required' };
      return canApproveInvoice(context, {
        type: 'invoice',
        id: resource.id,
        tenantId: resource.tenantId,
        status: resource.status as RLSPolicyResult['allowed'] extends boolean
          ? never
          : string,
        amount: resource.amount,
      });

    default:
      return { allowed: false, reason: 'Unknown operation' };
  }
}

/**
 * RLS middleware factory
 */
export function withRLS<Bindings = RLSBindings>() {
  return async function rlsMiddleware(
    c: Context<Bindings>,
    next: () => Promise<void>
  ): Promise<void> {
    // Extract and set RLS context
    const rlsContext = extractRLSContext(c);
    c.set('rlsContext', rlsContext);

    await next();
  };
}

/**
 * Create a typed RLS context getter for use in handlers
 */
export function getRLSContext(c: Context): RLSContext {
  return c.get('rlsContext') || extractRLSContext(c);
}

/**
 * Require specific permission - throws if not allowed
 */
export function requirePermission(
  c: Context,
  permission: string,
  bindings?: Record<string, unknown>
): void {
  const context = getRLSContext(c);
  const result = hasPermission(context, permission);

  if (!result.allowed) {
    c.status(403);
    c.json({
      error: 'Forbidden',
      message: result.reason || 'Access denied',
    });
    throw new Error('RLS: Permission denied');
  }
}

/**
 * Require specific role - throws if not met
 */
export function requireRole(
  c: Context,
  requiredRole: RLSContext['role']
): void {
  const context = getRLSContext(c);

  if (context.role !== requiredRole && context.role !== 'ADMIN') {
    c.status(403);
    c.json({
      error: 'Forbidden',
      message: `Requires '${requiredRole}' role`,
    });
    throw new Error('RLS: Role requirement not met');
  }
}
