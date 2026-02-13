/**
 * RLS Policy Tests
 *
 * Run with: pnpm test -- test/lib/rls
 */

import { describe, it, expect } from 'vitest';
import {
  hasPermission,
  hasRole,
  canViewInvoice,
  canCreateInvoice,
  canUpdateInvoice,
  canApproveInvoice,
  canDeleteInvoice,
  canViewVendor,
  maskSensitiveData,
  maskData,
  buildInvoiceFilter,
  filterByRLS,
} from './policies.js';
import type { RLSContext, RLSResource } from './types.js';

describe('RLS Permission Checks', () => {
  const adminContext: RLSContext = {
    userId: 'admin-1',
    role: 'ADMIN',
    tenantId: 'tenant-1',
  };

  const financeContext: RLSContext = {
    userId: 'finance-1',
    role: 'FINANCE',
    tenantId: 'tenant-1',
  };

  const approverContext: RLSContext = {
    userId: 'approver-1',
    role: 'APPROVER',
    tenantId: 'tenant-1',
    approvalLimit: 1000,
  };

  const userContext: RLSContext = {
    userId: 'user-1',
    role: 'USER',
    tenantId: 'tenant-1',
  };

  describe('hasPermission', () => {
    it('should grant all permissions to admin', () => {
      expect(hasPermission(adminContext, 'invoices:read').allowed).toBe(true);
      expect(hasPermission(adminContext, 'invoices:write').allowed).toBe(true);
      expect(hasPermission(adminContext, 'invoices:delete').allowed).toBe(true);
      expect(hasPermission(adminContext, 'audit_logs:read').allowed).toBe(true);
    });

    it('should grant limited permissions to viewer', () => {
      const viewerContext: RLSContext = {
        userId: 'viewer-1',
        role: 'VIEWER',
        tenantId: 'tenant-1',
      };
      expect(hasPermission(viewerContext, 'invoices:read').allowed).toBe(true);
      expect(hasPermission(viewerContext, 'invoices:write').allowed).toBe(false);
    });

    it('should deny non-existent permissions', () => {
      const result = hasPermission(userContext, 'users:delete');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBeDefined();
    });
  });

  describe('hasRole', () => {
    it('should allow higher roles', () => {
      expect(hasRole(adminContext, 'USER').allowed).toBe(true);
      expect(hasRole(adminContext, 'APPROVER').allowed).toBe(true);
      expect(hasRole(adminContext, 'FINANCE').allowed).toBe(true);
      expect(hasRole(adminContext, 'ADMIN').allowed).toBe(true);
    });

    it('should deny lower roles', () => {
      expect(hasRole(userContext, 'ADMIN').allowed).toBe(false);
      expect(hasRole(userContext, 'FINANCE').allowed).toBe(false);
      expect(hasRole(userContext, 'APPROVER').allowed).toBe(false);
    });
  });
});

describe('Invoice Access Policies', () => {
  const adminContext: RLSContext = {
    userId: 'admin-1',
    role: 'ADMIN',
    tenantId: 'tenant-1',
  };

  const approverContext: RLSContext = {
    userId: 'approver-1',
    role: 'APPROVER',
    tenantId: 'tenant-1',
    approvalLimit: 1000,
  };

  const userContext: RLSContext = {
    userId: 'user-1',
    role: 'USER',
    tenantId: 'tenant-1',
  };

  describe('canViewInvoice', () => {
    it('should allow admin to view any invoice', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'NEW',
        tenantId: 'tenant-1',
      };
      expect(canViewInvoice(adminContext, invoice).allowed).toBe(true);
    });

    it('should allow approver to view pending invoices', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'PENDING',
        tenantId: 'tenant-1',
      };
      expect(canViewInvoice(approverContext, invoice).allowed).toBe(true);
    });

    it('should deny approver from viewing approved invoices', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'APPROVED',
        tenantId: 'tenant-1',
      };
      expect(canViewInvoice(approverContext, invoice).allowed).toBe(false);
    });

    it('should allow user to view approved invoices', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'APPROVED',
        tenantId: 'tenant-1',
      };
      expect(canViewInvoice(userContext, invoice).allowed).toBe(true);
    });

    it('should deny access to different tenant', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'APPROVED',
        tenantId: 'tenant-2', // Different tenant
      };
      const result = canViewInvoice(userContext, invoice);
      expect(result.allowed).toBe(false);
      expect(result.reason).toContain('different organization');
    });
  });

  describe('canCreateInvoice', () => {
    it('should allow user to create invoice', () => {
      expect(canCreateInvoice(userContext).allowed).toBe(true);
    });

    it('should deny viewer to create invoice', () => {
      const viewerContext: RLSContext = {
        userId: 'viewer-1',
        role: 'VIEWER',
        tenantId: 'tenant-1',
      };
      expect(canCreateInvoice(viewerContext).allowed).toBe(false);
    });
  });

  describe('canApproveInvoice', () => {
    it('should allow approver within limit', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'PENDING',
        amount: 500,
        tenantId: 'tenant-1',
      };
      expect(canApproveInvoice(approverContext, invoice).allowed).toBe(true);
    });

    it('should deny approver over limit', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'PENDING',
        amount: 2000, // Over limit of 1000
        tenantId: 'tenant-1',
      };
      expect(canApproveInvoice(approverContext, invoice).allowed).toBe(false);
    });

    it('should allow admin to approve any amount', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'PENDING',
        amount: 100000,
        tenantId: 'tenant-1',
      };
      expect(canApproveInvoice(adminContext, invoice).allowed).toBe(true);
    });
  });

  describe('canDeleteInvoice', () => {
    it('should only allow admin to delete', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'NEW',
        tenantId: 'tenant-1',
      };
      expect(canDeleteInvoice(adminContext, invoice).allowed).toBe(true);
      expect(canDeleteInvoice(userContext, invoice).allowed).toBe(false);
    });

    it('should deny deletion of paid invoices', () => {
      const invoice: RLSResource = {
        type: 'invoice',
        id: 'inv-1',
        status: 'PAID',
        tenantId: 'tenant-1',
      };
      expect(canDeleteInvoice(adminContext, invoice).allowed).toBe(false);
    });
  });
});

describe('Vendor Access Policies', () => {
  const adminContext: RLSContext = {
    userId: 'admin-1',
    role: 'ADMIN',
    tenantId: 'tenant-1',
  };

  const userContext: RLSContext = {
    userId: 'user-1',
    role: 'USER',
    tenantId: 'tenant-1',
  };

  describe('canViewVendor', () => {
    it('should allow admin to view any vendor', () => {
      const vendor: RLSResource = {
        type: 'vendor',
        id: 'vnd-1',
        isVerified: false,
        tenantId: 'tenant-1',
      };
      expect(canViewVendor(adminContext, vendor).allowed).toBe(true);
    });

    it('should allow user to view verified vendors', () => {
      const vendor: RLSResource = {
        type: 'vendor',
        id: 'vnd-1',
        isVerified: true,
        tenantId: 'tenant-1',
      };
      expect(canViewVendor(userContext, vendor).allowed).toBe(true);
    });

    it('should deny user from viewing unverified vendors', () => {
      const vendor: RLSResource = {
        type: 'vendor',
        id: 'vnd-1',
        isVerified: false,
        tenantId: 'tenant-1',
      };
      expect(canViewVendor(userContext, vendor).allowed).toBe(false);
    });
  });
});

describe('Data Masking', () => {
  const adminContext: RLSContext = {
    userId: 'admin-1',
    role: 'ADMIN',
    tenantId: 'tenant-1',
  };

  const userContext: RLSContext = {
    userId: 'user-1',
    role: 'USER',
    tenantId: 'tenant-1',
  };

  describe('maskSensitiveData', () => {
    it('should not mask for admin', () => {
      expect(maskSensitiveData('ssn', '123-45-6789', 'ADMIN')).toBe(
        '123-45-6789'
      );
      expect(maskSensitiveData('bank_account', '1234567890', 'ADMIN')).toBe(
        '1234567890'
      );
    });

    it('should mask SSN for non-admin', () => {
      expect(maskSensitiveData('ssn', '123-45-6789', 'USER')).toBe(
        'XXX-XX-6789'
      );
    });

    it('should mask bank account for non-admin', () => {
      expect(maskSensitiveData('bank_account', '1234567890', 'USER')).toBe(
        'XXXX7890'
      );
    });

    it('should mask email for non-admin', () => {
      expect(
        maskSensitiveData('email', 'john.doe@example.com', 'USER')
      ).toBe('j***@example.com');
    });

    it('should mask phone for non-admin', () => {
      expect(
        maskSensitiveData('phone', '(555) 123-4567', 'USER')
      ).toMatch(/\(XXX\) XXX-4567/);
    });
  });

  describe('maskData', () => {
    it('should mask multiple fields', () => {
      const data = {
        id: 'inv-1',
        vendor: 'Acme Corp',
        ssn: '123-45-6789',
        bank_account: '9876543210',
      };

      const masked = maskData(data, ['ssn', 'bank_account'], 'USER');

      expect(masked.id).toBe('inv-1');
      expect(masked.vendor).toBe('Acme Corp');
      expect(masked.ssn).toBe('XXX-XX-6789');
      expect(masked.bank_account).toBe('XXXX3210');
    });

    it('should not mask any fields for admin', () => {
      const data = {
        id: 'inv-1',
        ssn: '123-45-6789',
        bank_account: '9876543210',
      };

      const masked = maskData(data, ['ssn', 'bank_account'], 'ADMIN');

      expect(masked).toEqual(data);
    });
  });
});

describe('Query Filtering', () => {
  const adminContext: RLSContext = {
    userId: 'admin-1',
    role: 'ADMIN',
    tenantId: 'tenant-1',
  };

  const approverContext: RLSContext = {
    userId: 'approver-1',
    role: 'APPROVER',
    tenantId: 'tenant-1',
  };

  const userContext: RLSContext = {
    userId: 'user-1',
    role: 'USER',
    tenantId: 'tenant-1',
  };

  const invoices = [
    { id: '1', status: 'NEW', tenantId: 'tenant-1' },
    { id: '2', status: 'PENDING', tenantId: 'tenant-1' },
    { id: '3', status: 'APPROVED', tenantId: 'tenant-1' },
    { id: '4', status: 'REJECTED', tenantId: 'tenant-1' },
    { id: '5', status: 'PAID', tenantId: 'tenant-1' },
    { id: '6', status: 'PENDING', tenantId: 'tenant-2' }, // Different tenant
  ];

  describe('buildInvoiceFilter', () => {
    it('should allow admin to see all invoices in their tenant', () => {
      const filter = buildInvoiceFilter(adminContext);
      const visible = invoices.filter(filter);
      // Admin sees all invoices from their tenant (tenant-1) = 5 invoices
      // Invoice 6 is from tenant-2, so it's filtered out
      expect(visible).toHaveLength(5);
      expect(visible.every(i => i.tenantId === 'tenant-1')).toBe(true);
    });

    it('should allow approver to see only pending', () => {
      const filter = buildInvoiceFilter(approverContext);
      const visible = invoices.filter(filter);
      expect(visible).toHaveLength(1);
      expect(visible[0].id).toBe('2');
    });

    it('should allow user to see approved/rejected/paid', () => {
      const filter = buildInvoiceFilter(userContext);
      const visible = invoices.filter(filter);
      expect(visible).toHaveLength(3);
      expect(visible.map((i) => i.id).sort()).toEqual(['3', '4', '5']);
    });

    it('should filter out other tenant invoices', () => {
      const filter = buildInvoiceFilter(userContext);
      const visible = invoices.filter(filter);
      expect(visible.every((i) => i.tenantId === 'tenant-1')).toBe(true);
    });
  });

  describe('filterByRLS', () => {
    it('should filter invoices by RLS context', () => {
      const filtered = filterByRLS(invoices, adminContext, 'invoice');
      // Admin sees 5 invoices from their tenant (tenant-1)
      expect(filtered).toHaveLength(5);

      const userFiltered = filterByRLS(invoices, userContext, 'invoice');
      expect(userFiltered).toHaveLength(3);
    });
  });
});
