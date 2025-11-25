"""Normalize JSON fields to relational models

Revision ID: 002_normalize_json_fields
Revises: 001_add_ingestion_system
Create Date: 2025-11-25 13:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_normalize_json_fields'
down_revision = '001_add_ingestion_system'
branch_labels = None
depends_on = None


def upgrade():
    """Normalize JSON fields to relational models."""
    
    # Create email_security_flags table
    op.create_table('email_security_flags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('email_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flag_type', sa.Enum('malicious_sender', 'phishing_attempt', 'suspicious_attachments', 
                                     'unusual_sender', 'domain_mismatch', 'blacklisted_ip', 
                                     'suspicious_content', 'malware_detected', 'ransomware', 
                                     'social_engineering', name='securityflagtype'), nullable=False),
        sa.Column('severity', sa.Integer(), nullable=False),
        sa.Column('confidence_score', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('detection_method', sa.String(length=100), nullable=True),
        sa.Column('detection_rule', sa.String(length=255), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['email_id'], ['emails.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_email_security_flags_email', 'email_security_flags', ['email_id'])
    op.create_index('idx_email_security_flags_type', 'email_security_flags', ['flag_type'])
    op.create_index('idx_email_security_flags_severity', 'email_security_flags', ['severity'])
    op.create_index('idx_email_security_flags_resolved', 'email_security_flags', ['is_resolved'])
    
    # Create workflow_steps table
    op.create_table('workflow_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_name', sa.String(length=100), nullable=False),
        sa.Column('step_type', sa.Enum('email_received', 'security_scan', 'content_extraction', 
                                     'invoice_parsing', 'data_validation', 'duplicate_check', 
                                     'approval_required', 'approved', 'rejected', 'exported', 
                                     'archived', name='workflowsteptype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'in_progress', 'completed', 'failed', 
                                  'skipped', 'cancelled', name='workflowstepstatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', sa.JSON(), nullable=True),
        sa.Column('executed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('execution_context', sa.JSON(), nullable=True),
        sa.Column('depends_on', sa.JSON(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_workflow_steps_invoice', 'workflow_steps', ['invoice_id'])
    op.create_index('idx_workflow_steps_type', 'workflow_steps', ['step_type'])
    op.create_index('idx_workflow_steps_status', 'workflow_steps', ['status'])
    op.create_index('idx_workflow_steps_order', 'workflow_steps', ['invoice_id', 'order_index'])
    
    # Create email_metadata table
    op.create_table('email_metadata',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('email_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=True),
        sa.Column('thread_id', sa.String(length=255), nullable=True),
        sa.Column('in_reply_to', sa.String(length=255), nullable=True),
        sa.Column('references', sa.JSON(), nullable=True),
        sa.Column('sender_domain', sa.String(length=255), nullable=True),
        sa.Column('sender_ip', sa.String(length=45), nullable=True),
        sa.Column('sender_reputation', sa.Integer(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('attachment_count', sa.Integer(), nullable=True),
        sa.Column('has_links', sa.Boolean(), nullable=False),
        sa.Column('link_count', sa.Integer(), nullable=True),
        sa.Column('urgency_level', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('confidence_score', sa.Integer(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('extraction_confidence', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['email_id'], ['emails.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_email_metadata_email', 'email_metadata', ['email_id'])
    op.create_index('idx_email_metadata_message_id', 'email_metadata', ['message_id'])
    op.create_index('idx_email_metadata_thread_id', 'email_metadata', ['thread_id'])
    op.create_index('idx_email_metadata_sender_domain', 'email_metadata', ['sender_domain'])
    op.create_index('idx_email_metadata_category', 'email_metadata', ['category'])
    op.create_index('idx_email_metadata_urgency', 'email_metadata', ['urgency_level'])
    
    # Create invoice_extraction_results table
    op.create_table('invoice_extraction_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('extraction_method', sa.String(length=50), nullable=False),
        sa.Column('extraction_version', sa.String(length=20), nullable=True),
        sa.Column('confidence_score', sa.Integer(), nullable=False),
        sa.Column('vendor_name', sa.String(length=255), nullable=True),
        sa.Column('invoice_number', sa.String(length=100), nullable=True),
        sa.Column('invoice_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_amount', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('line_items', sa.JSON(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), nullable=True),
        sa.Column('validation_errors', sa.JSON(), nullable=True),
        sa.Column('validation_warnings', sa.JSON(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('processor_version', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_extraction_results_invoice', 'invoice_extraction_results', ['invoice_id'])
    op.create_index('idx_extraction_results_method', 'invoice_extraction_results', ['extraction_method'])
    op.create_index('idx_extraction_results_confidence', 'invoice_extraction_results', ['confidence_score'])
    op.create_index('idx_extraction_results_vendor', 'invoice_extraction_results', ['vendor_name'])
    op.create_index('idx_extraction_results_date', 'invoice_extraction_results', ['invoice_date'])
    
    # Data migration from JSON fields
    # Note: This is a simplified migration. In production, you'd want more sophisticated
    # data transformation and validation logic
    
    # Migrate email security flags
    op.execute("""
        INSERT INTO email_security_flags (email_id, flag_type, severity, description, created_at, updated_at)
        SELECT 
            id as email_id,
            'suspicious_content' as flag_type,
            COALESCE((security_flags->>'severity')::int, 1) as severity,
            security_flags->>'description' as description,
            created_at,
            updated_at
        FROM emails 
        WHERE security_flags IS NOT NULL 
        AND jsonb_typeof(security_flags) = 'object'
    """)
    
    # Migrate workflow steps
    op.execute("""
        INSERT INTO workflow_steps (invoice_id, step_name, step_type, status, description, created_at, updated_at)
        SELECT 
            id as invoice_id,
            'data_processing' as step_name,
            'content_extraction' as step_type,
            CASE 
                WHEN workflow_data->>'status' = 'completed' THEN 'completed'
                WHEN workflow_data->>'status' = 'failed' THEN 'failed'
                ELSE 'pending'
            END as status,
            workflow_data->>'description' as description,
            created_at,
            updated_at
        FROM invoices 
        WHERE workflow_data IS NOT NULL 
        AND jsonb_typeof(workflow_data) = 'object'
    """)
    
    # Migrate email metadata
    op.execute("""
        INSERT INTO email_metadata (email_id, message_id, thread_id, sender_domain, word_count, attachment_count, created_at, updated_at)
        SELECT 
            id as email_id,
            email_metadata->>'message_id' as message_id,
            email_metadata->>'thread_id' as thread_id,
            SPLIT_PART(email_metadata->>'from', '@', 2) as sender_domain,
            COALESCE((email_metadata->>'word_count')::int, 0) as word_count,
            COALESCE((email_metadata->>'attachment_count')::int, 0) as attachment_count,
            created_at,
            updated_at
        FROM emails 
        WHERE email_metadata IS NOT NULL 
        AND jsonb_typeof(email_metadata) = 'object'
    """)


def downgrade():
    """Revert JSON field normalization."""
    
    # Drop new normalized tables
    op.drop_table('invoice_extraction_results')
    op.drop_table('email_metadata')
    op.drop_table('workflow_steps')
    op.drop_table('email_security_flags')
    
    # Note: We don't restore the original JSON fields as they would be
    # incomplete after the migration. In a real scenario, you'd want
    # to backup the original data before migration.