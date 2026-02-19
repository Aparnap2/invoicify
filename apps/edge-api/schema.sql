-- D1 Database Schema for Invoicify Edge
-- Run: wrangler d1 migrations apply invoicify-edge

-- Invoice submissions table (edge metadata only - no sensitive financial data)
CREATE TABLE IF NOT EXISTS invoice_submissions (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    trace_id    TEXT NOT NULL UNIQUE,
    r2_key      TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL,
    status      TEXT DEFAULT 'SUBMITTED' CHECK (status IN (
        'SUBMITTED',
        'EXTRACTING',
        'VALIDATING',
        'ANALYZING',
        'APPROVED',
        'PENDING_REVIEW',
        'REJECTED',
        'FAILED'
    )),
    submitted_at TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_submissions_tenant ON invoice_submissions(tenant_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_trace ON invoice_submissions(trace_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON invoice_submissions(tenant_id, status);

-- Trigger to update updated_at on row update
CREATE TRIGGER IF NOT EXISTS update_submissions_updated_at
AFTER UPDATE ON invoice_submissions
BEGIN
    UPDATE invoice_submissions SET updated_at = datetime('now') WHERE id = NEW.id;
END;
