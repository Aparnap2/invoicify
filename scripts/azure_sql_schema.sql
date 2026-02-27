-- Azure SQL Server Schema for Invoicify
-- Run on Azure SQL serverless or local SQL Server emulator

-- Tenants table: Multi-tenant SaaS support
CREATE TABLE tenants (
    id              UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    name            NVARCHAR(255) NOT NULL,
    plan            NVARCHAR(50)  DEFAULT 'FREE',  -- FREE, PRO, ENTERPRISE
    auto_approve_limit DECIMAL(18,2) DEFAULT 500.00,
    created_at      DATETIME2 DEFAULT GETUTCDATE(),
    updated_at      DATETIME2 DEFAULT GETUTCDATE()
);

-- Vendors table: Trust battery storage
CREATE TABLE vendors (
    id                  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    tenant_id           UNIQUEIDENTIFIER NOT NULL REFERENCES tenants(id),
    name                NVARCHAR(255) NOT NULL,
    normalized_name     NVARCHAR(255) NOT NULL,  -- lowercase, trimmed for dedup
    tax_id              NVARCHAR(50),
    phone               NVARCHAR(50),
    email               NVARCHAR(255),
    trust_level         NVARCHAR(20) DEFAULT 'PROBATION',  -- PROBATION, STANDARD, CORE, STRATEGIC
    trust_score         FLOAT DEFAULT 0.0,
    invoice_count       INT DEFAULT 0,
    accurate_count      INT DEFAULT 0,
    error_count         INT DEFAULT 0,
    total_approved_amt  DECIMAL(18,2) DEFAULT 0,
    consecutive_errors  INT DEFAULT 0,
    last_invoice_at     DATETIME2,
    created_at          DATETIME2 DEFAULT GETUTCDATE(),
    updated_at          DATETIME2 DEFAULT GETUTCDATE(),
    CONSTRAINT UQ_Vendors_Tenant_Name UNIQUE (tenant_id, normalized_name)
);

-- Users table: Human reviewers
CREATE TABLE users (
    id              UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    tenant_id       UNIQUEIDENTIFIER NOT NULL REFERENCES tenants(id),
    email           NVARCHAR(255) NOT NULL UNIQUE,
    role            NVARCHAR(50) DEFAULT 'REVIEWER',  -- ADMIN, REVIEWER, VIEWER
    entra_oid       NVARCHAR(255),  -- Azure AD object ID for SSO
    created_at      DATETIME2 DEFAULT GETUTCDATE()
);

-- Approvals table: HITL decisions
CREATE TABLE approvals (
    id              UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    invoice_id      NVARCHAR(255) NOT NULL,
    tenant_id       UNIQUEIDENTIFIER NOT NULL,
    reviewer_id     UNIQUEIDENTIFIER REFERENCES users(id),
    decision        NVARCHAR(20),  -- APPROVED, REJECTED
    notes           NVARCHAR(2000),
    decided_at      DATETIME2,
    created_at      DATETIME2 DEFAULT GETUTCDATE()
);

-- Indexes for performance
CREATE INDEX idx_vendors_tenant ON vendors(tenant_id);
CREATE INDEX idx_vendors_name ON vendors(tenant_id, normalized_name);
CREATE INDEX idx_vendors_trust ON vendors(tenant_id, trust_level);
CREATE INDEX idx_approvals_invoice ON approvals(invoice_id);
CREATE INDEX idx_approvals_tenant ON approvals(tenant_id, decided_at DESC);
CREATE INDEX idx_approvals_reviewer ON approvals(reviewer_id, decided_at DESC);

-- Insert default tenant
INSERT INTO tenants (id, name, plan) VALUES 
    ('00000000-0000-0000-0000-000000000001', 'Default Tenant', 'FREE');
