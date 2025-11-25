"""
Normalized database models for JSON field normalization.

This module provides relational models to replace JSON fields
with proper database relationships for better performance and data integrity.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from enum import Enum

from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class SecurityFlagType(str, Enum):
    """Types of security flags for emails."""
    MALICIOUS_SENDER = "malicious_sender"
    PHISHING_ATTEMPT = "phishing_attempt"
    SUSPICIOUS_ATTACHMENTS = "suspicious_attachments"
    UNUSUAL_SENDER = "unusual_sender"
    DOMAIN_MISMATCH = "domain_mismatch"
    BLACKLISTED_IP = "blacklisted_ip"
    SUSPICIOUS_CONTENT = "suspicious_content"
    MALWARE_DETECTED = "malware_detected"
    RANSOMWARE = "ransomware"
    SOCIAL_ENGINEERING = "social_engineering"


class EmailSecurityFlag(BaseModel):
    """
    Normalized email security flags.
    
    Replaces JSON security_flags field with proper relational model
    for better query performance and data integrity.
    """
    __tablename__ = "email_security_flags"
    
    # Foreign key to email
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False)
    
    # Security flag information
    flag_type = Column(SQLEnum(SecurityFlagType), nullable=False)
    severity = Column(Integer, nullable=False, default=1)  # 1-5 severity scale
    confidence_score = Column(Integer, nullable=True)  # 0-100 confidence
    description = Column(Text, nullable=True)
    
    # Detection information
    detection_method = Column(String(100), nullable=True)  # regex, ml, heuristic, etc.
    detection_rule = Column(String(255), nullable=True)  # Rule that triggered flag
    raw_data = Column(JSON, nullable=True)  # Original detection data
    
    # Status
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_email_security_flags_email', 'email_id'),
        Index('idx_email_security_flags_type', 'flag_type'),
        Index('idx_email_security_flags_severity', 'severity'),
        Index('idx_email_security_flags_resolved', 'is_resolved'),
    )
    
    def __repr__(self):
        return f"<EmailSecurityFlag(id={self.id}, email_id={self.email_id}, type={self.flag_type})>"
    
    def resolve(self, user_id: uuid.UUID, notes: str = None):
        """Mark security flag as resolved."""
        self.is_resolved = True
        self.resolved_by = user_id
        self.resolved_at = datetime.utcnow()
        self.resolution_notes = notes


class WorkflowStepStatus(str, Enum):
    """Status of workflow steps."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowStepType(str, Enum):
    """Types of workflow steps."""
    EMAIL_RECEIVED = "email_received"
    SECURITY_SCAN = "security_scan"
    CONTENT_EXTRACTION = "content_extraction"
    INVOICE_PARSING = "invoice_parsing"
    DATA_VALIDATION = "data_validation"
    DUPLICATE_CHECK = "duplicate_check"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class WorkflowStep(BaseModel):
    """
    Normalized workflow steps for invoices.
    
    Replaces JSON workflow_data field with proper relational model
    for better tracking and audit capabilities.
    """
    __tablename__ = "workflow_steps"
    
    # Foreign key to invoice
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    
    # Step information
    step_name = Column(String(100), nullable=False)
    step_type = Column(SQLEnum(WorkflowStepType), nullable=False)
    status = Column(SQLEnum(WorkflowStepStatus), nullable=False, default=WorkflowStepStatus.PENDING)
    
    # Timing information
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Duration in milliseconds
    
    # Step details
    description = Column(Text, nullable=True)
    input_data = Column(JSON, nullable=True)  # Input parameters for the step
    output_data = Column(JSON, nullable=True)  # Results from the step
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Execution context
    executed_by = Column(UUID(as_uuid=True), nullable=True)  # User or system that executed
    execution_context = Column(JSON, nullable=True)  # Additional context (IP, user agent, etc.)
    
    # Dependencies and ordering
    depends_on = Column(JSON, nullable=True)  # List of step IDs this step depends on
    order_index = Column(Integer, nullable=False, default=0)  # Execution order
    
    # Indexes
    __table_args__ = (
        Index('idx_workflow_steps_invoice', 'invoice_id'),
        Index('idx_workflow_steps_type', 'step_type'),
        Index('idx_workflow_steps_status', 'status'),
        Index('idx_workflow_steps_order', 'invoice_id', 'order_index'),
    )
    
    def __repr__(self):
        return f"<WorkflowStep(id={self.id}, invoice_id={self.invoice_id}, step={self.step_name})>"
    
    def start(self, user_id: uuid.UUID = None, context: Dict[str, Any] = None):
        """Start workflow step execution."""
        self.status = WorkflowStepStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        self.executed_by = user_id
        self.execution_context = context or {}
    
    def complete(self, output_data: Dict[str, Any] = None, duration_ms: int = None):
        """Mark workflow step as completed."""
        self.status = WorkflowStepStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.output_data = output_data
        if duration_ms:
            self.duration_ms = duration_ms
        elif self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds() * 1000
            self.duration_ms = int(duration)
    
    def fail(self, error_message: str, error_details: Dict[str, Any] = None):
        """Mark workflow step as failed."""
        self.status = WorkflowStepStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.error_details = error_details
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds() * 1000
            self.duration_ms = int(duration)


class EmailMetadata(BaseModel):
    """
    Normalized email metadata.
    
    Replaces JSON email_metadata field with proper relational model
    for better search and filtering capabilities.
    """
    __tablename__ = "email_metadata"
    
    # Foreign key to email
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False)
    
    # Email metadata fields
    message_id = Column(String(255), nullable=True)  # RFC message ID
    thread_id = Column(String(255), nullable=True)  # Gmail thread ID
    in_reply_to = Column(String(255), nullable=True)  # Message ID this replies to
    references = Column(JSON, nullable=True)  # List of referenced message IDs
    
    # Sender information
    sender_domain = Column(String(255), nullable=True)
    sender_ip = Column(String(45), nullable=True)
    sender_reputation = Column(Integer, nullable=True)  # 0-100 reputation score
    
    # Content analysis
    word_count = Column(Integer, nullable=True)
    attachment_count = Column(Integer, nullable=True)
    has_links = Column(Boolean, default=False, nullable=False)
    link_count = Column(Integer, nullable=True)
    urgency_level = Column(Integer, nullable=True)  # 1-5 urgency based on content
    
    # Classification
    category = Column(String(50), nullable=True)  # invoice, notification, spam, etc.
    confidence_score = Column(Integer, nullable=True)  # 0-100 classification confidence
    
    # Processing metadata
    processing_time_ms = Column(Integer, nullable=True)
    extraction_confidence = Column(Integer, nullable=True)  # 0-100 extraction confidence
    
    # Indexes
    __table_args__ = (
        Index('idx_email_metadata_email', 'email_id'),
        Index('idx_email_metadata_message_id', 'message_id'),
        Index('idx_email_metadata_thread_id', 'thread_id'),
        Index('idx_email_metadata_sender_domain', 'sender_domain'),
        Index('idx_email_metadata_category', 'category'),
        Index('idx_email_metadata_urgency', 'urgency_level'),
    )
    
    def __repr__(self):
        return f"<EmailMetadata(id={self.id}, email_id={self.email_id}, category={self.category})>"


class InvoiceExtractionResult(BaseModel):
    """
    Normalized invoice extraction results.
    
    Replaces JSON extraction fields with proper relational model
    for better data validation and tracking.
    """
    __tablename__ = "invoice_extraction_results"
    
    # Foreign key to invoice
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    
    # Extraction information
    extraction_method = Column(String(50), nullable=False)  # ocr, ml, manual, etc.
    extraction_version = Column(String(20), nullable=True)  # Version of extraction algorithm
    confidence_score = Column(Integer, nullable=False)  # 0-100 overall confidence
    
    # Extracted data
    vendor_name = Column(String(255), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    total_amount = Column(Integer, nullable=True)  # Store in cents
    currency = Column(String(3), nullable=True)
    
    # Line items
    line_items = Column(JSON, nullable=True)  # Keep as JSON for complex line items
    
    # Validation results
    is_valid = Column(Boolean, nullable=True)
    validation_errors = Column(JSON, nullable=True)
    validation_warnings = Column(JSON, nullable=True)
    
    # Processing metadata
    processing_time_ms = Column(Integer, nullable=True)
    processor_version = Column(String(20), nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_extraction_results_invoice', 'invoice_id'),
        Index('idx_extraction_results_method', 'extraction_method'),
        Index('idx_extraction_results_confidence', 'confidence_score'),
        Index('idx_extraction_results_vendor', 'vendor_name'),
        Index('idx_extraction_results_date', 'invoice_date'),
    )
    
    def __repr__(self):
        return f"<InvoiceExtractionResult(id={self.id}, invoice_id={self.invoice_id}, confidence={self.confidence_score})>"
    
    @property
    def total_amount_dollars(self) -> float:
        """Get total amount in dollars."""
        return self.total_amount / 100.0 if self.total_amount else 0.0