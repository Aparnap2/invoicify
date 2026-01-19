-- Row-Level Security (RLS) Policies for Invoicify D1 Database
-- Note: D1 doesn't support native PostgreSQL RLS, so these are implemented
-- as security policies and query-level access controls in the application layer.
--
-- These policies define data access rules for multi-tenant invoice processing.

-- ============================================================================
-- RLS POLICY DEFINITIONS
-- ============================================================================

-- ============================================================================
-- POLICY 1: Invoice Visibility
-- ============================================================================
-- Users can only see invoices within their organization/tenant context
-- Implemented via: tenant_id column (added in migration) + API filtering

-- ============================================================================
-- POLICY 2: Approval Access Control
-- ============================================================================
-- Approvers can only approve invoices within their approval threshold
-- Implemented via: amount_threshold check in approval API

-- ============================================================================
-- POLICY 3: Vendor Access Control
-- ============================================================================
-- Users can only access verified vendors unless admin
-- Implemented via: is_verified column + role-based access

-- ============================================================================
-- POLICY 4: Audit Log Read Access
-- ============================================================================
-- Only admins and auditors can read audit logs
-- Implemented via: role-based middleware

-- ============================================================================
-- POLICY 5: Sync Queue Access
-- ============================================================================
-- Only system processes can modify sync queue
-- Implemented via: service account authentication

-- ============================================================================
-- RLS ENFORCEMENT FUNCTIONS (for use in API layer)
-- ============================================================================

-- Function: can_view_invoice(user_role, invoice_status, user_tenant)
-- Returns: boolean indicating if user can view the invoice
/*
CREATE FUNCTION IF NOT EXISTS can_view_invoice(
  user_role TEXT,
  invoice_status TEXT,
  user_tenant TEXT
) RETURNS INTEGER AS $$
BEGIN
  -- Admins can view all invoices
  IF user_role = 'ADMIN' THEN
    RETURN 1;
  END IF;

  -- Finance team can view all invoices
  IF user_role = 'FINANCE' THEN
    RETURN 1;
  END IF;

  -- Regular users can only view approved/completed invoices
  IF user_role = 'USER' AND invoice_status IN ('APPROVED', 'PAID', 'REJECTED') THEN
    RETURN 1;
  END IF;

  -- Approvers can view pending invoices in their queue
  IF user_role = 'APPROVER' AND invoice_status = 'PENDING' THEN
    RETURN 1;
  END IF;

  RETURN 0;
END;
$$;
*/

-- Function: can_approve_invoice(user_role, invoice_amount, user_limit)
-- Returns: boolean indicating if user can approve this invoice
/*
CREATE FUNCTION IF NOT EXISTS can_approve_invoice(
  user_role TEXT,
  invoice_amount REAL,
  user_limit REAL
) RETURNS INTEGER AS $$
BEGIN
  -- Only approvers can approve
  IF user_role NOT IN ('ADMIN', 'FINANCE', 'APPROVER') THEN
    RETURN 0;
  END IF;

  -- Amount must be within user's approval limit
  IF invoice_amount <= user_limit THEN
    RETURN 1;
  END IF;

  -- Admins and finance can approve any amount
  IF user_role IN ('ADMIN', 'FINANCE') THEN
    RETURN 1;
  END IF;

  RETURN 0;
END;
$$;
*/

-- ============================================================================
-- DATA MASKING POLICIES
-- ============================================================================

-- Mask sensitive PII data for non-admin users
/*
CREATE FUNCTION IF NOT EXISTS mask_sensitive_data(
  field_name TEXT,
  field_value TEXT,
  user_role TEXT
) RETURNS TEXT AS $$
BEGIN
  -- Admins see full data
  IF user_role = 'ADMIN' THEN
    RETURN field_value;
  END IF;

  -- Mask SSN: XXX-XX-1234
  IF field_name = 'ssn' THEN
    RETURN 'XXX-XX-' || RIGHT(field_value, 4);
  END IF;

  -- Mask bank account: XXXX1234
  IF field_name = 'bank_account' THEN
    RETURN 'XXXX' || RIGHT(field_value, 4);
  END IF;

  -- Mask email: j***@example.com
  IF field_name = 'email' THEN
    RETURN LEFT(field_value, 1) || '***' || SUBSTRING(field_value FROM '@');
  END IF;

  RETURN field_value;
END;
$$;
*/

-- ============================================================================
-- AUDIT LOGGING FOR RLS VIOLATIONS
-- ============================================================================

-- Log access attempts for security monitoring
/*
CREATE TABLE IF NOT EXISTS rls_audit_log (
  id TEXT NOT NULL PRIMARY KEY,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  denied_reason TEXT,
  ip_address TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
*/

-- ============================================================================
-- INDEXES FOR RLS PERFORMANCE
-- ============================================================================

-- Index for invoice status filtering
CREATE INDEX IF NOT EXISTS `idx_invoices_status_tenant` ON `invoices`(`status`);

-- Index for approval queue filtering
CREATE INDEX IF NOT EXISTS `idx_approvals_status_approver` ON `approvals`(`status`, `approver_email`);
