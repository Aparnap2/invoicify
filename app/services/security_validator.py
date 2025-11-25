"""
Advanced security validation service with comprehensive attack pattern detection.
Implements defense-in-depth security validation with threat intelligence and business logic protection.
"""

import logging
import re
import hashlib
import ipaddress
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import time

from app.schemas.validation_rules import (
    SecurityThreatLevel,
    ThreatType,
    ThreatDetectionResult,
    SecurityPattern,
    AllowlistRule,
    SecurityRule,
    DEFAULT_SECURITY_RULES,
    DEFAULT_ALLOWLIST_RULES,
    SQL_INJECTION_PATTERNS,
    XSS_PATTERNS,
    PATH_TRAVERSAL_PATTERNS,
    COMMAND_INJECTION_PATTERNS
)

logger = logging.getLogger(__name__)


@dataclass
class SecurityContext:
    """Security context for validation operations."""
    source_ip: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ValidationResult:
    """Result of security validation."""
    is_valid: bool
    is_threat: bool
    threat_type: Optional[ThreatType] = None
    threat_level: SecurityThreatLevel = SecurityThreatLevel.LOW
    confidence: float = 0.0
    matched_patterns: List[str] = field(default_factory=list)
    field: Optional[str] = None
    original_value: Optional[str] = None
    risk_score: float = 0.0
    recommendation: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileUploadValidation:
    """File upload security validation result."""
    is_safe: bool
    is_threat: bool
    threat_type: Optional[ThreatType] = None
    threat_level: SecurityThreatLevel = SecurityThreatLevel.LOW
    file_size_mb: float = 0.0
    file_type: str = ""
    filename: str = ""
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class RateLimitResult:
    """Rate limiting validation result."""
    is_allowed: bool
    is_threat: bool
    threat_level: SecurityThreatLevel = SecurityThreatLevel.LOW
    current_requests: int = 0
    limit: int = 0
    time_window_minutes: int = 0
    retry_after_seconds: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class SecurityValidator:
    """
    Advanced security validation service with comprehensive threat detection.

    Features:
    - SQL injection detection with advanced pattern matching
    - XSS attack detection with HTML/JavaScript analysis
    - Path traversal and file upload security
    - Command injection prevention
    - Rate limiting and abuse detection
    - Business logic abuse protection
    - Allowlist/denylist validation
    - Threat intelligence integration
    - Performance-optimized pattern matching
    - Risk scoring and recommendation engine
    """

    def __init__(self, enable_threat_intelligence: bool = True):
        """Initialize security validator."""
        self.enable_threat_intelligence = enable_threat_intelligence

        # Initialize security rules
        self.security_rules: Dict[str, SecurityRule] = {}
        self.allowlist_rules: Dict[str, AllowlistRule] = {}
        self._load_default_rules()

        # Compile regex patterns for performance
        self._compile_patterns()

        # Initialize rate limiting tracking
        self.rate_limits: Dict[str, deque] = defaultdict(deque)
        self.request_history: Dict[str, List[datetime]] = defaultdict(list)

        # Initialize threat intelligence
        self.malicious_ips: Set[str] = set()
        self.suspicious_patterns: Dict[str, float] = {}

        # Statistics
        self.validation_stats = {
            "total_validations": 0,
            "threats_detected": 0,
            "sql_injections_blocked": 0,
            "xss_attempts_blocked": 0,
            "file_uploads_blocked": 0,
            "rate_limit_violations": 0,
            "validation_time_ms": 0.0
        }

        logger.info("SecurityValidator initialized")

    def _load_default_rules(self):
        """Load default security rules."""
        for rule in DEFAULT_SECURITY_RULES:
            self.security_rules[rule.name] = rule

        for allowlist_rule in DEFAULT_ALLOWLIST_RULES:
            self.allowlist_rules[allowlist_rule.field_name] = allowlist_rule

    def _compile_patterns(self):
        """Compile security patterns for optimal performance."""
        self.compiled_patterns = {}

        for rule_name, rule in self.security_rules.items():
            self.compiled_patterns[rule_name] = []
            for pattern in rule.patterns:
                if pattern.pattern_type == "regex":
                    try:
                        compiled_regex = re.compile(
                            pattern.pattern,
                            re.IGNORECASE if not pattern.is_case_sensitive else 0
                        )
                        self.compiled_patterns[rule_name].append({
                            "pattern": compiled_regex,
                            "threat_type": pattern.threat_type,
                            "confidence": pattern.confidence,
                            "name": pattern.name
                        })
                    except re.error as e:
                        logger.warning(f"Failed to compile pattern {pattern.name}: {e}")

    def validate_field(
        self,
        field_name: str,
        value: Any,
        context: Optional[SecurityContext] = None,
        custom_rules: Optional[List[SecurityRule]] = None
    ) -> ValidationResult:
        """
        Validate a field for security threats.

        Args:
            field_name: Name of the field being validated
            value: Value to validate
            context: Security context information
            custom_rules: Optional custom security rules

        Returns:
            ValidationResult with threat analysis
        """
        start_time = time.time()
        self.validation_stats["total_validations"] += 1

        if value is None:
            return ValidationResult(is_valid=True, is_threat=False, field=field_name)

        original_value = str(value)
        current_value = original_value

        # Initialize result
        result = ValidationResult(
            is_valid=True,
            is_threat=False,
            field=field_name,
            original_value=original_value,
            threat_level=SecurityThreatLevel.LOW,
            confidence=0.0
        )

        try:
            # Apply allowlist validation first
            allowlist_result = self._validate_allowlist(field_name, current_value)
            if not allowlist_result["valid"]:
                result.is_valid = False
                result.is_threat = True
                result.threat_level = SecurityThreatLevel.MEDIUM
                result.confidence = 0.9
                result.matched_patterns.append("allowlist_violation")
                result.recommendation = f"Value not in allowlist for field {field_name}"
                result.details.update(allowlist_result)

            # Apply denylist validation
            denylist_result = self._validate_denylist(field_name, current_value)
            if denylist_result["violation"]:
                result.is_valid = False
                result.is_threat = True
                result.threat_level = SecurityThreatLevel.HIGH
                result.confidence = 0.95
                result.matched_patterns.append("denylist_violation")
                result.recommendation = f"Value contains forbidden content for field {field_name}"
                result.details.update(denylist_result)

            # Apply security pattern validation
            for rule_name, rule in self.security_rules.items():
                if not rule.enabled:
                    continue

                # Check if rule applies to this field
                if not self._rule_applies_to_field(rule, field_name):
                    continue

                pattern_matches = self._check_patterns(rule_name, current_value)
                for match in pattern_matches:
                    result.is_valid = False
                    result.is_threat = True
                    result.threat_type = match["threat_type"]
                    result.confidence = max(result.confidence, match["confidence"])
                    result.matched_patterns.append(match["name"])

                    # Update threat level if this is more severe
                    if self._compare_threat_levels(match["threat_type"], result.threat_level) > 0:
                        result.threat_level = self._get_threat_level_for_type(match["threat_type"])

            # Apply custom rules if provided
            if custom_rules:
                for rule in custom_rules:
                    if not rule.enabled:
                        continue

                    pattern_matches = self._check_patterns(rule.name, current_value)
                    for match in pattern_matches:
                        result.is_valid = False
                        result.is_threat = True
                        result.threat_type = match["threat_type"]
                        result.confidence = max(result.confidence, match["confidence"])
                        result.matched_patterns.append(f"custom_{match['name']}")

            # Apply business logic validation
            business_result = self._validate_business_logic(field_name, current_value)
            if business_result["violation"]:
                result.is_valid = False
                result.is_threat = True
                result.confidence = max(result.confidence, business_result["confidence"])
                result.matched_patterns.extend(business_result["patterns"])
                result.recommendation = business_result["recommendation"]
                result.details.update(business_result["details"])

            # Apply threat intelligence
            if self.enable_threat_intelligence and context:
                intel_result = self._apply_threat_intelligence(current_value, context)
                if intel_result["is_threat"]:
                    result.is_valid = False
                    result.is_threat = True
                    result.confidence = max(result.confidence, intel_result["confidence"])
                    result.matched_patterns.extend(intel_result["patterns"])
                    result.details.update(intel_result["details"])

            # Calculate risk score
            result.risk_score = self._calculate_risk_score(result)

            # Generate recommendation
            if not result.is_valid:
                result.recommendation = self._generate_recommendation(result)

            # Update statistics
            processing_time = (time.time() - start_time) * 1000
            self.validation_stats["validation_time_ms"] += processing_time

            if result.is_threat:
                self.validation_stats["threats_detected"] += 1
                if result.threat_type == ThreatType.SQL_INJECTION:
                    self.validation_stats["sql_injections_blocked"] += 1
                elif result.threat_type == ThreatType.XSS:
                    self.validation_stats["xss_attempts_blocked"] += 1

            return result

        except Exception as e:
            logger.error(f"Security validation error for field {field_name}: {e}")
            return ValidationResult(
                is_valid=False,
                is_threat=True,
                field=field_name,
                original_value=original_value,
                threat_level=SecurityThreatLevel.HIGH,
                confidence=1.0,
                recommendation="Validation error - treat as suspicious",
                details={"error": str(e)}
            )

    def validate_file_upload(
        self,
        file_data: Dict[str, Any],
        context: Optional[SecurityContext] = None
    ) -> FileUploadValidation:
        """
        Validate file upload for security threats.

        Args:
            file_data: Dictionary containing file information (filename, content_type, size, etc.)
            context: Security context information

        Returns:
            FileUploadValidation with comprehensive analysis
        """
        result = FileUploadValidation(
            is_safe=True,
            is_threat=False,
            filename=file_data.get("filename", ""),
            file_type=file_data.get("content_type", ""),
            file_size_mb=file_data.get("size", 0) / (1024 * 1024)  # Convert to MB
        )

        try:
            # Validate filename
            filename = file_data.get("filename", "")
            if filename:
                filename_result = self.validate_field("filename", filename, context)
                if filename_result.is_threat:
                    result.is_safe = False
                    result.is_threat = True
                    result.threat_level = max(result.threat_level, filename_result.threat_level)
                    result.issues.extend(filename_result.matched_patterns)

            # Validate file size
            max_size_mb = 50  # Default max size
            if result.file_size_mb > max_size_mb:
                result.is_safe = False
                result.is_threat = True
                result.threat_level = SecurityThreatLevel.MEDIUM
                result.issues.append(f"File too large: {result.file_size_mb:.2f}MB > {max_size_mb}MB")
                result.recommendations.append("Compress file or use smaller file")

            # Validate file type
            content_type = file_data.get("content_type", "")
            dangerous_types = [
                "application/x-executable",
                "application/x-msdownload",
                "application/x-msdos-program",
                "application/x-sh",
                "application/x-python",
                "application/x-perl",
                "application/x-ruby"
            ]

            if content_type in dangerous_types:
                result.is_safe = False
                result.is_threat = True
                result.threat_level = SecurityThreatLevel.HIGH
                result.threat_type = ThreatType.FILE_UPLOAD_MALWARE
                result.issues.append(f"Dangerous file type: {content_type}")
                result.recommendations.append("Use allowed file types only")

            # Check file extension
            dangerous_extensions = [
                ".exe", ".bat", ".cmd", ".com", ".pif", ".scr", ".vbs", ".js", ".jar",
                ".ps1", ".sh", ".py", ".pl", ".rb", ".php", ".asp", ".aspx"
            ]

            if filename:
                file_ext = filename.lower().split('.')[-1] if '.' in filename else ""
                if f".{file_ext}" in dangerous_extensions:
                    result.is_safe = False
                    result.is_threat = True
                    result.threat_level = SecurityThreatLevel.HIGH
                    result.threat_type = ThreatType.FILE_UPLOAD_MALWARE
                    result.issues.append(f"Dangerous file extension: .{file_ext}")
                    result.recommendations.append("Use allowed file extensions only")

            # Check for double extensions (common attack vector)
            if filename:
                parts = filename.lower().split('.')
                if len(parts) > 2:
                    result.is_safe = False
                    result.threat_level = max(result.threat_level, SecurityThreatLevel.MEDIUM)
                    result.issues.append("Multiple file extensions detected")
                    result.recommendations.append("Use single file extension")

            # Validate content if provided
            if "content" in file_data:
                content_result = self._validate_file_content(file_data["content"], filename)
                if content_result["is_threat"]:
                    result.is_safe = False
                    result.is_threat = True
                    result.threat_level = max(result.threat_level, content_result["threat_level"])
                    result.threat_type = content_result.get("threat_type")
                    result.issues.extend(content_result["issues"])
                    result.recommendations.extend(content_result["recommendations"])

            # Update statistics
            if result.is_threat:
                self.validation_stats["file_uploads_blocked"] += 1

            return result

        except Exception as e:
            logger.error(f"File upload validation error: {e}")
            return FileUploadValidation(
                is_safe=False,
                is_threat=True,
                threat_level=SecurityThreatLevel.HIGH,
                filename=filename,
                issues=[f"Validation error: {str(e)}"],
                recommendations=["File validation failed - review manually"]
            )

    def check_rate_limits(
        self,
        context: SecurityContext,
        limit_per_minute: int = 100,
        time_window_minutes: int = 1
    ) -> RateLimitResult:
        """
        Check rate limits for the given context.

        Args:
            context: Security context with IP/user information
            limit_per_minute: Maximum requests per time window
            time_window_minutes: Time window in minutes

        Returns:
            RateLimitResult with analysis
        """
        now = datetime.now()
        window_start = now - timedelta(minutes=time_window_minutes)

        # Use IP address as primary key, fallback to user ID
        key = context.source_ip or context.user_id or "unknown"

        # Clean old entries
        self.request_history[key] = [
            timestamp for timestamp in self.request_history[key]
            if timestamp > window_start
        ]

        # Count current requests
        current_requests = len(self.request_history[key])

        # Check limit
        is_allowed = current_requests < limit_per_minute
        is_threat = not is_allowed and current_requests > limit_per_minute * 1.5  # 50% buffer

        # Calculate retry after
        if not is_allowed and self.request_history[key]:
            oldest_request = min(self.request_history[key])
            retry_after_seconds = int((oldest_request + timedelta(minutes=time_window_minutes) - now).total_seconds())
        else:
            retry_after_seconds = 0

        result = RateLimitResult(
            is_allowed=is_allowed,
            is_threat=is_threat,
            threat_level=SecurityThreatLevel.HIGH if is_threat else SecurityThreatLevel.LOW,
            current_requests=current_requests,
            limit=limit_per_minute,
            time_window_minutes=time_window_minutes,
            retry_after_seconds=max(0, retry_after_seconds),
            details={
                "key": key,
                "window_start": window_start.isoformat(),
                "requests_in_window": current_requests
            }
        )

        # Add current request to history
        self.request_history[key].append(now)

        # Update statistics
        if result.is_threat:
            self.validation_stats["rate_limit_violations"] += 1

        return result

    def validate_allowlist(
        self,
        field_name: str,
        value: str,
        allowed_values: Optional[List[str]] = None
    ) -> ValidationResult:
        """
        Validate value against allowlist.

        Args:
            field_name: Name of the field
            value: Value to validate
            allowed_values: Optional custom allowlist

        Returns:
            ValidationResult with allowlist analysis
        """
        result = ValidationResult(
            is_valid=True,
            is_threat=False,
            field=field_name,
            original_value=value
        )

        try:
            # Use custom allowlist if provided, otherwise use configured rules
            if allowed_values:
                # Direct allowlist validation
                if value not in allowed_values:
                    result.is_valid = False
                    result.is_threat = True
                    result.threat_level = SecurityThreatLevel.MEDIUM
                    result.confidence = 1.0
                    result.matched_patterns.append("allowlist_violation")
                    result.recommendation = f"Value '{value}' not in allowlist"
                    result.details = {"allowed_values": allowed_values, "actual_value": value}
            else:
                # Use configured allowlist rules
                if field_name in self.allowlist_rules:
                    rule = self.allowlist_rules[field_name]
                    if not self._check_allowlist_rule(rule, value):
                        result.is_valid = False
                        result.is_threat = True
                        result.threat_level = SecurityThreatLevel.MEDIUM if rule.is_strict else SecurityThreatLevel.LOW
                        result.confidence = 0.9
                        result.matched_patterns.append(f"allowlist_violation_{field_name}")
                        result.recommendation = rule.description or f"Value not in allowlist for {field_name}"
                        result.details = {
                            "allowed_values": rule.allowed_values,
                            "actual_value": value,
                            "is_strict": rule.is_strict
                        }

            return result

        except Exception as e:
            logger.error(f"Allowlist validation error for field {field_name}: {e}")
            return ValidationResult(
                is_valid=False,
                is_threat=True,
                field=field_name,
                original_value=value,
                threat_level=SecurityThreatLevel.HIGH,
                recommendation="Allowlist validation error",
                details={"error": str(e)}
            )

    def validate_query(self, query: str, context: Optional[SecurityContext] = None) -> ValidationResult:
        """
        Validate query for data exfiltration and abuse patterns.

        Args:
            query: Query string to validate
            context: Security context

        Returns:
            ValidationResult with query analysis
        """
        result = ValidationResult(
            is_valid=True,
            is_threat=False,
            original_value=query
        )

        try:
            # Check for data exfiltration patterns
            exfiltration_patterns = [
                r"(?i)(select\s+\*\s+from)",
                r"(?i)(select.*from.*where.*1\s*=\s*1)",
                r"(?i)(union\s+select)",
                r"(?i)(order\s+by\s+\d+)",
                r"(?i)(group\s+by\s+\w+)",
                r"(?i)(count\s*\(\s*\*\s*\))",
                r"(?i)(export|download|dump|backup)"
            ]

            for pattern in exfiltration_patterns:
                if re.search(pattern, query):
                    result.is_valid = False
                    result.is_threat = True
                    result.threat_type = ThreatType.DATA_EXFILTRATION
                    result.threat_level = SecurityThreatLevel.MEDIUM
                    result.confidence = 0.8
                    result.matched_patterns.append("data_exfiltration_pattern")
                    result.recommendation = "Query contains suspicious data access patterns"

            # Check for bulk operations
            bulk_patterns = [
                r"(?i)(delete\s+from.*where\s+1\s*=\s*1)",
                r"(?i)(update.*set.*where\s+1\s*=\s*1)",
                r"(?i)(insert\s+into.*select)",
                r"(?i)(drop\s+table)",
                r"(?i)(truncate\s+table)"
            ]

            for pattern in bulk_patterns:
                if re.search(pattern, query):
                    result.is_valid = False
                    result.is_threat = True
                    result.threat_type = ThreatType.BUSINESS_LOGIC_ABUSE
                    result.threat_level = SecurityThreatLevel.HIGH
                    result.confidence = 0.9
                    result.matched_patterns.append("bulk_operation_pattern")
                    result.recommendation = "Query contains dangerous bulk operations"

            return result

        except Exception as e:
            logger.error(f"Query validation error: {e}")
            return ValidationResult(
                is_valid=False,
                is_threat=True,
                original_value=query,
                threat_level=SecurityThreatLevel.HIGH,
                recommendation="Query validation error",
                details={"error": str(e)}
            )

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get security validation statistics."""
        return {
            **self.validation_stats,
            "average_validation_time_ms": (
                self.validation_stats["validation_time_ms"] /
                max(self.validation_stats["total_validations"], 1)
            ),
            "threat_detection_rate": (
                self.validation_stats["threats_detected"] /
                max(self.validation_stats["total_validations"], 1)
            ) * 100
        }

    def reset_stats(self):
        """Reset validation statistics."""
        self.validation_stats = {
            "total_validations": 0,
            "threats_detected": 0,
            "sql_injections_blocked": 0,
            "xss_attempts_blocked": 0,
            "file_uploads_blocked": 0,
            "rate_limit_violations": 0,
            "validation_time_ms": 0.0
        }

    # Private helper methods

    def _rule_applies_to_field(self, rule: SecurityRule, field_name: str) -> bool:
        """Check if security rule applies to the given field."""
        # For now, apply all rules to all fields
        # In the future, this could be made more sophisticated
        return True

    def _check_patterns(self, rule_name: str, value: str) -> List[Dict[str, Any]]:
        """Check if value matches any patterns for the given rule."""
        matches = []

        if rule_name in self.compiled_patterns:
            for pattern_info in self.compiled_patterns[rule_name]:
                pattern = pattern_info["pattern"]
                if pattern.search(value):
                    matches.append({
                        "pattern": pattern.pattern,
                        "threat_type": pattern_info["threat_type"],
                        "confidence": pattern_info["confidence"],
                        "name": pattern_info["name"],
                        "match": pattern.search(value).group()
                    })

        return matches

    def _validate_allowlist(self, field_name: str, value: str) -> Dict[str, Any]:
        """Validate value against field-specific allowlist."""
        if field_name not in self.allowlist_rules:
            return {"valid": True}

        rule = self.allowlist_rules[field_name]
        is_valid = self._check_allowlist_rule(rule, value)

        return {
            "valid": is_valid,
            "rule": rule.name,
            "allowed_values": rule.allowed_values,
            "is_strict": rule.is_strict
        }

    def _validate_denylist(self, field_name: str, value: str) -> Dict[str, Any]:
        """Validate value against denylist patterns."""
        denylist_patterns = [
            r"(?i)(\b(admin|root|administrator|test|demo)\b)",
            r"(?i)(\b(drop|delete|truncate|exec|script)\b)",
            r"(?i)(<\s*script|javascript:|on\w+\s*=)"
        ]

        for pattern in denylist_patterns:
            if re.search(pattern, value):
                return {
                    "violation": True,
                    "pattern": pattern,
                    "match": re.search(pattern, value).group()
                }

        return {"violation": False}

    def _validate_business_logic(self, field_name: str, value: str) -> Dict[str, Any]:
        """Validate business logic rules for the field."""
        result = {
            "violation": False,
            "confidence": 0.0,
            "patterns": [],
            "recommendation": "",
            "details": {}
        }

        # Amount field validation
        if field_name in ["total_amount", "amount", "subtotal_amount"]:
            try:
                amount = float(re.sub(r'[^\d.]', '', value))
                if amount < 0:
                    result["violation"] = True
                    result["confidence"] = 0.9
                    result["patterns"].append("negative_amount")
                    result["recommendation"] = "Negative amounts are suspicious"
                elif amount > 10000000:  # $10M threshold
                    result["violation"] = True
                    result["confidence"] = 0.7
                    result["patterns"].append("excessive_amount")
                    result["recommendation"] = "Unusually high amount requires review"
                    result["details"]["amount"] = amount
            except ValueError:
                # Invalid amount format
                pass

        # Date field validation
        elif field_name.endswith("_date") and "date" in field_name:
            try:
                # This is a simplified date check
                if "future" in value.lower():
                    result["violation"] = True
                    result["confidence"] = 0.6
                    result["patterns"].append("future_date")
                    result["recommendation"] = "Future dates may be suspicious"
            except:
                pass

        # Vendor name validation
        elif field_name == "vendor_name":
            if value.upper().startswith("TEST") or value.upper() == "DEMO":
                result["violation"] = True
                result["confidence"] = 0.8
                result["patterns"].append("test_vendor")
                result["recommendation"] = "Test vendor name in production"

        return result

    def _apply_threat_intelligence(self, value: str, context: SecurityContext) -> Dict[str, Any]:
        """Apply threat intelligence to validation."""
        result = {
            "is_threat": False,
            "confidence": 0.0,
            "patterns": [],
            "details": {}
        }

        if not context:
            return result

        # Check malicious IP
        if context.source_ip and context.source_ip in self.malicious_ips:
            result["is_threat"] = True
            result["confidence"] = 0.95
            result["patterns"].append("malicious_ip")
            result["details"]["ip"] = context.source_ip

        # Check suspicious patterns in value
        for pattern, score in self.suspicious_patterns.items():
            if pattern in value.lower():
                result["is_threat"] = True
                result["confidence"] = max(result["confidence"], score)
                result["patterns"].append("suspicious_pattern")
                result["details"]["suspicious_pattern"] = pattern

        return result

    def _validate_file_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Validate file content for malicious signatures."""
        result = {
            "is_threat": False,
            "threat_level": SecurityThreatLevel.LOW,
            "issues": [],
            "recommendations": []
        }

        try:
            # Check file signatures
            content_str = content[:1024].decode('utf-8', errors='ignore').lower()

            # Check for executable signatures
            executable_signatures = [
                b'MZ',  # Windows PE
                b'\x7fELF',  # Linux ELF
                b'#!/bin/',  # Shell scripts
                b'<script',  # JavaScript
                b'<?php',  # PHP
            ]

            for signature in executable_signatures:
                if content.startswith(signature):
                    result["is_threat"] = True
                    result["threat_level"] = SecurityThreatLevel.HIGH
                    result["issues"].append("File contains executable signature")
                    result["recommendations"].append("Executable files not allowed")

            # Check for suspicious text content
            suspicious_text = [
                "system(", "exec(", "eval(", "shell_exec(",
                "passthru(", "document.cookie", "javascript:",
                "<script", "</script>", "onload=", "onerror="
            ]

            for suspicious in suspicious_text:
                if suspicious in content_str:
                    result["is_threat"] = True
                    result["threat_level"] = max(result["threat_level"], SecurityThreatLevel.MEDIUM)
                    result["issues"].append(f"Suspicious content: {suspicious}")
                    result["recommendations"].append("File contains potentially dangerous content")

        except Exception as e:
            logger.error(f"File content validation error: {e}")
            result["issues"].append(f"Content validation error: {str(e)}")

        return result

    def _check_allowlist_rule(self, rule: AllowlistRule, value: str) -> bool:
        """Check if value complies with allowlist rule."""
        if rule.allowlist_type == "exact":
            return value in rule.allowed_values
        elif rule.allowlist_type == "pattern":
            for pattern in rule.allowed_values:
                if re.match(pattern, value, re.IGNORECASE):
                    return True
            return False
        elif rule.allowlist_type == "range":
            # For numeric ranges
            try:
                num_value = float(value)
                for range_spec in rule.allowed_values:
                    if "-" in range_spec:
                        min_val, max_val = map(float, range_spec.split("-"))
                        if min_val <= num_value <= max_val:
                            return True
            except ValueError:
                pass
            return False

        return False

    def _calculate_risk_score(self, result: ValidationResult) -> float:
        """Calculate risk score based on threat analysis."""
        base_score = 0.0

        if result.threat_type:
            # Base score by threat type
            threat_scores = {
                ThreatType.SQL_INJECTION: 9.0,
                ThreatType.XSS: 7.0,
                ThreatType.COMMAND_INJECTION: 8.5,
                ThreatType.PATH_TRAVERSAL: 6.0,
                ThreatType.FILE_UPLOAD_MALWARE: 7.5,
                ThreatType.DATA_EXFILTRATION: 8.0,
                ThreatType.BUSINESS_LOGIC_ABUSE: 5.0,
                ThreatType.RATE_LIMIT_EXCEEDED: 4.0
            }
            base_score = threat_scores.get(result.threat_type, 3.0)

        # Adjust by confidence
        base_score *= result.confidence

        # Adjust by threat level
        level_multipliers = {
            SecurityThreatLevel.LOW: 0.3,
            SecurityThreatLevel.MEDIUM: 0.6,
            SecurityThreatLevel.HIGH: 0.8,
            SecurityThreatLevel.CRITICAL: 1.0
        }
        base_score *= level_multipliers.get(result.threat_level, 0.5)

        # Add bonus for multiple patterns
        if len(result.matched_patterns) > 1:
            base_score *= 1.2

        return min(10.0, max(0.0, base_score))

    def _generate_recommendation(self, result: ValidationResult) -> str:
        """Generate security recommendation based on threat analysis."""
        if result.threat_type == ThreatType.SQL_INJECTION:
            return "SQL injection detected - block request and investigate source"
        elif result.threat_type == ThreatType.XSS:
            return "XSS attack detected - sanitize input and block malicious scripts"
        elif result.threat_type == ThreatType.COMMAND_INJECTION:
            return "Command injection detected - block request and scan system"
        elif result.threat_type == ThreatType.PATH_TRAVERSAL:
            return "Path traversal detected - validate file paths and block access"
        elif result.threat_type == ThreatType.FILE_UPLOAD_MALWARE:
            return "Malicious file upload detected - block file and scan system"
        elif result.threat_type == ThreatType.DATA_EXFILTRATION:
            return "Data exfiltration attempt detected - block request and monitor user"
        elif result.threat_type == ThreatType.BUSINESS_LOGIC_ABUSE:
            return "Business logic abuse detected - review request and implement controls"
        elif result.threat_type == ThreatType.RATE_LIMIT_EXCEEDED:
            return "Rate limit exceeded - throttle requests and consider blocking source"

        return "Security threat detected - review and block if necessary"

    def _compare_threat_levels(self, threat_type1: ThreatType, threat_level2: SecurityThreatLevel) -> int:
        """Compare threat types and levels for severity."""
        threat_priorities = {
            ThreatType.SQL_INJECTION: 10,
            ThreatType.COMMAND_INJECTION: 9,
            ThreatType.DATA_EXFILTRATION: 8,
            ThreatType.FILE_UPLOAD_MALWARE: 7,
            ThreatType.XSS: 6,
            ThreatType.PATH_TRAVERSAL: 5,
            ThreatType.BUSINESS_LOGIC_ABUSE: 4,
            ThreatType.RATE_LIMIT_EXCEEDED: 3,
            ThreatType.AUTHENTICATION_BYPASS: 2,
            ThreatType.PRIVILEGE_ESCALATION: 1
        }

        return threat_priorities.get(threat_type1, 0)

    def _get_threat_level_for_type(self, threat_type: ThreatType) -> SecurityThreatLevel:
        """Get threat level for threat type."""
        threat_level_mapping = {
            ThreatType.SQL_INJECTION: SecurityThreatLevel.CRITICAL,
            ThreatType.COMMAND_INJECTION: SecurityThreatLevel.CRITICAL,
            ThreatType.DATA_EXFILTRATION: SecurityThreatLevel.HIGH,
            ThreatType.FILE_UPLOAD_MALWARE: SecurityThreatLevel.HIGH,
            ThreatType.XSS: SecurityThreatLevel.HIGH,
            ThreatType.PATH_TRAVERSAL: SecurityThreatLevel.HIGH,
            ThreatType.BUSINESS_LOGIC_ABUSE: SecurityThreatLevel.MEDIUM,
            ThreatType.RATE_LIMIT_EXCEEDED: SecurityThreatLevel.MEDIUM,
            ThreatType.AUTHENTICATION_BYPASS: SecurityThreatLevel.HIGH,
            ThreatType.PRIVILEGE_ESCALATION: SecurityThreatLevel.HIGH
        }

        return threat_level_mapping.get(threat_type, SecurityThreatLevel.LOW)