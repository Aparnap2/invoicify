#!/usr/bin/env python3
"""
Reference Solution: Junior vs Senior Patterns Refactoring

This is a senior-level implementation that addresses all the issues in the junior code
while demonstrating proper design patterns, error handling, and maintainability.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any, Protocol
from datetime import datetime

logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationIssue:
    """Structured validation issue with comprehensive metadata"""
    code: str
    message: str
    severity: ValidationSeverity
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    suggested_fix: Optional[str] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

@dataclass
class ValidationResult:
    """Comprehensive validation result with performance metrics"""
    is_valid: bool
    issues: List[ValidationIssue]
    processing_time_ms: int
    confidence_score: float
    metadata: Dict[str, Any]

    def has_errors(self) -> bool:
        """Check if there are any error-level issues"""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues"""
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    def get_error_count(self) -> int:
        """Get count of error-level issues"""
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    def get_warning_count(self) -> int:
        """Get count of warning-level issues"""
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)

class ValidationRule(ABC):
    """Abstract base class for validation rules following Strategy pattern"""

    def __init__(self, name: str, severity: ValidationSeverity = ValidationSeverity.ERROR):
        self.name = name
        self.severity = severity
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def validate(self, invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate invoice data and return list of issues"""
        pass

    async def is_applicable(self, invoice_data: Dict[str, Any]) -> bool:
        """Check if this rule applies to the given invoice data"""
        return True

class RequiredFieldsRule(ValidationRule):
    """Validates that all required fields are present and non-empty"""

    def __init__(self, required_fields: List[str]):
        super().__init__("required_fields")
        self.required_fields = required_fields

    async def validate(self, invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
        issues = []

        for field in self.required_fields:
            field_value = invoice_data.get(field)

            if field_value is None:
                issues.append(ValidationIssue(
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field}' is missing",
                    severity=self.severity,
                    field=field,
                    suggested_fix=f"Add '{field}' field to invoice data"
                ))
            elif isinstance(field_value, str) and not field_value.strip():
                issues.append(ValidationIssue(
                    code="EMPTY_REQUIRED_FIELD",
                    message=f"Required field '{field}' is empty",
                    severity=self.severity,
                    field=field,
                    details={"value": field_value},
                    suggested_fix=f"Provide a non-empty value for '{field}'"
                ))

        return issues

class AmountValidationRule(ValidationRule):
    """Validates amount fields with proper decimal handling"""

    def __init__(self, field_name: str, allow_negative: bool = False, allow_zero: bool = True):
        super().__init__(f"amount_validation_{field_name}")
        self.field_name = field_name
        self.allow_negative = allow_negative
        self.allow_zero = allow_zero

    async def validate(self, invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
        issues = []

        amount_value = invoice_data.get(self.field_name)
        if amount_value is None:
            return issues  # Required fields handled separately

        try:
            # Convert to Decimal for precise financial calculations
            amount = Decimal(str(amount_value))

            if not self.allow_negative and amount < 0:
                issues.append(ValidationIssue(
                    code="NEGATIVE_AMOUNT",
                    message=f"Amount '{self.field_name}' cannot be negative",
                    severity=self.severity,
                    field=self.field_name,
                    details={"value": str(amount)},
                    suggested_fix="Ensure amounts are non-negative or adjust validation rules"
                ))

            if not self.allow_zero and amount == 0:
                issues.append(ValidationIssue(
                    code="ZERO_AMOUNT",
                    message=f"Amount '{self.field_name}' cannot be zero",
                    severity=ValidationSeverity.WARNING,
                    field=self.field_name,
                    details={"value": str(amount)},
                    suggested_fix="Verify that zero amounts are intentional"
                ))

            # Check for unreasonable precision (more than 2 decimal places for currency)
            if abs(amount.as_tuple().exponent) > 2:
                issues.append(ValidationIssue(
                    code="EXCESSIVE_PRECISION",
                    message=f"Amount '{self.field_name}' has excessive decimal precision",
                    severity=ValidationSeverity.WARNING,
                    field=self.field_name,
                    details={"value": str(amount), "precision": abs(amount.as_tuple().exponent)},
                    suggested_fix="Round amounts to appropriate currency precision (2 decimal places)"
                ))

        except (InvalidOperation, ValueError, TypeError) as e:
            issues.append(ValidationIssue(
                code="INVALID_AMOUNT_FORMAT",
                message=f"Amount '{self.field_name}' has invalid format: {str(e)}",
                severity=self.severity,
                field=self.field_name,
                details={"value": str(amount_value), "error": str(e)},
                suggested_fix="Provide amount in valid numeric format (e.g., '123.45' or 123.45)"
            ))

        return issues

class LineItemValidationRule(ValidationRule):
    """Comprehensive line item validation with business logic"""

    def __init__(self, tolerance_cents: int = 1, max_line_items: int = 100):
        super().__init__("line_items")
        self.tolerance = Decimal(str(tolerance_cents / 100))
        self.max_line_items = max_line_items

    async def validate(self, invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
        issues = []

        lines = invoice_data.get('lines', [])

        if not lines:
            issues.append(ValidationIssue(
                code="NO_LINE_ITEMS",
                message="Invoice must have at least one line item",
                severity=self.severity,
                suggested_fix="Add at least one line item with description and amount"
            ))
            return issues

        if len(lines) > self.max_line_items:
            issues.append(ValidationIssue(
                code="EXCESSIVE_LINE_ITEMS",
                message=f"Invoice has {len(lines)} line items (maximum: {self.max_line_items})",
                severity=ValidationSeverity.WARNING,
                details={"line_count": len(lines), "max_allowed": self.max_line_items},
                suggested_fix="Consider splitting large invoices or review line item structure"
            ))

        line_total = Decimal('0')
        for i, line in enumerate(lines):
            line_issues = await self._validate_single_line(line, i)
            issues.extend(line_issues)

            # Calculate line total if amount is valid
            if not any(issue.field == f"lines[{i}].amount" for issue in line_issues):
                try:
                    amount = Decimal(str(line.get('amount', 0)))
                    line_total += amount
                except (InvalidOperation, ValueError, TypeError):
                    # Amount validation issue already captured above
                    pass

        # Validate totals match if we have a valid invoice total
        self._validate_total_matching(invoice_data, line_total, issues)

        return issues

    async def _validate_single_line(self, line: Dict[str, Any], index: int) -> List[ValidationIssue]:
        """Validate a single line item"""
        issues = []
        line_prefix = f"lines[{index}]"

        # Validate description
        description = line.get('description', '').strip()
        if not description:
            issues.append(ValidationIssue(
                code="MISSING_LINE_DESCRIPTION",
                message=f"Line {index + 1} missing description",
                severity=self.severity,
                field=f"{line_prefix}.description",
                suggested_fix="Add meaningful description for each line item"
            ))
        elif len(description) < 3:
            issues.append(ValidationIssue(
                code="SHORT_LINE_DESCRIPTION",
                message=f"Line {index + 1} description is too short",
                severity=ValidationSeverity.WARNING,
                field=f"{line_prefix}.description",
                details={"description": description},
                suggested_fix="Provide more descriptive line item descriptions"
            ))

        # Validate amount
        amount_value = line.get('amount')
        if amount_value is None:
            issues.append(ValidationIssue(
                code="MISSING_LINE_AMOUNT",
                message=f"Line {index + 1} missing amount",
                severity=self.severity,
                field=f"{line_prefix}.amount",
                suggested_fix="Specify amount for each line item"
            ))
        else:
            try:
                amount = Decimal(str(amount_value))
                if amount < 0:
                    issues.append(ValidationIssue(
                        code="NEGATIVE_LINE_AMOUNT",
                        message=f"Line {index + 1} amount cannot be negative",
                        severity=self.severity,
                        field=f"{line_prefix}.amount",
                        details={"value": str(amount)},
                        suggested_fix="Ensure all line item amounts are non-negative"
                    ))
                elif amount == 0:
                    issues.append(ValidationIssue(
                        code="ZERO_LINE_AMOUNT",
                        message=f"Line {index + 1} has zero amount",
                        severity=ValidationSeverity.WARNING,
                        field=f"{line_prefix}.amount",
                        details={"value": str(amount)},
                        suggested_fix="Verify that zero-amount line items are intentional"
                    ))
            except (InvalidOperation, ValueError, TypeError):
                issues.append(ValidationIssue(
                    code="INVALID_LINE_AMOUNT",
                    message=f"Line {index + 1} has invalid amount format",
                    severity=self.severity,
                    field=f"{line_prefix}.amount",
                    details={"value": str(amount_value)},
                    suggested_fix="Provide valid numeric amount (e.g., '123.45')"
                ))

        return issues

    def _validate_total_matching(self, invoice_data: Dict[str, Any], line_total: Decimal, issues: List[ValidationIssue]):
        """Validate that line totals match invoice total"""
        try:
            invoice_total_str = invoice_data.get('total_amount', '0')
            invoice_total = Decimal(str(invoice_total_str))

            difference = abs(line_total - invoice_total)
            if difference > self.tolerance:
                issues.append(ValidationIssue(
                    code="TOTAL_MISMATCH",
                    message=f"Line total ({line_total}) doesn't match invoice total ({invoice_total})",
                    severity=self.severity,
                    details={
                        "line_total": str(line_total),
                        "invoice_total": str(invoice_total),
                        "difference": str(difference),
                        "tolerance": str(self.tolerance)
                    },
                    suggested_fix="Ensure line items sum to the invoice total within tolerance"
                ))

        except (InvalidOperation, ValueError, TypeError):
            # Invoice total validation already handled by amount validation rule
            pass

# Protocol for external service dependencies (Dependency Injection pattern)
class VendorService(Protocol):
    async def get_vendor_by_name(self, vendor_name: str) -> Optional[Any]:
        ...

class VendorValidationRule(ValidationRule):
    """Validates vendor with proper error handling and caching"""

    def __init__(self, vendor_service: VendorService, cache_ttl: int = 300):
        super().__init__("vendor_validation")
        self.vendor_service = vendor_service
        self.cache_ttl = cache_ttl
        self._vendor_cache = {}

    async def validate(self, invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
        issues = []
        vendor_name = invoice_data.get('vendor_name', '').strip()

        if not vendor_name:
            return issues  # Handled by required fields rule

        try:
            # Check cache first
            vendor = await self._get_cached_vendor(vendor_name)

            if not vendor:
                issues.append(ValidationIssue(
                    code="VENDOR_NOT_FOUND",
                    message=f"Vendor '{vendor_name}' not found in system",
                    severity=self.severity,
                    field="vendor_name",
                    details={"vendor_name": vendor_name},
                    suggested_fix="Add vendor to system or correct vendor name"
                ))
            elif not getattr(vendor, 'is_active', True):
                issues.append(ValidationIssue(
                    code="INACTIVE_VENDOR",
                    message=f"Vendor '{vendor_name}' is inactive",
                    severity=self.severity,
                    field="vendor_name",
                    details={
                        "vendor_id": str(getattr(vendor, 'id', 'unknown')),
                        "vendor_name": vendor_name
                    },
                    suggested_fix="Activate vendor or use an active vendor"
                ))

        except Exception as e:
            self.logger.error(f"Vendor validation failed for '{vendor_name}': {e}")
            issues.append(ValidationIssue(
                code="VENDOR_VALIDATION_ERROR",
                message="Vendor service temporarily unavailable",
                severity=ValidationSeverity.WARNING,
                field="vendor_name",
                details={"error": str(e), "vendor_name": vendor_name},
                suggested_fix="Try again later or contact support"
            ))

        return issues

    async def _get_cached_vendor(self, vendor_name: str) -> Optional[Any]:
        """Get vendor from cache or fetch from service"""
        # Check cache
        if vendor_name in self._vendor_cache:
            cached_data = self._vendor_cache[vendor_name]
            if datetime.now().timestamp() - cached_data['timestamp'] < self.cache_ttl:
                return cached_data['vendor']

        # Fetch from service
        try:
            vendor = await self.vendor_service.get_vendor_by_name(vendor_name)

            # Update cache
            self._vendor_cache[vendor_name] = {
                'vendor': vendor,
                'timestamp': datetime.now().timestamp()
            }

            return vendor
        except Exception as e:
            self.logger.error(f"Failed to fetch vendor '{vendor_name}': {e}")
            return None

class ValidationEngine:
    """Senior-level validation engine with comprehensive rule system and monitoring"""

    def __init__(self, enable_metrics: bool = True):
        self.rules: List[ValidationRule] = []
        self.logger = logging.getLogger(__name__)
        self.enable_metrics = enable_metrics
        self._metrics = {
            'total_validations': 0,
            'total_issues': 0,
            'avg_processing_time': 0,
            'rule_performance': {}
        }

    def add_rule(self, rule: ValidationRule):
        """Add a validation rule to the engine"""
        self.rules.append(rule)
        self.logger.info(f"Added validation rule: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a validation rule by name"""
        original_count = len(self.rules)
        self.rules = [rule for rule in self.rules if rule.name != rule_name]
        removed = len(self.rules) < original_count

        if removed:
            self.logger.info(f"Removed validation rule: {rule_name}")

        return removed

    async def validate_invoice(self, invoice_data: Dict[str, Any]) -> ValidationResult:
        """Comprehensive invoice validation with performance monitoring"""
        start_time = datetime.utcnow()

        try:
            # Input validation
            if not isinstance(invoice_data, dict):
                return ValidationResult(
                    is_valid=False,
                    issues=[ValidationIssue(
                        code="INVALID_INPUT_TYPE",
                        message="Invoice data must be a dictionary",
                        severity=ValidationSeverity.ERROR,
                        suggested_fix="Provide invoice data as a JSON object/dictionary"
                    )],
                    processing_time_ms=0,
                    confidence_score=0.0,
                    metadata={"error": "invalid_input_type"}
                )

            all_issues = []
            rule_results = {}

            # Execute all validation rules
            for rule in self.rules:
                try:
                    # Check if rule is applicable
                    if not await rule.is_applicable(invoice_data):
                        continue

                    rule_start = datetime.utcnow()
                    rule_issues = await rule.validate(invoice_data)
                    rule_duration = int((datetime.utcnow() - rule_start).total_seconds() * 1000)

                    all_issues.extend(rule_issues)
                    rule_results[rule.name] = {
                        'issues_count': len(rule_issues),
                        'duration_ms': rule_duration,
                        'applicable': True
                    }

                    # Log rule performance
                    if self.enable_metrics:
                        self._update_rule_metrics(rule.name, rule_duration)

                except Exception as e:
                    self.logger.error(f"Rule '{rule.name}' failed: {e}")
                    all_issues.append(ValidationIssue(
                        code="VALIDATION_RULE_ERROR",
                        message=f"Validation rule '{rule.name}' encountered an error: {str(e)}",
                        severity=ValidationSeverity.ERROR,
                        details={"rule": rule.name, "error": str(e)},
                        suggested_fix="Contact support about validation system error"
                    ))
                    rule_results[rule.name] = {
                        'error': str(e),
                        'applicable': True
                    }

            # Calculate processing time
            processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Calculate confidence score based on issues and processing
            error_count = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.ERROR)
            warning_count = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.WARNING)

            # Confidence score: starts at 1.0, decreases with issues
            confidence_score = max(0.0, 1.0 - (error_count * 0.2) - (warning_count * 0.05))

            # Determine overall validity
            is_valid = not any(issue.severity == ValidationSeverity.ERROR for issue in all_issues)

            # Update metrics
            if self.enable_metrics:
                self._update_global_metrics(processing_time, len(all_issues))

            # Create comprehensive result
            result = ValidationResult(
                is_valid=is_valid,
                issues=all_issues,
                processing_time_ms=processing_time,
                confidence_score=confidence_score,
                metadata={
                    'rule_results': rule_results,
                    'invoice_number': invoice_data.get('invoice_number', 'unknown'),
                    'validation_timestamp': start_time.isoformat(),
                    'rules_executed': len([r for r in rule_results.values() if r.get('applicable', False)]),
                    'system_metrics': self._metrics if self.enable_metrics else None
                }
            )

            # Log completion with appropriate level
            if is_valid:
                self.logger.info(
                    f"Validation PASSED for invoice {invoice_data.get('invoice_number', 'unknown')} "
                    f"({processing_time}ms, {len(all_issues)} issues)"
                )
            else:
                self.logger.warning(
                    f"Validation FAILED for invoice {invoice_data.get('invoice_number', 'unknown')} "
                    f"({processing_time}ms, {len(all_issues)} issues, {error_count} errors)"
                )

            return result

        except Exception as e:
            self.logger.error(f"Validation engine failed: {e}")
            processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return ValidationResult(
                is_valid=False,
                issues=[ValidationIssue(
                    code="VALIDATION_ENGINE_ERROR",
                    message=f"Validation system error: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    details={"error": str(e)},
                    suggested_fix="Contact support about validation system failure"
                )],
                processing_time_ms=processing_time,
                confidence_score=0.0,
                metadata={"error": str(e), "processing_time": processing_time}
            )

    def _update_rule_metrics(self, rule_name: str, duration_ms: int):
        """Update performance metrics for a specific rule"""
        if rule_name not in self._metrics['rule_performance']:
            self._metrics['rule_performance'][rule_name] = {
                'total_executions': 0,
                'total_duration': 0,
                'avg_duration': 0
            }

        rule_metrics = self._metrics['rule_performance'][rule_name]
        rule_metrics['total_executions'] += 1
        rule_metrics['total_duration'] += duration_ms
        rule_metrics['avg_duration'] = rule_metrics['total_duration'] // rule_metrics['total_executions']

    def _update_global_metrics(self, processing_time_ms: int, issues_count: int):
        """Update global validation metrics"""
        self._metrics['total_validations'] += 1
        self._metrics['total_issues'] += issues_count

        # Calculate rolling average processing time
        total = self._metrics['total_validations']
        current_avg = self._metrics['avg_processing_time']
        self._metrics['avg_processing_time'] = ((current_avg * (total - 1)) + processing_time_ms) // total

    def get_metrics(self) -> Dict[str, Any]:
        """Get current validation metrics"""
        return self._metrics.copy()

    def reset_metrics(self):
        """Reset all metrics"""
        self._metrics = {
            'total_validations': 0,
            'total_issues': 0,
            'avg_processing_time': 0,
            'rule_performance': {}
        }

# Factory function for easy engine creation
def create_validation_engine(
    vendor_service: Optional[VendorService] = None,
    enable_metrics: bool = True,
    tolerance_cents: int = 1,
    max_line_items: int = 100
) -> ValidationEngine:
    """Factory function to create a pre-configured validation engine"""

    engine = ValidationEngine(enable_metrics=enable_metrics)

    # Add standard validation rules
    engine.add_rule(RequiredFieldsRule([
        'vendor_name', 'invoice_number', 'total_amount'
    ]))

    engine.add_rule(AmountValidationRule('total_amount', allow_negative=False))
    engine.add_rule(LineItemValidationRule(tolerance_cents, max_line_items))

    if vendor_service:
        engine.add_rule(VendorValidationRule(vendor_service))

    return engine

# Example usage and testing
async def main():
    """Example usage of the refactored validation system"""

    # Mock vendor service for testing
    class MockVendorService:
        async def get_vendor_by_name(self, vendor_name: str):
            if vendor_name.lower() == "acme corp":
                vendor = type('Vendor', (), {'id': '123', 'name': 'ACME Corp', 'is_active': True})()
                return vendor
            return None

    # Create validation engine
    vendor_service = MockVendorService()
    validation_engine = create_validation_engine(vendor_service, enable_metrics=True)

    # Test data
    test_invoice = {
        'vendor_name': 'ACME Corp',
        'invoice_number': 'INV-2024-001',
        'total_amount': '150.00',
        'lines': [
            {'description': 'Consulting Services', 'amount': '100.00'},
            {'description': 'Travel Expenses', 'amount': '50.00'}
        ]
    }

    # Run validation
    result = await validation_engine.validate_invoice(test_invoice)

    # Print results
    print(f"Validation Result: {'PASSED' if result.is_valid else 'FAILED'}")
    print(f"Confidence Score: {result.confidence_score:.2f}")
    print(f"Processing Time: {result.processing_time_ms}ms")
    print(f"Issues Found: {len(result.issues)}")

    for issue in result.issues:
        print(f"  [{issue.severity.value.upper()}] {issue.code}: {issue.message}")
        if issue.suggested_fix:
            print(f"    Suggested Fix: {issue.suggested_fix}")

    # Show metrics
    metrics = validation_engine.get_metrics()
    print(f"\nSystem Metrics:")
    print(f"  Total Validations: {metrics['total_validations']}")
    print(f"  Average Processing Time: {metrics['avg_processing_time']}ms")
    print(f"  Rule Performance: {metrics['rule_performance']}")

if __name__ == "__main__":
    asyncio.run(main())