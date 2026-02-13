-- Initial Migration
CREATE TABLE IF NOT EXISTS `invoices` (
  `id` TEXT PRIMARY KEY,
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
  `r2_key_raw` TEXT,
  `r2_key_processed` TEXT,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TEXT
);

CREATE TABLE IF NOT EXISTS `audit_logs` (
  `id` TEXT PRIMARY KEY,
  `timestamp` TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `organization_id` TEXT NOT NULL,
  `actor_user_id` TEXT NOT NULL,
  `actor_email` TEXT,
  `actor_name` TEXT,
  `actor_role` TEXT,
  `action` TEXT NOT NULL,
  `resource_type` TEXT NOT NULL,
  `resource_id` TEXT NOT NULL,
  `resource_name` TEXT,
  `details` TEXT,
  `severity` TEXT NOT NULL DEFAULT 'INFO',
  `ip_address` TEXT,
  `user_agent` TEXT,
  `correlation_id` TEXT,
  `archived_at` TEXT,
  `storage_location` TEXT,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `vendors` (
  `id` TEXT PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS `trust_battery` (
  `id` TEXT PRIMARY KEY,
  `vendor_id` TEXT NOT NULL REFERENCES `vendors`(`id`) ON DELETE CASCADE,
  `consecutive_accurate` INTEGER DEFAULT 0,
  `consecutive_errors` INTEGER DEFAULT 0,
  `total_decisions` INTEGER DEFAULT 0,
  `accurate_decisions` INTEGER DEFAULT 0,
  `last_decision_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `trust_level` INTEGER DEFAULT 3,
  `auto_approve_threshold` REAL DEFAULT 500,
  `created_at` TEXT DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TEXT
);

CREATE TABLE IF NOT EXISTS `risk_indicators` (
  `id` TEXT PRIMARY KEY,
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
