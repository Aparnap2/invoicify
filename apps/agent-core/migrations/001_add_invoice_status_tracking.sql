-- ═══════════════════════════════════════════════════════════════
-- Invoice Status Tracking Migration
-- ═══════════════════════════════════════════════════════════════
-- 
-- Purpose: Add direct Postgres status tracking to replace
--          edge_callback.py (Cloudflare Worker HTTP calls)
--
-- Background:
--   The old system called http://host.docker.internal:8787
--   (Cloudflare Worker) to update invoice status. This fails
--   in Azure Container Apps. Now we write directly to Postgres.
--
-- Usage:
--   psql $DATABASE_URL -f migrations/001_add_invoice_status_tracking.sql
-- ═══════════════════════════════════════════════════════════════

-- Add trace_id for correlation (if not exists)
ALTER TABLE invoices 
ADD COLUMN IF NOT EXISTS trace_id TEXT;

-- Add status field (PENDING, APPROVED, REJECTED, ERROR, PAID)
ALTER TABLE invoices 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'PENDING';

-- Add metadata JSONB for flexible data storage
ALTER TABLE invoices 
ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Add updated_at timestamp
ALTER TABLE invoices 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Create index for fast trace_id lookups
CREATE INDEX IF NOT EXISTS idx_invoices_trace_id 
ON invoices(trace_id);

-- Create index for status filtering
CREATE INDEX IF NOT EXISTS idx_invoices_status 
ON invoices(status);

-- Add comment for documentation
COMMENT ON COLUMN invoices.trace_id IS 'Unique correlation ID for pipeline tracking';
COMMENT ON COLUMN invoices.status IS 'Current invoice status: PENDING, APPROVED, REJECTED, ERROR, PAID';
COMMENT ON COLUMN invoices.metadata IS 'Flexible JSON metadata for pipeline state';
COMMENT ON INDEX idx_invoices_trace_id IS 'Fast lookup by trace_id for status updates';

-- Add content_hash column for duplicate detection
ALTER TABLE invoices
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_invoices_content_hash
ON invoices(content_hash);

COMMENT ON COLUMN invoices.content_hash IS 'SHA256 hash of invoice content for duplicate detection';
