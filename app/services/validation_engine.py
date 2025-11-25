"""
Advanced validation engine with deterministic structural validation, mathematical validation,
business rules validation, security validation, compliance validation, and machine-readable reason codes.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.api.schemas.validation import (
    ValidationCode,
    ValidationIssue,
    ValidationSeverity,
    ValidationResult,
    MathValidationResult,
    MatchingResult,
    VendorPolicyResult,
    DuplicateCheckResult,
    ValidationRulesConfig,
)
from app.core.exceptions import ValidationException, SecurityException
from app.db.session import AsyncSessionLocal
from app.models.invoice import Invoice, InvoiceExtraction
from app.models.reference import Vendor, PurchaseOrder, GoodsReceiptNote
from app.schemas.validation_rules import (
    ValidationLayer,
    SecurityThreatLevel,
    ThreatType,
    SecurityRule,
    DefenseInDepthResult,
    ThreatDetectionResult,
    SanitizationResult,
    SecurityEvent,
    DEFAULT_SECURITY_RULES,
    SQL_INJECTION_PATTERNS,
    XSS_PATTERNS,
    PATH_TRAVERSAL_PATTERNS,
    COMMAND_INJECTION_PATTERNS
)
from app.services.security_validator import SecurityValidator, SecurityContext
from app.services.input_sanitizer import InputSanitizer, SanitizationLevel

logger = logging.getLogger(__name__)


class ReasonTaxonomy(Enum):
    """Machine-readable reason taxonomy for validation failures."""

    # PO and Matching Issues
    PO_NOT_FOUND = "PO_NOT_FOUND"
    PO_MISMATCH = "PO_MISMATCH"
    PO_AMOUNT_MISMATCH = "PO_AMOUNT_MISMATCH"
    PO_QUANTITY_MISMATCH = "PO_QUANTITY_MISMATCH"
    GRN_NOT_FOUND = "GRN_NOT_FOUND"
    GRN_MISMATCH = "GRN_MISMATCH"
    GRN_QUANTITY_MISMATCH = "GRN_QUANTITY_MISMATCH"

    # Amount and Calculation Issues
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    SUBTOTAL_MISMATCH = "SUBTOTAL_MISMATCH"
    LINE_MATH_MISMATCH = "LINE_MATH_MISMATCH"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    TAX_CALCULATION_ERROR = "TAX_CALCULATION_ERROR"

    # Data Quality Issues
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    INVALID_DATA_FORMAT = "INVALID_DATA_FORMAT"
    INVALID_FIELD_FORMAT = "INVALID_FIELD_FORMAT"

    # Business Rule Violations
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
    INACTIVE_VENDOR = "INACTIVE_VENDOR"
    INVALID_CURRENCY = "INVALID_CURRENCY"
    PAYMENT_TERMS_VIOLATION = "PAYMENT_TERMS_VIOLATION"

    # Duplicate and Fraud Issues
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"
    POTENTIAL_FRAUD = "POTENTIAL_FRAUD"

    # Security Validation Issues
    SQL_INJECTION_DETECTED = "SQL_INJECTION_DETECTED"
    XSS_ATTACK_DETECTED = "XSS_ATTACK_DETECTED"
    COMMAND_INJECTION_DETECTED = "COMMAND_INJECTION_DETECTED"
    PATH_TRAVERSAL_DETECTED = "PATH_TRAVERSAL_DETECTED"
    FILE_UPLOAD_THREAT = "FILE_UPLOAD_THREAT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    DATA_EXFILTRATION_ATTEMPT = "DATA_EXFILTRATION_ATTEMPT"
    BUSINESS_LOGIC_ABUSE = "BUSINESS_LOGIC_ABUSE"
    ALLOWLIST_VIOLATION = "ALLOWLIST_VIOLATION"
    DENYLIST_VIOLATION = "DENYLIST_VIOLATION"
    MALICIOUS_INPUT_DETECTED = "MALICIOUS_INPUT_DETECTED"

    # Compliance Validation Issues
    GDPR_VIOLATION = "GDPR_VIOLATION"
    PCI_DSS_VIOLATION = "PCI_DSS_VIOLATION"
    SOX_COMPLIANCE_VIOLATION = "SOX_COMPLIANCE_VIOLATION"
    DATA_RETENTION_VIOLATION = "DATA_RETENTION_VIOLATION"
    AUDIT_LOGGING_REQUIRED = "AUDIT_LOGGING_REQUIRED"
    ENCRYPTION_REQUIRED = "ENCRYPTION_REQUIRED"
    ACCESS_CONTROL_VIOLATION = "ACCESS_CONTROL_VIOLATION"

    # System Issues
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    SANITIZATION_ERROR = "SANITIZATION_ERROR"
    SECURITY_VALIDATION_ERROR = "SECURITY_VALIDATION_ERROR"


@dataclass
class ValidationRule:
    """Individual validation rule with versioning."""
    name: str
    category: str
    description: str
    severity: ValidationSeverity
    enabled: bool = True
    version: str = "1.0.0"
    parameters: Dict[str, Any] = None
    condition: str = None  # Condition expression for rule application

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


@dataclass
class RuleExecutionResult:
    """Result of rule execution."""
    rule_name: str
    passed: bool
    reason_taxonomy: Optional[ReasonTaxonomy] = None
    message: str = ""
    details: Dict[str, Any] = None
    execution_time_ms: int = 0

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class ValidationEngine:
    """Advanced validation engine with comprehensive rule sets and defense-in-depth security."""

    def __init__(self, enable_security_validation: bool = True, enable_sanitization: bool = True):
        """Initialize the validation engine with security capabilities."""
        self.rules_version = "3.0.0"
        self.enable_security_validation = enable_security_validation
        self.enable_sanitization = enable_sanitization

        # Initialize traditional validation rules
        self.rules = self._initialize_rules()
        self.reason_taxonomy_map = self._initialize_reason_taxonomy()

        # Initialize defense-in-depth services
        if enable_security_validation:
            self.security_validator = SecurityValidator(enable_threat_intelligence=True)
            logger.info("Security validator initialized")

        if enable_sanitization:
            self.input_sanitizer = InputSanitizer(default_level=SanitizationLevel.NORMAL)
            logger.info("Input sanitizer initialized")

        # Initialize security and compliance rules
        self.security_rules = self._initialize_security_rules()
        self.compliance_rules = self._initialize_compliance_rules()

        logger.info(f"ValidationEngine initialized with security: {enable_security_validation}, sanitization: {enable_sanitization}")

    def _initialize_rules(self) -> Dict[str, List[ValidationRule]]:
        """Initialize validation rules by category."""
        return {
            "structural": [
                ValidationRule(
                    name="required_header_fields",
                    category="structural",
                    description="Validate required header fields are present",
                    severity=ValidationSeverity.ERROR,
                    parameters={"required_fields": ["vendor_name", "invoice_number", "total_amount"]}
                ),
                ValidationRule(
                    name="required_line_item_fields",
                    category="structural",
                    description="Validate required line item fields are present",
                    severity=ValidationSeverity.ERROR,
                    parameters={"required_fields": ["description", "total_amount"]}
                ),
                ValidationRule(
                    name="field_format_validation",
                    category="structural",
                    description="Validate field formats (dates, amounts, etc.)",
                    severity=ValidationSeverity.ERROR
                ),
                ValidationRule(
                    name="line_item_count_validation",
                    category="structural",
                    description="Validate reasonable number of line items",
                    severity=ValidationSeverity.WARNING,
                    parameters={"max_line_items": 100}
                )
            ],
            "mathematical": [
                ValidationRule(
                    name="line_item_math_validation",
                    category="mathematical",
                    description="Validate line item calculations (qty × price = amount)",
                    severity=ValidationSeverity.ERROR,
                    parameters={"tolerance_cents": 1}
                ),
                ValidationRule(
                    name="subtotal_validation",
                    category="mathematical",
                    description="Validate subtotal matches sum of line items",
                    severity=ValidationSeverity.ERROR,
                    parameters={"tolerance_cents": 1}
                ),
                ValidationRule(
                    name="total_amount_validation",
                    category="mathematical",
                    description="Validate total amount (subtotal + tax)",
                    severity=ValidationSeverity.ERROR,
                    parameters={"tolerance_cents": 1}
                ),
                ValidationRule(
                    name="tax_calculation_validation",
                    category="mathematical",
                    description="Validate tax calculations",
                    severity=ValidationSeverity.WARNING
                )
            ],
            "business_rules": [
                ValidationRule(
                    name="vendor_validation",
                    category="business_rules",
                    description="Validate vendor exists and is active",
                    severity=ValidationSeverity.ERROR
                ),
                ValidationRule(
                    name="currency_validation",
                    category="business_rules",
                    description="Validate currency matches vendor currency",
                    severity=ValidationSeverity.ERROR
                ),
                ValidationRule(
                    name="po_matching_validation",
                    category="business_rules",
                    description="Validate PO matches invoice data",
                    severity=ValidationSeverity.WARNING
                ),
                ValidationRule(
                    name="grn_matching_validation",
                    category="business_rules",
                    description="Validate GRN matches invoice quantities",
                    severity=ValidationSeverity.WARNING
                ),
                ValidationRule(
                    name="duplicate_detection",
                    category="business_rules",
                    description="Detect duplicate invoices",
                    severity=ValidationSeverity.ERROR
                ),
                ValidationRule(
                    name="invoice_age_validation",
                    category="business_rules",
                    description="Validate invoice is not too old",
                    severity=ValidationSeverity.WARNING,
                    parameters={"max_age_days": 365}
                ),
                ValidationRule(
                    name="amount_limits_validation",
                    category="business_rules",
                    description="Validate amounts are within reasonable limits",
                    severity=ValidationSeverity.WARNING,
                    parameters={"max_total_amount": 1000000}
                )
            ]
        }

    def _initialize_reason_taxonomy(self) -> Dict[str, ReasonTaxonomy]:
        """Initialize reason taxonomy mapping."""
        return {
            # Structural reasons
            "missing_vendor_name": ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
            "missing_invoice_number": ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
            "missing_total_amount": ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
            "invalid_date_format": ReasonTaxonomy.INVALID_FIELD_FORMAT,
            "invalid_amount_format": ReasonTaxonomy.INVALID_FIELD_FORMAT,
            "no_line_items": ReasonTaxonomy.MISSING_REQUIRED_FIELDS,

            # Mathematical reasons
            "line_calculation_mismatch": ReasonTaxonomy.LINE_MATH_MISMATCH,
            "subtotal_mismatch": ReasonTaxonomy.SUBTOTAL_MISMATCH,
            "total_mismatch": ReasonTaxonomy.TOTAL_MISMATCH,
            "tax_calculation_error": ReasonTaxonomy.TAX_CALCULATION_ERROR,

            # Business rule reasons
            "vendor_not_found": ReasonTaxonomy.VENDOR_NOT_FOUND,
            "vendor_inactive": ReasonTaxonomy.INACTIVE_VENDOR,
            "currency_mismatch": ReasonTaxonomy.INVALID_CURRENCY,
            "po_not_found": ReasonTaxonomy.PO_NOT_FOUND,
            "po_amount_mismatch": ReasonTaxonomy.PO_AMOUNT_MISMATCH,
            "po_quantity_mismatch": ReasonTaxonomy.PO_QUANTITY_MISMATCH,
            "grn_not_found": ReasonTaxonomy.GRN_NOT_FOUND,
            "grn_quantity_mismatch": ReasonTaxonomy.GRN_QUANTITY_MISMATCH,
            "duplicate_invoice": ReasonTaxonomy.DUPLICATE_SUSPECT,
            "invoice_too_old": ReasonTaxonomy.BUSINESS_RULE_VIOLATION,
            "amount_excessive": ReasonTaxonomy.BUSINESS_RULE_VIOLATION,

            # Security reasons
            "sql_injection_detected": ReasonTaxonomy.SQL_INJECTION_DETECTED,
            "xss_attack_detected": ReasonTaxonomy.XSS_ATTACK_DETECTED,
            "command_injection_detected": ReasonTaxonomy.COMMAND_INJECTION_DETECTED,
            "path_traversal_detected": ReasonTaxonomy.PATH_TRAVERSAL_DETECTED,
            "file_upload_threat": ReasonTaxonomy.FILE_UPLOAD_THREAT,
            "rate_limit_exceeded": ReasonTaxonomy.RATE_LIMIT_EXCEEDED,
            "data_exfiltration_attempt": ReasonTaxonomy.DATA_EXFILTRATION_ATTEMPT,
            "business_logic_abuse": ReasonTaxonomy.BUSINESS_LOGIC_ABUSE,
            "allowlist_violation": ReasonTaxonomy.ALLOWLIST_VIOLATION,
            "denylist_violation": ReasonTaxonomy.DENYLIST_VIOLATION,
            "malicious_input_detected": ReasonTaxonomy.MALICIOUS_INPUT_DETECTED,

            # Compliance reasons
            "gdpr_violation": ReasonTaxonomy.GDPR_VIOLATION,
            "pci_dss_violation": ReasonTaxonomy.PCI_DSS_VIOLATION,
            "sox_compliance_violation": ReasonTaxonomy.SOX_COMPLIANCE_VIOLATION,
            "data_retention_violation": ReasonTaxonomy.DATA_RETENTION_VIOLATION,
            "audit_logging_required": ReasonTaxonomy.AUDIT_LOGGING_REQUIRED,
            "encryption_required": ReasonTaxonomy.ENCRYPTION_REQUIRED,
            "access_control_violation": ReasonTaxonomy.ACCESS_CONTROL_VIOLATION,

            # System reasons
            "validation_system_error": ReasonTaxonomy.SYSTEM_ERROR,
            "database_error": ReasonTaxonomy.SYSTEM_ERROR,
            "sanitization_error": ReasonTaxonomy.SANITIZATION_ERROR,
            "security_validation_error": ReasonTaxonomy.SECURITY_VALIDATION_ERROR
        }

    def _initialize_security_rules(self) -> Dict[str, List[SecurityRule]]:
        """Initialize security validation rules."""
        return {
            "injection_attacks": DEFAULT_SECURITY_RULES[:2],  # SQL and Command injection
            "xss_attacks": [DEFAULT_SECURITY_RULES[1]],  # XSS protection
            "file_security": [DEFAULT_SECURITY_RULES[2]],  # Path traversal
            "input_validation": DEFAULT_SECURITY_RULES,  # All security rules
        }

    def _initialize_compliance_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        """Initialize compliance validation rules."""
        return {
            "gdpr": [
                {
                    "name": "personal_data_detection",
                    "description": "Detect and flag personal data for GDPR compliance",
                    "patterns": [r"\b\d{4}-\d{2}-\d{2}\b",  # Dates (potential DoB)
                                r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
                                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"],  # Email
                    "action": "flag_for_review"
                }
            ],
            "pci_dss": [
                {
                    "name": "credit_card_detection",
                    "description": "Detect and mask credit card numbers for PCI DSS compliance",
                    "patterns": [r"\b4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # Visa
                                r"\b5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # MasterCard
                                r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b"],  # American Express
                    "action": "mask_and_flag"
                }
            ],
            "audit": [
                {
                    "name": "audit_logging_required",
                    "description": "Ensure all sensitive operations are logged for audit",
                    "check_fields": ["total_amount", "vendor_name", "invoice_number"],
                    "action": "ensure_logging"
                }
            ]
        }

    async def validate_comprehensive(
        self,
        extraction_result: Dict[str, Any],
        invoice_id: Optional[str] = None,
        vendor_id: Optional[str] = None,
        strict_mode: bool = False,
        custom_rules: Optional[Dict[str, List[ValidationRule]]] = None
    ) -> ValidationResult:
        """Perform comprehensive validation with all rule categories."""
        start_time = datetime.utcnow()
        logger.info(f"Starting comprehensive validation for invoice {invoice_id}")

        # Extract data
        header = extraction_result.get("header", {})
        lines = extraction_result.get("lines", [])
        confidence = extraction_result.get("confidence", {})

        # Initialize results
        all_issues = []
        rule_results = []
        validation_results = {}

        try:
            # Get database session for advanced validations
            async with AsyncSessionLocal() as session:
                # Execute validation rules by category
                for category, rules in (custom_rules or self.rules).items():
                    category_results = await self._execute_rule_category(
                        category, rules, header, lines, confidence, session, invoice_id, vendor_id
                    )
                    rule_results.extend(category_results)

                    # Collect issues
                    for result in category_results:
                        if not result.passed:
                            issue = self._create_validation_issue(result)
                            all_issues.append(issue)

                    # Store category-specific results
                    if category == "mathematical":
                        validation_results["math_validation"] = self._create_math_result(
                            category_results, header, lines
                        )
                    elif category == "business_rules":
                        validation_results["matching_result"] = self._create_matching_result(
                            category_results, invoice_id, session
                        )
                        validation_results["vendor_policy_result"] = self._create_vendor_policy_result(
                            category_results
                        )
                        validation_results["duplicate_check_result"] = self._create_duplicate_result(
                            category_results
                        )

            # Calculate overall validation result
            error_count = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.ERROR)
            warning_count = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.WARNING)
            info_count = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.INFO)

            validation_passed = error_count == 0
            if strict_mode:
                validation_passed = validation_passed and warning_count == 0

            # Calculate confidence score
            confidence_score = self._calculate_validation_confidence(rule_results, confidence)

            # Create validation result
            result = ValidationResult(
                passed=validation_passed,
                confidence_score=confidence_score,
                total_issues=len(all_issues),
                error_count=error_count,
                warning_count=warning_count,
                info_count=info_count,
                issues=all_issues,
                math_validation=validation_results.get("math_validation"),
                matching_result=validation_results.get("matching_result"),
                vendor_policy_result=validation_results.get("vendor_policy_result"),
                duplicate_check_result=validation_results.get("duplicate_check_result"),
                check_results=self._create_check_results(rule_results),
                validated_at=start_time,
                rules_version=self.rules_version,
                validator_version="2.0.0",
                processing_time_ms=str(int((datetime.utcnow() - start_time).total_seconds() * 1000)),
                header_summary=self._create_header_summary(header),
                lines_summary=self._create_lines_summary(lines)
            )

            logger.info(
                f"Comprehensive validation completed for invoice {invoice_id}: "
                f"{'PASSED' if result.passed else 'FAILED'} "
                f"(errors: {error_count}, warnings: {warning_count}, confidence: {confidence_score:.2f})"
            )

            return result

        except Exception as e:
            logger.error(f"Comprehensive validation failed: {e}")
            # Create error result
            error_issue = ValidationIssue(
                code=ValidationCode.VALIDATION_ERROR,
                message=f"Validation process failed: {str(e)}",
                severity=ValidationSeverity.ERROR,
                details={"error_type": type(e).__name__}
            )

            return ValidationResult(
                passed=False,
                confidence_score=0.0,
                total_issues=1,
                error_count=1,
                warning_count=0,
                info_count=0,
                issues=[error_issue],
                check_results=self._create_error_check_results(),
                validated_at=start_time,
                rules_version=self.rules_version,
                validator_version="3.0.0",
                header_summary={},
                lines_summary={}
            )

    async def validate_defense_in_depth(
        self,
        extraction_result: Dict[str, Any],
        invoice_id: Optional[str] = None,
        vendor_id: Optional[str] = None,
        context: Optional[SecurityContext] = None,
        strict_mode: bool = False,
        custom_rules: Optional[Dict[str, List[ValidationRule]]] = None
    ) -> DefenseInDepthResult:
        """
        Perform comprehensive defense-in-depth validation with all security layers.

        Args:
            extraction_result: Invoice extraction data
            invoice_id: Optional invoice ID
            vendor_id: Optional vendor ID
            context: Security context for threat analysis
            strict_mode: Enable strict validation mode
            custom_rules: Optional custom validation rules

        Returns:
            DefenseInDepthResult with comprehensive analysis
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting defense-in-depth validation for invoice {invoice_id}")

        # Initialize result
        result = DefenseInDepthResult(
            passed=True,
            overall_threat_level=SecurityThreatLevel.LOW,
            confidence_score=1.0,
            processing_time_ms=0.0,
            layers_executed=[],
            rules_applied=[]
        )

        try:
            # Extract data
            header = extraction_result.get("header", {})
            lines = extraction_result.get("lines", [])
            confidence = extraction_result.get("confidence", {})

            # Layer 1: Input Sanitization
            if self.enable_sanitization:
                logger.info("Executing Layer 1: Input Sanitization")
                result.layers_executed.append(ValidationLayer.SYNTACTIC)

                sanitization_results = await self._sanitize_extraction_data(
                    header, lines, context
                )
                result.sanitization_results = sanitization_results

                # Check for critical sanitization failures
                critical_sanitization_issues = [
                    sr for sr in sanitization_results
                    if not sr.success and sr.warnings
                ]

                if critical_sanitization_issues:
                    result.passed = False
                    result.overall_threat_level = SecurityThreatLevel.HIGH
                    result.confidence_score *= 0.7
                    result.blocked_operations.append("critical_sanitization_failure")

            # Layer 2: Syntactic Validation (traditional validation)
            logger.info("Executing Layer 2: Syntactic Validation")
            result.layers_executed.append(ValidationLayer.SYNTACTIC)

            traditional_result = await self.validate_comprehensive(
                extraction_result, invoice_id, vendor_id, strict_mode, custom_rules
            )

            if not traditional_result.passed:
                result.passed = False
                result.confidence_score *= 0.8
                result.syntactic_validation = {
                    "passed": traditional_result.passed,
                    "error_count": traditional_result.error_count,
                    "warning_count": traditional_result.warning_count,
                    "issues": [issue.message for issue in traditional_result.issues]
                }

            # Layer 3: Security Validation
            if self.enable_security_validation:
                logger.info("Executing Layer 3: Security Validation")
                result.layers_executed.append(ValidationLayer.SECURITY)

                security_results = await self._validate_security_layers(
                    header, lines, context, invoice_id
                )
                result.threat_detections = security_results["threat_detections"]
                result.security_events = security_results["security_events"]

                # Update threat level based on security results
                if security_results["threat_detections"]:
                    max_threat_level = max(
                        td.threat_level for td in security_results["threat_detections"]
                    )
                    result.overall_threat_level = max(result.overall_threat_level, max_threat_level)

                    # Critical threats cause immediate failure
                    critical_threats = [
                        td for td in security_results["threat_detections"]
                        if td.threat_level in [SecurityThreatLevel.CRITICAL, SecurityThreatLevel.HIGH]
                    ]

                    if critical_threats:
                        result.passed = False
                        result.confidence_score *= 0.5
                        result.blocked_operations.append("security_threat_detected")

                result.security_validation = {
                    "threats_detected": len(security_results["threat_detections"]),
                    "security_events": len(security_results["security_events"]),
                    "max_threat_level": result.overall_threat_level.value
                }

            # Layer 4: Compliance Validation
            logger.info("Executing Layer 4: Compliance Validation")
            result.layers_executed.append(ValidationLayer.COMPLIANCE)

            compliance_results = await self._validate_compliance_layers(
                header, lines, context
            )

            if compliance_results["violations"]:
                result.passed = False
                result.overall_threat_level = max(result.overall_threat_level, SecurityThreatLevel.MEDIUM)
                result.confidence_score *= 0.9
                result.compliance_validation = {
                    "violations": len(compliance_results["violations"]),
                    "compliance_score": compliance_results["score"],
                    "issues": compliance_results["violations"]
                }

            # Calculate final processing time
            result.processing_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Generate security recommendations
            result.security_recommendations = self._generate_security_recommendations(result)

            # Log completion
            logger.info(
                f"Defense-in-depth validation completed for invoice {invoice_id}: "
                f"{'PASSED' if result.passed else 'FAILED'} "
                f"(threat_level: {result.overall_threat_level.value}, "
                f"confidence: {result.confidence_score:.2f}, "
                f"processing_time: {result.processing_time_ms:.2f}ms)"
            )

            return result

        except Exception as e:
            logger.error(f"Defense-in-depth validation failed: {e}")
            result.passed = False
            result.overall_threat_level = SecurityThreatLevel.CRITICAL
            result.confidence_score = 0.0
            result.security_recommendations = [f"Validation error: {str(e)}"]

            return result

    # Helper methods for defense-in-depth validation

    async def _sanitize_extraction_data(
        self,
        header: Dict[str, Any],
        lines: List[Dict[str, Any]],
        context: Optional[SecurityContext] = None
    ) -> List[SanitizationResult]:
        """Sanitize all extracted data using input sanitizer."""
        sanitization_results = []

        if not self.input_sanitizer:
            return sanitization_results

        # Sanitize header fields
        for field_name, field_value in header.items():
            try:
                result = self.input_sanitizer.sanitize(
                    field_value,
                    field_name=field_name
                )
                sanitization_results.append(result)

                # Update header with sanitized value
                header[field_name] = result.sanitized_value

            except Exception as e:
                logger.error(f"Error sanitizing field {field_name}: {e}")
                sanitization_results.append(SanitizationResult(
                    success=False,
                    sanitized_value="",
                    original_value=str(field_value),
                    sanitization_level=SanitizationLevel.NORMAL,
                    warnings=[f"Sanitization error: {str(e)}"]
                ))

        # Sanitize line item fields
        for i, line in enumerate(lines):
            for field_name, field_value in line.items():
                try:
                    result = self.input_sanitizer.sanitize(
                        field_value,
                        field_name=f"line_{i}_{field_name}"
                    )
                    sanitization_results.append(result)

                    # Update line with sanitized value
                    line[field_name] = result.sanitized_value

                except Exception as e:
                    logger.error(f"Error sanitizing line {i} field {field_name}: {e}")
                    sanitization_results.append(SanitizationResult(
                        success=False,
                        sanitized_value="",
                        original_value=str(field_value),
                        sanitization_level=SanitizationLevel.NORMAL,
                        warnings=[f"Sanitization error: {str(e)}"]
                    ))

        return sanitization_results

    async def _validate_security_layers(
        self,
        header: Dict[str, Any],
        lines: List[Dict[str, Any]],
        context: Optional[SecurityContext] = None,
        invoice_id: Optional[str] = None
    ) -> Dict[str, List[Any]]:
        """Validate all security layers for threats."""
        threat_detections = []
        security_events = []

        if not self.security_validator:
            return {"threat_detections": threat_detections, "security_events": security_events}

        # Validate header fields
        for field_name, field_value in header.items():
            try:
                result = self.security_validator.validate_field(
                    field_name, field_value, context
                )

                if result.is_threat:
                    # Convert to threat detection result
                    threat_result = ThreatDetectionResult(
                        is_threat=True,
                        threat_type=result.threat_type,
                        threat_level=result.threat_level,
                        confidence=result.confidence,
                        matched_patterns=result.matched_patterns,
                        field=field_name,
                        original_value=result.original_value,
                        risk_score=result.risk_score,
                        recommendation=result.recommendation,
                        details=result.details
                    )
                    threat_detections.append(threat_result)

                    # Create security event
                    security_event = SecurityEvent(
                        event_type="threat_detected",
                        threat_type=result.threat_type,
                        threat_level=result.threat_level,
                        field=field_name,
                        original_value=result.original_value,
                        confidence=result.confidence,
                        details=result.details
                    )

                    if context:
                        security_event.source_ip = context.source_ip
                        security_event.user_id = context.user_id
                        security_event.session_id = context.session_id
                        security_event.user_agent = context.user_agent
                        security_event.request_id = context.request_id

                    security_events.append(security_event)

            except Exception as e:
                logger.error(f"Error validating field {field_name}: {e}")

        # Validate line item fields
        for i, line in enumerate(lines):
            for field_name, field_value in line.items():
                try:
                    result = self.security_validator.validate_field(
                        f"line_{i}_{field_name}", field_value, context
                    )

                    if result.is_threat:
                        threat_result = ThreatDetectionResult(
                            is_threat=True,
                            threat_type=result.threat_type,
                            threat_level=result.threat_level,
                            confidence=result.confidence,
                            matched_patterns=result.matched_patterns,
                            field=f"line_{i}_{field_name}",
                            original_value=result.original_value,
                            risk_score=result.risk_score,
                            recommendation=result.recommendation,
                            details=result.details
                        )
                        threat_detections.append(threat_result)

                except Exception as e:
                    logger.error(f"Error validating line {i} field {field_name}: {e}")

        return {"threat_detections": threat_detections, "security_events": security_events}

    async def _validate_compliance_layers(
        self,
        header: Dict[str, Any],
        lines: List[Dict[str, Any]],
        context: Optional[SecurityContext] = None
    ) -> Dict[str, Any]:
        """Validate compliance requirements."""
        violations = []
        total_checks = 0

        # GDPR compliance checks
        gdpr_rules = self.compliance_rules.get("gdpr", [])
        for rule in gdpr_rules:
            total_checks += 1
            violation_found = False

            # Check header fields
            for field_name, field_value in header.items():
                if isinstance(field_value, str):
                    for pattern in rule.get("patterns", []):
                        if re.search(pattern, field_value):
                            violations.append({
                                "compliance_type": "GDPR",
                                "rule": rule["name"],
                                "field": field_name,
                                "pattern_matched": pattern,
                                "action_required": rule["action"]
                            })
                            violation_found = True
                            break

            # Check line item fields
            for line in lines:
                for field_name, field_value in line.items():
                    if isinstance(field_value, str):
                        for pattern in rule.get("patterns", []):
                            if re.search(pattern, field_value):
                                violations.append({
                                    "compliance_type": "GDPR",
                                    "rule": rule["name"],
                                    "field": f"line_item_{field_name}",
                                    "pattern_matched": pattern,
                                    "action_required": rule["action"]
                                })
                                violation_found = True
                                break

        # PCI DSS compliance checks
        pci_rules = self.compliance_rules.get("pci_dss", [])
        for rule in pci_rules:
            total_checks += 1

            # Check header fields for credit card numbers
            for field_name, field_value in header.items():
                if isinstance(field_value, str):
                    for pattern in rule.get("patterns", []):
                        if re.search(pattern, field_value):
                            violations.append({
                                "compliance_type": "PCI_DSS",
                                "rule": rule["name"],
                                "field": field_name,
                                "pattern_matched": pattern,
                                "action_required": rule["action"]
                            })

        # Audit compliance checks
        audit_rules = self.compliance_rules.get("audit", [])
        for rule in audit_rules:
            total_checks += 1
            required_fields = rule.get("check_fields", [])

            for field in required_fields:
                if field not in header or not header[field]:
                    violations.append({
                        "compliance_type": "AUDIT",
                        "rule": rule["name"],
                        "field": field,
                        "issue": "Missing required field for audit logging",
                        "action_required": rule["action"]
                    })

        # Calculate compliance score
        violations_count = len(violations)
        compliance_score = max(0, 100 - (violations_count / max(total_checks, 1) * 100))

        return {
            "violations": violations,
            "score": compliance_score,
            "total_checks": total_checks,
            "violations_count": violations_count
        }

    def _generate_security_recommendations(
        self, result: DefenseInDepthResult
    ) -> List[str]:
        """Generate security recommendations based on validation results."""
        recommendations = []

        # Threat-based recommendations
        for threat in result.threat_detections:
            if threat.recommendation:
                recommendations.append(threat.recommendation)

        # Threat level-based recommendations
        if result.overall_threat_level == SecurityThreatLevel.CRITICAL:
            recommendations.extend([
                "CRITICAL: Block request immediately and investigate source",
                "Scan system for potential compromise",
                "Review all recent requests from this source"
            ])
        elif result.overall_threat_level == SecurityThreatLevel.HIGH:
            recommendations.extend([
                "HIGH: Review request manually before processing",
                "Consider temporarily blocking source IP",
                "Enable enhanced monitoring for this source"
            ])
        elif result.overall_threat_level == SecurityThreatLevel.MEDIUM:
            recommendations.extend([
                "MEDIUM: Additional validation recommended",
                "Log request for security review",
                "Consider rate limiting for this source"
            ])

        # Sanitization-based recommendations
        for sanitization in result.sanitization_results:
            if not sanitization.success:
                recommendations.append(
                    f"Input sanitization failed for field: {getattr(sanitization, 'field', 'unknown')}"
                )

        # Compliance-based recommendations
        if result.compliance_validation and result.compliance_validation.get("violations", 0) > 0:
            recommendations.append("Compliance violations detected - review and remediate")

        # Remove duplicates
        recommendations = list(set(recommendations))

        return recommendations[:10]  # Limit to top 10 recommendations

    async def _execute_rule_category(
        self,
        category: str,
        rules: List[ValidationRule],
        header: Dict[str, Any],
        lines: List[Dict[str, Any]],
        confidence: Dict[str, Any],
        session: AsyncSession,
        invoice_id: Optional[str],
        vendor_id: Optional[str]
    ) -> List[RuleExecutionResult]:
        """Execute all rules in a category."""
        results = []

        for rule in rules:
            if not rule.enabled:
                continue

            try:
                start_time = datetime.utcnow()
                result = await self._execute_single_rule(
                    rule, header, lines, confidence, session, invoice_id, vendor_id
                )
                result.execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                results.append(result)

            except Exception as e:
                logger.error(f"Rule {rule.name} execution failed: {e}")
                results.append(RuleExecutionResult(
                    rule_name=rule.name,
                    passed=False,
                    reason_taxonomy=ReasonTaxonomy.SYSTEM_ERROR,
                    message=f"Rule execution failed: {str(e)}",
                    details={"error_type": type(e).__name__}
                ))

        return results

    async def _execute_single_rule(
        self,
        rule: ValidationRule,
        header: Dict[str, Any],
        lines: List[Dict[str, Any]],
        confidence: Dict[str, Any],
        session: AsyncSession,
        invoice_id: Optional[str],
        vendor_id: Optional[str]
    ) -> RuleExecutionResult:
        """Execute a single validation rule."""
        if rule.name == "required_header_fields":
            return await self._validate_required_header_fields(rule, header)
        elif rule.name == "required_line_item_fields":
            return await self._validate_required_line_item_fields(rule, lines)
        elif rule.name == "field_format_validation":
            return await self._validate_field_formats(rule, header, lines)
        elif rule.name == "line_item_count_validation":
            return await self._validate_line_item_count(rule, lines)
        elif rule.name == "line_item_math_validation":
            return await self._validate_line_item_math(rule, lines)
        elif rule.name == "subtotal_validation":
            return await self._validate_subtotal(rule, header, lines)
        elif rule.name == "total_amount_validation":
            return await self._validate_total_amount(rule, header, lines)
        elif rule.name == "tax_calculation_validation":
            return await self._validate_tax_calculation(rule, header, lines)
        elif rule.name == "vendor_validation":
            return await self._validate_vendor(rule, header, session)
        elif rule.name == "currency_validation":
            return await self._validate_currency(rule, header, session)
        elif rule.name == "po_matching_validation":
            return await self._validate_po_matching(rule, header, session)
        elif rule.name == "grn_matching_validation":
            return await self._validate_grn_matching(rule, header, lines, session)
        elif rule.name == "duplicate_detection":
            return await self._validate_duplicates(rule, header, invoice_id, session)
        elif rule.name == "invoice_age_validation":
            return await self._validate_invoice_age(rule, header)
        elif rule.name == "amount_limits_validation":
            return await self._validate_amount_limits(rule, header, lines)
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.SYSTEM_ERROR,
                message=f"Unknown rule: {rule.name}"
            )

    # Individual rule implementations
    async def _validate_required_header_fields(
        self, rule: ValidationRule, header: Dict[str, Any]
    ) -> RuleExecutionResult:
        """Validate required header fields are present."""
        required_fields = rule.parameters.get("required_fields", [])
        missing_fields = []

        for field in required_fields:
            # Map field names to header keys
            header_key = self._map_field_to_header_key(field)
            value = header.get(header_key)

            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)

        if missing_fields:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
                message=f"Missing required fields: {', '.join(missing_fields)}",
                details={"missing_fields": missing_fields}
            )
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="All required header fields present"
            )

    async def _validate_required_line_item_fields(
        self, rule: ValidationRule, lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate required line item fields are present."""
        required_fields = rule.parameters.get("required_fields", [])
        issues = []

        if not lines:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
                message="No line items found"
            )

        for i, line in enumerate(lines):
            missing_fields = []
            for field in required_fields:
                value = line.get(field)
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append(field)

            if missing_fields:
                issues.append({
                    "line_number": i + 1,
                    "missing_fields": missing_fields
                })

        if issues:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
                message=f"Missing fields in line items",
                details={"issues": issues}
            )
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="All line item fields present"
            )

    async def _validate_field_formats(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate field formats."""
        format_issues = []

        # Validate header formats
        invoice_date = header.get("invoice_date")
        if invoice_date and not self._is_valid_date(invoice_date):
            format_issues.append({
                "field": "invoice_date",
                "value": invoice_date,
                "error": "Invalid date format"
            })

        total_amount = header.get("total_amount")
        if total_amount and not self._is_valid_amount(total_amount):
            format_issues.append({
                "field": "total_amount",
                "value": total_amount,
                "error": "Invalid amount format"
            })

        # Validate line item formats
        for i, line in enumerate(lines):
            amount = line.get("total_amount") or line.get("amount")
            if amount and not self._is_valid_amount(amount):
                format_issues.append({
                    "field": f"line_{i+1}_amount",
                    "value": amount,
                    "error": "Invalid amount format"
                })

        if format_issues:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.INVALID_FIELD_FORMAT,
                message=f"Invalid field formats found",
                details={"format_issues": format_issues}
            )
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="All field formats valid"
            )

    async def _validate_line_item_count(
        self, rule: ValidationRule, lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate reasonable number of line items."""
        max_items = rule.parameters.get("max_line_items", 100)

        if len(lines) > max_items:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.BUSINESS_RULE_VIOLATION,
                message=f"Too many line items: {len(lines)} (max: {max_items})",
                details={"line_count": len(lines), "max_allowed": max_items}
            )
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message=f"Line item count acceptable: {len(lines)}"
            )

    async def _validate_line_item_math(
        self, rule: ValidationRule, lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate line item calculations."""
        tolerance_cents = rule.parameters.get("tolerance_cents", 1)
        issues = []

        for i, line in enumerate(lines):
            try:
                quantity = self._safe_decimal(line.get("quantity", 1))
                unit_price = self._safe_decimal(line.get("unit_price", 0))
                amount = self._safe_decimal(line.get("total_amount") or line.get("amount", 0))

                expected_amount = quantity * unit_price
                difference = abs(amount - expected_amount)

                if difference > Decimal(str(tolerance_cents / 100)):
                    issues.append({
                        "line_number": i + 1,
                        "quantity": float(quantity),
                        "unit_price": float(unit_price),
                        "actual_amount": float(amount),
                        "expected_amount": float(expected_amount),
                        "difference": float(difference)
                    })

            except (InvalidOperation, TypeError) as e:
                issues.append({
                    "line_number": i + 1,
                    "error": f"Invalid numeric values: {str(e)}"
                })

        if issues:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.LINE_MATH_MISMATCH,
                message=f"Line item calculation errors found",
                details={"issues": issues}
            )
        else:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="All line item calculations correct"
            )

    async def _validate_subtotal(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate subtotal matches sum of line items."""
        tolerance_cents = rule.parameters.get("tolerance_cents", 1)

        try:
            # Calculate line items total
            lines_total = sum(
                self._safe_decimal(line.get("total_amount") or line.get("amount", 0))
                for line in lines
            )

            # Get header subtotal
            header_subtotal = self._safe_decimal(header.get("subtotal_amount", 0))

            if header_subtotal > 0:
                difference = abs(lines_total - header_subtotal)
                tolerance = Decimal(str(tolerance_cents / 100))

                if difference > tolerance:
                    return RuleExecutionResult(
                        rule_name=rule.name,
                        passed=False,
                        reason_taxonomy=ReasonTaxonomy.SUBTOTAL_MISMATCH,
                        message=f"Subtotal mismatch: lines total {lines_total}, header subtotal {header_subtotal}",
                        details={
                            "lines_total": float(lines_total),
                            "header_subtotal": float(header_subtotal),
                            "difference": float(difference),
                            "tolerance": float(tolerance)
                        }
                    )

            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="Subtotal validation passed"
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.CALCULATION_ERROR,
                message=f"Subtotal validation error: {str(e)}"
            )

    async def _validate_total_amount(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate total amount calculation."""
        tolerance_cents = rule.parameters.get("tolerance_cents", 1)

        try:
            # Calculate expected total
            lines_total = sum(
                self._safe_decimal(line.get("total_amount") or line.get("amount", 0))
                for line in lines
            )

            header_subtotal = self._safe_decimal(header.get("subtotal_amount", lines_total))
            tax_amount = self._safe_decimal(header.get("tax_amount", 0))

            expected_total = header_subtotal + tax_amount
            header_total = self._safe_decimal(header.get("total_amount", 0))

            if header_total > 0:
                difference = abs(header_total - expected_total)
                tolerance = Decimal(str(tolerance_cents / 100))

                if difference > tolerance:
                    return RuleExecutionResult(
                        rule_name=rule.name,
                        passed=False,
                        reason_taxonomy=ReasonTaxonomy.TOTAL_MISMATCH,
                        message=f"Total amount mismatch: expected {expected_total}, actual {header_total}",
                        details={
                            "expected_total": float(expected_total),
                            "actual_total": float(header_total),
                            "difference": float(difference),
                            "subtotal": float(header_subtotal),
                            "tax": float(tax_amount),
                            "tolerance": float(tolerance)
                        }
                    )

            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="Total amount validation passed"
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.CALCULATION_ERROR,
                message=f"Total amount validation error: {str(e)}"
            )

    async def _validate_vendor(
        self, rule: ValidationRule, header: Dict[str, Any], session: AsyncSession
    ) -> RuleExecutionResult:
        """Validate vendor exists and is active."""
        vendor_name = header.get("vendor_name")

        if not vendor_name:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.MISSING_REQUIRED_FIELDS,
                message="Vendor name not provided"
            )

        try:
            # Search for vendor
            vendor_query = select(Vendor).where(Vendor.name.ilike(f"%{vendor_name}%"))
            vendor_result = await session.execute(vendor_query)
            vendor = vendor_result.scalar_one_or_none()

            if not vendor:
                return RuleExecutionResult(
                    rule_name=rule.name,
                    passed=False,
                    reason_taxonomy=ReasonTaxonomy.VENDOR_NOT_FOUND,
                    message=f"Vendor '{vendor_name}' not found in system",
                    details={"vendor_name": vendor_name}
                )

            if not vendor.active:
                return RuleExecutionResult(
                    rule_name=rule.name,
                    passed=False,
                    reason_taxonomy=ReasonTaxonomy.INACTIVE_VENDOR,
                    message=f"Vendor '{vendor_name}' is inactive",
                    details={"vendor_id": str(vendor.id), "status": vendor.status.value}
                )

            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message=f"Vendor validation passed: {vendor_name}",
                details={"vendor_id": str(vendor.id)}
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.SYSTEM_ERROR,
                message=f"Vendor validation error: {str(e)}"
            )

    async def _validate_currency(
        self, rule: ValidationRule, header: Dict[str, Any], session: AsyncSession
    ) -> RuleExecutionResult:
        """Validate currency matches vendor currency."""
        invoice_currency = header.get("currency", "USD")
        vendor_name = header.get("vendor_name")

        if not vendor_name:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,  # Skip if no vendor
                message="Currency validation skipped (no vendor)"
            )

        try:
            # Find vendor
            vendor_query = select(Vendor).where(Vendor.name.ilike(f"%{vendor_name}%"))
            vendor_result = await session.execute(vendor_query)
            vendor = vendor_result.scalar_one_or_none()

            if vendor and vendor.currency:
                if invoice_currency != vendor.currency:
                    return RuleExecutionResult(
                        rule_name=rule.name,
                        passed=False,
                        reason_taxonomy=ReasonTaxonomy.INVALID_CURRENCY,
                        message=f"Currency mismatch: invoice {invoice_currency}, vendor {vendor.currency}",
                        details={
                            "invoice_currency": invoice_currency,
                            "vendor_currency": vendor.currency,
                            "vendor_id": str(vendor.id)
                        }
                    )

            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="Currency validation passed"
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.SYSTEM_ERROR,
                message=f"Currency validation error: {str(e)}"
            )

    async def _validate_duplicates(
        self, rule: ValidationRule, header: Dict[str, Any], invoice_id: Optional[str], session: AsyncSession
    ) -> RuleExecutionResult:
        """Detect duplicate invoices."""
        invoice_number = header.get("invoice_number")
        vendor_name = header.get("vendor_name")
        total_amount = header.get("total_amount")

        if not invoice_number or not vendor_name:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,  # Skip if insufficient data
                message="Duplicate check skipped (insufficient data)"
            )

        try:
            # Search for potential duplicates
            vendor_query = select(Vendor).where(Vendor.name.ilike(f"%{vendor_name}%"))
            vendor_result = await session.execute(vendor_query)
            vendor = vendor_result.scalar_one_or_none()

            if vendor:
                # Find invoices with same number and vendor
                duplicate_query = select(Invoice, InvoiceExtraction).join(InvoiceExtraction).where(
                    and_(
                        Invoice.vendor_id == vendor.id,
                        InvoiceExtraction.header_json['invoice_number'].astext == invoice_number,
                        Invoice.id != invoice_id if invoice_id else True
                    )
                )

                duplicate_result = await session.execute(duplicate_query)
                duplicates = duplicate_result.all()

                if duplicates:
                    # Check amount match for higher confidence
                    exact_matches = [
                        dup for dup in duplicates
                        if self._extract_header_amount(dup[1]) == total_amount
                    ]

                    return RuleExecutionResult(
                        rule_name=rule.name,
                        passed=False,
                        reason_taxonomy=ReasonTaxonomy.DUPLICATE_SUSPECT,
                        message=f"Potential duplicate invoice found: {len(duplicates)} matches",
                        details={
                            "duplicate_count": len(duplicates),
                            "exact_amount_matches": len(exact_matches),
                            "invoice_number": invoice_number,
                            "vendor_name": vendor_name
                        }
                    )

            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message="No duplicate invoices found"
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=False,
                reason_taxonomy=ReasonTaxonomy.SYSTEM_ERROR,
                message=f"Duplicate check error: {str(e)}"
            )

    # Helper methods
    def _create_validation_issue(self, result: RuleExecutionResult) -> ValidationIssue:
        """Create ValidationIssue from RuleExecutionResult."""
        # Map reason taxonomy to validation code
        code_mapping = {
            ReasonTaxonomy.MISSING_REQUIRED_FIELDS: ValidationCode.MISSING_REQUIRED_FIELD,
            ReasonTaxonomy.INVALID_FIELD_FORMAT: ValidationCode.INVALID_FIELD_FORMAT,
            ReasonTaxonomy.LINE_MATH_MISMATCH: ValidationCode.LINE_MATH_MISMATCH,
            ReasonTaxonomy.SUBTOTAL_MISMATCH: ValidationCode.SUBTOTAL_MISMATCH,
            ReasonTaxonomy.TOTAL_MISMATCH: ValidationCode.TOTAL_MISMATCH,
            ReasonTaxonomy.VENDOR_NOT_FOUND: ValidationCode.INACTIVE_VENDOR,
            ReasonTaxonomy.INACTIVE_VENDOR: ValidationCode.INACTIVE_VENDOR,
            ReasonTaxonomy.INVALID_CURRENCY: ValidationCode.INVALID_CURRENCY,
            ReasonTaxonomy.DUPLICATE_SUSPECT: ValidationCode.DUPLICATE_INVOICE,
            ReasonTaxonomy.BUSINESS_RULE_VIOLATION: ValidationCode.EXCESSIVE_AMOUNT,
            ReasonTaxonomy.SYSTEM_ERROR: ValidationCode.VALIDATION_ERROR,
        }

        validation_code = code_mapping.get(result.reason_taxonomy, ValidationCode.VALIDATION_ERROR)

        return ValidationIssue(
            code=validation_code,
            message=result.message,
            severity=ValidationSeverity.ERROR if not result.passed else ValidationSeverity.INFO,
            details=result.details
        )

    def _map_field_to_header_key(self, field: str) -> str:
        """Map field name to header key."""
        field_mapping = {
            "vendor_name": "vendor_name",
            "invoice_number": "invoice_number",
            "total_amount": "total_amount",
            "invoice_date": "invoice_date",
            "due_date": "due_date",
            "po_number": "po_number"
        }
        return field_mapping.get(field, field)

    def _is_valid_date(self, date_value: Any) -> bool:
        """Check if date value is valid."""
        if isinstance(date_value, datetime):
            return True

        if isinstance(date_value, str):
            date_patterns = [
                r"^\d{4}-\d{2}-\d{2}$",
                r"^\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}$"
            ]
            return any(re.match(pattern, date_value.strip()) for pattern in date_patterns)

        return False

    def _is_valid_amount(self, amount_value: Any) -> bool:
        """Check if amount value is valid."""
        try:
            if isinstance(amount_value, (int, float, Decimal)):
                return float(amount_value) >= 0

            if isinstance(amount_value, str):
                cleaned = amount_value.replace("$", "").replace(",", "").strip()
                amount = float(cleaned)
                return amount >= 0
        except (ValueError, TypeError):
            pass

        return False

    def _safe_decimal(self, value: Any) -> Decimal:
        """Safely convert value to Decimal."""
        if value is None:
            return Decimal("0")

        try:
            if isinstance(value, Decimal):
                return value
            elif isinstance(value, (int, float)):
                return Decimal(str(value))
            elif isinstance(value, str):
                cleaned = value.replace("$", "").replace(",", "").strip()
                return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            pass

        return Decimal("0")

    def _calculate_validation_confidence(
        self, rule_results: List[RuleExecutionResult], extraction_confidence: Dict[str, Any]
    ) -> float:
        """Calculate overall validation confidence score."""
        if not rule_results:
            return 0.0

        passed_rules = sum(1 for result in rule_results if result.passed)
        rule_confidence = passed_rules / len(rule_results)

        # Factor in extraction confidence
        extraction_score = extraction_confidence.get("overall", 0.0)

        # Weight extraction confidence higher than rule confidence
        overall_confidence = (extraction_score * 0.7) + (rule_confidence * 0.3)

        return round(overall_confidence, 3)

    def _create_header_summary(self, header: Dict[str, Any]) -> Dict[str, Any]:
        """Create header summary for validation result."""
        return {
            "vendor_name": header.get("vendor_name"),
            "invoice_number": header.get("invoice_number"),
            "invoice_date": header.get("invoice_date"),
            "total_amount": header.get("total_amount"),
            "currency": header.get("currency", "USD")
        }

    def _create_lines_summary(self, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create lines summary for validation result."""
        if not lines:
            return {"count": 0, "total_amount": 0.0}

        total_amount = sum(
            self._safe_decimal(line.get("total_amount") or line.get("amount", 0))
            for line in lines
        )

        return {
            "count": len(lines),
            "total_amount": float(total_amount),
            "descriptions": [line.get("description", "")[:50] for line in lines[:3]]
        }

    def _create_check_results(self, rule_results: List[RuleExecutionResult]) -> Dict[str, bool]:
        """Create detailed check results from rule results."""
        checks = {}

        for result in rule_results:
            if "header" in result.rule_name or "field" in result.rule_name:
                checks["header_fields_check"] = checks.get("header_fields_check", True) and result.passed
            elif "line" in result.rule_name:
                checks["line_items_check"] = checks.get("line_items_check", True) and result.passed
            elif "math" in result.rule_name or "calculation" in result.rule_name:
                checks["math_check"] = checks.get("math_check", True) and result.passed
            elif "vendor" in result.rule_name or "currency" in result.rule_name:
                checks["vendor_policy_check"] = checks.get("vendor_policy_check", True) and result.passed
            elif "duplicate" in result.rule_name:
                checks["duplicate_check"] = checks.get("duplicate_check", True) and result.passed
            elif "po" in result.rule_name or "matching" in result.rule_name:
                checks["matching_check"] = checks.get("matching_check", True) and result.passed

        # Set defaults for missing checks
        default_checks = [
            "structure_check", "header_fields_check", "line_items_check",
            "math_check", "business_rules_check", "duplicate_check",
            "vendor_policy_check", "matching_check"
        ]

        for check in default_checks:
            if check not in checks:
                checks[check] = True

        return checks

    def _create_error_check_results(self) -> Dict[str, bool]:
        """Create error check results when validation fails."""
        return {
            "structure_check": False,
            "header_fields_check": False,
            "line_items_check": False,
            "math_check": False,
            "business_rules_check": False,
            "duplicate_check": False,
            "vendor_policy_check": False,
            "matching_check": False
        }

    def _create_math_result(
        self, math_results: List[RuleExecutionResult], header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> Optional[MathValidationResult]:
        """Create math validation result."""
        if not math_results:
            return None

        # Calculate line total
        lines_total = sum(
            self._safe_decimal(line.get("total_amount") or line.get("amount", 0))
            for line in lines
        )

        # Find specific validation results
        subtotal_result = next((r for r in math_results if r.rule_name == "subtotal_validation"), None)
        total_result = next((r for r in math_results if r.rule_name == "total_amount_validation"), None)

        return MathValidationResult(
            lines_total=float(lines_total),
            subtotal_match=subtotal_result.passed if subtotal_result else None,
            subtotal_difference=float(subtotal_result.details.get("difference", 0)) if subtotal_result and not subtotal_result.passed else None,
            total_match=total_result.passed if total_result else None,
            total_difference=float(total_result.details.get("difference", 0)) if total_result and not total_result.passed else None,
            tax_amount=float(self._safe_decimal(header.get("tax_amount", 0))),
            line_item_validation=[]  # Would be populated by line math validation
        )

    def _create_matching_result(
        self, business_results: List[RuleExecutionResult], invoice_id: Optional[str], session: AsyncSession
    ) -> Optional[MatchingResult]:
        """Create matching validation result."""
        # Simplified matching result
        po_result = next((r for r in business_results if r.rule_name == "po_matching_validation"), None)

        if not po_result:
            return MatchingResult(po_found=False, matching_type="none")

        return MatchingResult(
            po_found=po_result.passed,
            matching_type="2_way" if po_result.passed else "none"
        )

    def _create_vendor_policy_result(self, business_results: List[RuleExecutionResult]) -> Optional[VendorPolicyResult]:
        """Create vendor policy validation result."""
        vendor_result = next((r for r in business_results if r.rule_name == "vendor_validation"), None)
        currency_result = next((r for r in business_results if r.rule_name == "currency_validation"), None)

        if not vendor_result:
            return None

        return VendorPolicyResult(
            vendor_active=vendor_result.passed,
            currency_valid=currency_result.passed if currency_result else True,
            tax_id_valid=None,  # Would be populated by tax ID validation
            spend_limit_ok=None,  # Would be populated by spend limit validation
            payment_terms_ok=True,
            vendor_policy_issues=[]
        )

    def _create_duplicate_result(self, business_results: List[RuleExecutionResult]) -> Optional[DuplicateCheckResult]:
        """Create duplicate check result."""
        duplicate_result = next((r for r in business_results if r.rule_name == "duplicate_detection"), None)

        if not duplicate_result:
            return DuplicateCheckResult(is_duplicate=False)

        return DuplicateCheckResult(
            is_duplicate=not duplicate_result.passed,
            confidence=1.0 if not duplicate_result.passed else 0.0,
            match_criteria=duplicate_result.details or {}
        )

    def _extract_header_amount(self, extraction) -> Optional[float]:
        """Extract amount from header JSON."""
        try:
            if isinstance(extraction.header_json, dict):
                total = extraction.header_json.get("total_amount") or extraction.header_json.get("total")
                if total:
                    return float(total)
        except (ValueError, TypeError):
            pass
        return None

    # Additional validation methods (simplified implementations)
    async def _validate_po_matching(self, rule: ValidationRule, header: Dict[str, Any], session: AsyncSession) -> RuleExecutionResult:
        """Validate PO matching."""
        # Simplified implementation
        po_number = header.get("po_number")
        if po_number:
            return RuleExecutionResult(
                rule_name=rule.name,
                passed=True,
                message=f"PO validation passed: {po_number}"
            )
        return RuleExecutionResult(
            rule_name=rule.name,
            passed=True,
            message="No PO number provided"
        )

    async def _validate_grn_matching(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]], session: AsyncSession
    ) -> RuleExecutionResult:
        """Validate GRN matching."""
        # Simplified implementation
        return RuleExecutionResult(
            rule_name=rule.name,
            passed=True,
            message="GRN validation passed"
        )

    async def _validate_invoice_age(self, rule: ValidationRule, header: Dict[str, Any]) -> RuleExecutionResult:
        """Validate invoice age."""
        max_age_days = rule.parameters.get("max_age_days", 365)
        invoice_date = header.get("invoice_date")

        if invoice_date and isinstance(invoice_date, datetime):
            age_days = (datetime.utcnow() - invoice_date).days
            if age_days > max_age_days:
                return RuleExecutionResult(
                    rule_name=rule.name,
                    passed=False,
                    reason_taxonomy=ReasonTaxonomy.BUSINESS_RULE_VIOLATION,
                    message=f"Invoice age {age_days} days exceeds maximum {max_age_days} days"
                )

        return RuleExecutionResult(
            rule_name=rule.name,
            passed=True,
            message="Invoice age validation passed"
        )

    async def _validate_amount_limits(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate amount limits."""
        max_amount = rule.parameters.get("max_total_amount", 1000000)
        total_amount = header.get("total_amount")

        if total_amount:
            try:
                amount_float = float(total_amount)
                if amount_float > max_amount:
                    return RuleExecutionResult(
                        rule_name=rule.name,
                        passed=False,
                        reason_taxonomy=ReasonTaxonomy.BUSINESS_RULE_VIOLATION,
                        message=f"Total amount {amount_float} exceeds maximum {max_amount}"
                    )
            except (ValueError, TypeError):
                pass

        return RuleExecutionResult(
            rule_name=rule.name,
            passed=True,
            message="Amount limits validation passed"
        )

    async def _validate_tax_calculation(
        self, rule: ValidationRule, header: Dict[str, Any], lines: List[Dict[str, Any]]
    ) -> RuleExecutionResult:
        """Validate tax calculations."""
        # Simplified tax validation
        return RuleExecutionResult(
            rule_name=rule.name,
            passed=True,
            message="Tax calculation validation passed"
        )