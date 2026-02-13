/**
 * RLS Bindings Type Definition
 *
 * Extends Cloudflare Worker bindings with RLS-specific fields.
 */

export interface RLSBindings {
  // RLS context attached by middleware
  rlsContext?: {
    userId: string;
    role: 'VIEWER' | 'USER' | 'APPROVER' | 'FINANCE' | 'ADMIN';
    tenantId: string;
    email?: string;
    approvalLimit?: number;
  };
}
