"""
Custom exceptions for the AP Intake & Validation system.
"""

from typing import Any, Dict, Optional


class APIntakeException(Exception):
    """Base exception for AP Intake system."""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(APIntakeException):
    """Raised when invoice validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class ConflictException(APIntakeException):
    """Raised when a conflict occurs, such as duplicate operations."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONFLICT_ERROR",
            details=details,
        )


class ExtractionException(APIntakeException):
    """Raised when document extraction fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EXTRACTION_ERROR",
            details=details,
        )


class StorageException(APIntakeException):
    """Raised when storage operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            details=details,
        )


class WorkflowException(APIntakeException):
    """Raised when workflow state machine fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="WORKFLOW_ERROR",
            details=details,
        )


class ExportException(APIntakeException):
    """Raised when export operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EXPORT_ERROR",
            details=details,
        )


class EmailException(APIntakeException):
    """Raised when email processing fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EMAIL_ERROR",
            details=details,
        )


class EmailServiceException(EmailException):
    """Raised when email service operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EMAIL_SERVICE_ERROR",
            details=details,
        )


class EmailIngestionException(EmailException):
    """Raised when email ingestion fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EMAIL_INGESTION_ERROR",
            details=details,
        )


class NotificationException(APIntakeException):
    """Raised when notification operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="NOTIFICATION_ERROR",
            details=details,
        )


class ConfigurationException(APIntakeException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details,
        )


class IngestionException(APIntakeException):
    """Raised when file ingestion fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="INGESTION_ERROR",
            details=details,
        )


class DeduplicationException(APIntakeException):
    """Raised when deduplication operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DEDUPLICATION_ERROR",
            details=details,
        )


class ExternalServiceException(APIntakeException):
    """Raised when external service operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )


class DiffException(APIntakeException):
    """Raised when diff operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DIFF_ERROR",
            details=details,
        )


class EvidenceHarnessException(APIntakeException):
    """Raised when evidence harness operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EVIDENCE_HARNESS_ERROR",
            details=details,
        )


class ERPException(APIntakeException):
    """Raised when ERP operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="ERP_ERROR",
            details=details,
        )


class SecurityException(APIntakeException):
    """Raised when security validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="SECURITY_ERROR",
            details=details,
        )


class LLMException(APIntakeException):
    """Raised when LLM operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="LLM_ERROR",
            details=details,
        )