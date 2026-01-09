-- Create invoices table
CREATE TABLE IF NOT EXISTS `invoices` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `vendor_name` TEXT NOT NULL,
  `vendor_id` TEXT,
  `invoice_number` TEXT NOT NULL,
  `total_amount` REAL NOT NULL DEFAULT 0,
  `currency` TEXT DEFAULT 'USD',
  `status` TEXT DEFAULT 'NEW',
  `due_date` TEXT,
  `invoice_date` TEXT,
  `raw_content` TEXT,
  `extracted_data` TEXT,
  `confidence_score` REAL,
  `risk_score` REAL,
  `risk_level` TEXT,
  `file_url` TEXT,
  `file_name` TEXT,
  `mime_type` TEXT,
  `quickbooks_id` TEXT,
  `quickbooks_synced_at` TEXT,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TEXT
);

-- Create line_items table
CREATE TABLE IF NOT EXISTS `line_items` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `invoice_id` TEXT NOT NULL REFERENCES `invoices`(`id`) ON DELETE CASCADE,
  `description` TEXT NOT NULL,
  `quantity` REAL NOT NULL DEFAULT 1,
  `unit_price` REAL NOT NULL DEFAULT 0,
  `amount` REAL NOT NULL DEFAULT 0,
  `gl_code` TEXT,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Create vendors table
CREATE TABLE IF NOT EXISTS `vendors` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `name` TEXT NOT NULL,
  `tax_id` TEXT,
  `email` TEXT,
  `phone` TEXT,
  `address` TEXT,
  `bank_account` TEXT,
  `bank_routing` TEXT,
  `is_verified` INTEGER DEFAULT 0,
  `risk_level` TEXT,
  `avg_invoice_amount` REAL,
  `total_invoices` INTEGER DEFAULT 0,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TEXT
);

-- Create approvals table
CREATE TABLE IF NOT EXISTS `approvals` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `invoice_id` TEXT NOT NULL REFERENCES `invoices`(`id`) ON DELETE CASCADE,
  `approver_email` TEXT NOT NULL,
  `approver_name` TEXT,
  `status` TEXT NOT NULL DEFAULT 'PENDING',
  `comments` TEXT,
  `amount_threshold` REAL,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TEXT
);

-- Create audit_logs table
CREATE TABLE IF NOT EXISTS `audit_logs` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `action` TEXT NOT NULL,
  `entity_type` TEXT NOT NULL,
  `entity_id` TEXT NOT NULL,
  `performed_by` TEXT,
  `performed_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `changes` TEXT,
  `metadata` TEXT,
  `ip_address` TEXT
);

-- Create duplicate_checks table
CREATE TABLE IF NOT EXISTS `duplicate_checks` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `invoice_id` TEXT NOT NULL REFERENCES `invoices`(`id`) ON DELETE CASCADE,
  `checksum` TEXT NOT NULL,
  `duplicate_of_id` TEXT,
  `is_duplicate` INTEGER DEFAULT 0,
  `confidence` REAL,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Create risk_indicators table
CREATE TABLE IF NOT EXISTS `risk_indicators` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `invoice_id` TEXT NOT NULL REFERENCES `invoices`(`id`) ON DELETE CASCADE,
  `indicator_type` TEXT NOT NULL,
  `severity` TEXT NOT NULL,
  `description` TEXT NOT NULL,
  `score_contribution` REAL NOT NULL DEFAULT 0,
  `resolved` INTEGER DEFAULT 0,
  `resolved_at` TEXT,
  `resolved_by` TEXT,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Create sync_queue table
CREATE TABLE IF NOT EXISTS `sync_queue` (
  `id` TEXT NOT NULL PRIMARY KEY,
  `entity_type` TEXT NOT NULL,
  `entity_id` TEXT NOT NULL,
  `action` TEXT NOT NULL DEFAULT 'CREATE',
  `status` TEXT DEFAULT 'PENDING',
  `attempts` INTEGER DEFAULT 0,
  `last_error` TEXT,
  `scheduled_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `processed_at` TEXT
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS `idx_invoices_status` ON `invoices`(`status`);
CREATE INDEX IF NOT EXISTS `idx_invoices_vendor` ON `invoices`(`vendor_name`);
CREATE INDEX IF NOT EXISTS `idx_invoices_created` ON `invoices`(`created_at`);
CREATE INDEX IF NOT EXISTS `idx_line_items_invoice` ON `line_items`(`invoice_id`);
CREATE INDEX IF NOT EXISTS `idx_approvals_invoice` ON `approvals`(`invoice_id`);
CREATE INDEX IF NOT EXISTS `idx_audit_logs_entity` ON `audit_logs`(`entity_type`, `entity_id`);
CREATE INDEX IF NOT EXISTS `idx_risk_indicators_invoice` ON `risk_indicators`(`invoice_id`);
CREATE INDEX IF NOT EXISTS `idx_sync_queue_status` ON `sync_queue`(`status`);
