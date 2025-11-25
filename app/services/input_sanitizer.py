"""
Comprehensive input sanitization service for defense-in-depth validation.
Implements multi-level sanitization with business-aware rules and performance optimization.
"""

import logging
import re
import html
import urllib.parse
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Pattern
from dataclasses import dataclass
import time

from app.schemas.validation_rules import (
    SanitizationLevel,
    SanitizationResult
)

logger = logging.getLogger(__name__)


@dataclass
class SanitizationStats:
    """Statistics for sanitization operations."""
    total_processed: int = 0
    total_sanitized: int = 0
    sql_injection_blocked: int = 0
    xss_blocked: int = 0
    path_traversal_blocked: int = 0
    command_injection_blocked: int = 0
    total_processing_time_ms: float = 0.0


class InputSanitizer:
    """
    Comprehensive input sanitization service with defense-in-depth protection.

    Features:
    - Multi-level sanitization (LENIENT, NORMAL, STRICT, PARANOID)
    - Business-aware field-specific sanitization
    - HTML/JavaScript neutralization
    - SQL injection pattern removal
    - Path traversal normalization
    - Command injection prevention
    - Character encoding validation and normalization
    - Performance monitoring and caching
    """

    def __init__(self, default_level: SanitizationLevel = SanitizationLevel.NORMAL):
        """Initialize input sanitizer with default sanitization level."""
        self.default_level = default_level
        self.stats = SanitizationStats()

        # Compile regex patterns for performance
        self._compile_patterns()

        # Business field sanitization rules
        self.field_rules = self._initialize_field_rules()

        logger.info(f"InputSanitizer initialized with level: {default_level}")

    def _compile_patterns(self):
        """Compile regex patterns for optimal performance."""
        # SQL injection patterns
        self.sql_patterns = [
            re.compile(r"(?i)(\bDROP\s+TABLE\b|\bDELETE\s+FROM\b|\bTRUNCATE\s+TABLE\b)", re.IGNORECASE),
            re.compile(r"(?i)(\bUNION\s+SELECT\b|\bUNION\s+ALL\s+SELECT\b)", re.IGNORECASE),
            re.compile(r"(?i)('|\s)*OR\s+1\s*=\s*1('|\s)*", re.IGNORECASE),
            re.compile(r"(?i)(\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b)", re.IGNORECASE),
            re.compile(r"(?i)(\bEXEC\b|\bEXECUTE\b|\bSP_EXECUTESQL\b)", re.IGNORECASE),
        ]

        # XSS patterns
        self.xss_patterns = [
            re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL),
            re.compile(r"<\s*iframe[^>]*>.*?<\s*/\s*iframe\s*>", re.IGNORECASE | re.DOTALL),
            re.compile(r"<\s*object[^>]*>.*?<\s*/\s*object\s*>", re.IGNORECASE | re.DOTALL),
            re.compile(r"<\s*embed[^>]*>", re.IGNORECASE),
            re.compile(r"javascript\s*:", re.IGNORECASE),
            re.compile(r"on\w+\s*=", re.IGNORECASE),
            re.compile(r"<\s*img[^>]*on\w+\s*=", re.IGNORECASE),
            re.compile(r"<\s*body[^>]*on\w+\s*=", re.IGNORECASE),
        ]

        # Path traversal patterns
        self.path_traversal_patterns = [
            re.compile(r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c|%252e%252e%252f)", re.IGNORECASE),
            re.compile(r"(?i)(file://|ftp://|http://|https://)", re.IGNORECASE),
            re.compile(r"[\\/]*[a-zA-Z]:[\\/]", re.IGNORECASE),  # Windows paths
        ]

        # Command injection patterns
        self.command_injection_patterns = [
            re.compile(r"(;|\||&|`|\$\(|\${)"),
            re.compile(r"(?i)(\b(cat|ls|dir|whoami|id|pwd|rm|del|type|net\s+user)\b)"),
            re.compile(r"(?i)(\b(ping|wget|curl|nc|netcat)\b)"),
            re.compile(r"(?i)(\b(rm\s+-rf|del\s+\/s|format)\b)"),
        ]

        # Control characters and dangerous unicode
        self.control_char_pattern = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
        self.dangerous_unicode_pattern = re.compile(r'[\u2028-\u2029\uFFF0-\uFFFF]')

        # Whitespace normalization
        self.whitespace_pattern = re.compile(r'\s+')
        self.newline_pattern = re.compile(r'[\r\n]+')

    def _initialize_field_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize field-specific sanitization rules."""
        return {
            "vendor_name": {
                "max_length": 100,
                "allowed_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .-&'@",
                "remove_patterns": ["<script", "</script>", "javascript:", "onload=", "onerror="],
                "normalize_case": True,
                "trim_whitespace": True
            },
            "invoice_number": {
                "max_length": 50,
                "allowed_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_/",
                "remove_patterns": [";", "--", "/*", "*/", "DROP", "DELETE", "UNION"],
                "normalize_case": False,
                "trim_whitespace": True
            },
            "total_amount": {
                "max_length": 20,
                "allowed_chars": "0123456789.,",
                "remove_patterns": [";", "--", "DELETE", "DROP", "script"],
                "normalize_numeric": True,
                "remove_currency_symbols": True
            },
            "description": {
                "max_length": 500,
                "allowed_chars": None,  # Allow most characters but sanitize HTML
                "remove_patterns": ["<script", "</script>", "javascript:", "onload=", "onerror="],
                "escape_html": True,
                "trim_whitespace": True
            },
            "email": {
                "max_length": 100,
                "allowed_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.@-_+",
                "remove_patterns": ["<", ">", "script", "javascript"],
                "normalize_case": False,
                "trim_whitespace": True
            },
            "file_path": {
                "max_length": 255,
                "allowed_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_./\\",
                "normalize_path": True,
                "remove_traversal": True,
                "trim_whitespace": True
            }
        }

    def sanitize(
        self,
        input_value: Any,
        level: Optional[SanitizationLevel] = None,
        field_name: Optional[str] = None
    ) -> SanitizationResult:
        """
        Sanitize input value with specified security level.

        Args:
            input_value: Value to sanitize
            level: Sanitization level (uses default if not specified)
            field_name: Optional field name for business-aware rules

        Returns:
            SanitizationResult with sanitized value and metadata
        """
        start_time = time.time()

        if input_value is None:
            return SanitizationResult(
                success=True,
                sanitized_value="",
                original_value="",
                sanitization_level=level or self.default_level
            )

        original_value = str(input_value)
        current_value = original_value
        sanitization_level = level or self.default_level

        removed_content = []
        modified_content = []
        warnings = []

        try:
            # Convert to string and normalize Unicode
            current_value = self._normalize_unicode(current_value)

            # Apply field-specific rules if provided
            if field_name and field_name in self.field_rules:
                current_value = self._apply_field_rules(
                    current_value, field_name, removed_content, modified_content, warnings
                )

            # Level-specific sanitization
            if sanitization_level == SanitizationLevel.PARANOID:
                current_value = self._paranoid_sanitization(
                    current_value, removed_content, modified_content, warnings
                )
            elif sanitization_level == SanitizationLevel.STRICT:
                current_value = self._strict_sanitization(
                    current_value, removed_content, modified_content, warnings
                )
            elif sanitization_level == SanitizationLevel.NORMAL:
                current_value = self._normal_sanitization(
                    current_value, removed_content, modified_content, warnings
                )
            elif sanitization_level == SanitizationLevel.LENIENT:
                current_value = self._lenient_sanitization(
                    current_value, removed_content, modified_content, warnings
                )

            # Final validation and cleanup
            current_value = self._final_cleanup(current_value, warnings)

            processing_time = (time.time() - start_time) * 1000
            self._update_stats(original_value, current_value, processing_time)

            return SanitizationResult(
                success=True,
                sanitized_value=current_value,
                original_value=original_value,
                sanitization_level=sanitization_level,
                removed_content=removed_content,
                modified_content=modified_content,
                warnings=warnings,
                is_safe_for_database=self._is_safe_for_database(current_value),
                is_safe_for_display=self._is_safe_for_display(current_value),
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Sanitization error: {e}")
            processing_time = (time.time() - start_time) * 1000

            return SanitizationResult(
                success=False,
                sanitized_value="",
                original_value=original_value,
                sanitization_level=sanitization_level,
                warnings=[f"Sanitization error: {str(e)}"],
                processing_time_ms=processing_time
            )

    def sanitize_invoice_number(self, invoice_number: Any) -> str:
        """Sanitize invoice number with business-specific rules."""
        result = self.sanitize(invoice_number, SanitizationLevel.STRICT, "invoice_number")
        return result.sanitized_value

    def sanitize_vendor_name(self, vendor_name: Any) -> str:
        """Sanitize vendor name with business-specific rules."""
        result = self.sanitize(vendor_name, SanitizationLevel.NORMAL, "vendor_name")
        return result.sanitized_value

    def sanitize_amount(self, amount: Any) -> str:
        """Sanitize amount field with numeric-focused rules."""
        result = self.sanitize(amount, SanitizationLevel.STRICT, "total_amount")
        return result.sanitized_value

    def sanitize_description(self, description: Any) -> str:
        """Sanitize description with HTML-aware rules."""
        result = self.sanitize(description, SanitizationLevel.NORMAL, "description")
        return result.sanitized_value

    def sanitize_file_path(self, file_path: Any) -> str:
        """Sanitize file path with traversal prevention."""
        result = self.sanitize(file_path, SanitizationLevel.STRICT, "file_path")
        return result.sanitized_value

    def sanitize_email(self, email: Any) -> str:
        """Sanitize email address."""
        result = self.sanitize(email, SanitizationLevel.NORMAL, "email")
        return result.sanitized_value

    def validate_encoding(self, value: str) -> bool:
        """Validate that string has proper UTF-8 encoding."""
        try:
            # Try to encode and decode as UTF-8
            value.encode('utf-8').decode('utf-8')
            return True
        except UnicodeError:
            return False

    def is_safe_for_database(self, value: str) -> bool:
        """Check if value is safe for database operations."""
        # Check for SQL injection patterns
        for pattern in self.sql_patterns:
            if pattern.search(value):
                return False

        # Check for unescaped quotes
        if "';" in value or "\";" in value:
            return False

        return True

    def is_safe_for_display(self, value: str) -> bool:
        """Check if value is safe for display in UI."""
        # Check for HTML/JavaScript patterns
        for pattern in self.xss_patterns:
            if pattern.search(value):
                return False

        # Check for control characters
        if self.control_char_pattern.search(value):
            return False

        return True

    def is_safe_file_path(self, value: str) -> bool:
        """Check if file path is safe."""
        # Check for path traversal
        for pattern in self.path_traversal_patterns:
            if pattern.search(value):
                return False

        # Check for dangerous protocols
        if any(protocol in value.lower() for protocol in ["file://", "ftp://", "http://", "https://"]):
            return False

        return True

    def get_sanitization_stats(self) -> Dict[str, Any]:
        """Get sanitization operation statistics."""
        return {
            "total_processed": self.stats.total_processed,
            "total_sanitized": self.stats.total_sanitized,
            "sql_injection_blocked": self.stats.sql_injection_blocked,
            "xss_blocked": self.stats.xss_blocked,
            "path_traversal_blocked": self.stats.path_traversal_blocked,
            "command_injection_blocked": self.stats.command_injection_blocked,
            "total_processing_time_ms": self.stats.total_processing_time_ms,
            "average_processing_time_ms": (
                self.stats.total_processing_time_ms / max(self.stats.total_processed, 1)
            ),
            "sanitization_rate": (
                self.stats.total_sanitized / max(self.stats.total_processed, 1)
            ) * 100
        }

    def reset_stats(self):
        """Reset sanitization statistics."""
        self.stats = SanitizationStats()

    # Private methods for internal sanitization logic

    def _normalize_unicode(self, value: str) -> str:
        """Normalize Unicode characters."""
        # Normalize to NFKC form (compatibility decomposition + recomposition)
        normalized = unicodedata.normalize('NFKC', value)

        # Remove dangerous Unicode characters
        normalized = self.dangerous_unicode_pattern.sub('', normalized)

        return normalized

    def _apply_field_rules(
        self,
        value: str,
        field_name: str,
        removed_content: List[str],
        modified_content: List[str],
        warnings: List[str]
    ) -> str:
        """Apply field-specific sanitization rules."""
        rules = self.field_rules.get(field_name, {})
        current_value = value

        # Apply max length
        if "max_length" in rules and len(current_value) > rules["max_length"]:
            current_value = current_value[:rules["max_length"]]
            modified_content.append(f"Truncated to {rules['max_length']} characters")

        # Remove specific patterns
        if "remove_patterns" in rules:
            for pattern in rules["remove_patterns"]:
                if pattern.lower() in current_value.lower():
                    current_value = current_value.replace(pattern, "")
                    removed_content.append(f"Removed pattern: {pattern}")

        # Apply allowed characters filter
        if "allowed_chars" in rules:
            filtered_chars = [c for c in current_value if c in rules["allowed_chars"]]
            filtered_value = ''.join(filtered_chars)
            if len(filtered_value) != len(current_value):
                removed_content.append("Filtered disallowed characters")
                current_value = filtered_value

        # Normalize case
        if rules.get("normalize_case", False):
            current_value = current_value.title()
            modified_content.append("Normalized case")

        # Normalize numeric values
        if rules.get("normalize_numeric", False):
            # Remove currency symbols and normalize numeric format
            current_value = re.sub(r'[^\d.]', '', current_value)
            try:
                if current_value:
                    float_val = float(current_value)
                    current_value = f"{float_val:.2f}"
                    modified_content.append("Normalized numeric format")
            except ValueError:
                current_value = "0.00"
                warnings.append("Invalid numeric value, set to 0.00")

        # Remove currency symbols
        if rules.get("remove_currency_symbols", False):
            current_value = re.sub(r'[$€£¥₹]', '', current_value)
            modified_content.append("Removed currency symbols")

        # Escape HTML
        if rules.get("escape_html", False):
            current_value = html.escape(current_value)
            modified_content.append("Escaped HTML entities")

        # Trim whitespace
        if rules.get("trim_whitespace", False):
            current_value = self.whitespace_pattern.sub(' ', current_value).strip()
            modified_content.append("Trimmed whitespace")

        # Normalize path
        if rules.get("normalize_path", False):
            current_value = self._normalize_file_path(current_value)
            modified_content.append("Normalized file path")

        # Remove path traversal
        if rules.get("remove_traversal", False):
            current_value = self._remove_path_traversal(current_value)
            modified_content.append("Removed path traversal")

        return current_value

    def _lenient_sanitization(
        self,
        value: str,
        removed_content: List[str],
        modified_content: List[str],
        warnings: List[str]
    ) -> str:
        """Apply lenient sanitization (basic protection)."""
        current_value = value

        # Basic HTML escaping for obvious script tags
        if "<script>" in current_value.lower():
            current_value = current_value.replace("<script>", "&lt;script&gt;")
            removed_content.append("Removed script tag")

        # Remove obvious SQL injection patterns
        for pattern in self.sql_patterns[:2]:  # Only most dangerous patterns
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed SQL injection pattern")
                self.stats.sql_injection_blocked += 1

        return current_value

    def _normal_sanitization(
        self,
        value: str,
        removed_content: List[str],
        modified_content: List[str],
        warnings: List[str]
    ) -> str:
        """Apply normal sanitization (balanced protection)."""
        current_value = value

        # Remove all SQL injection patterns
        for pattern in self.sql_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed SQL injection pattern")
                self.stats.sql_injection_blocked += 1

        # Remove XSS patterns
        for pattern in self.xss_patterns[:5]:  # Most common XSS patterns
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed XSS pattern")
                self.stats.xss_blocked += 1

        # Remove path traversal
        for pattern in self.path_traversal_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed path traversal pattern")
                self.stats.path_traversal_blocked += 1

        # Remove obvious command injection
        for pattern in self.command_injection_patterns[:2]:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed command injection pattern")
                self.stats.command_injection_blocked += 1

        # Normalize whitespace
        current_value = self.whitespace_pattern.sub(' ', current_value).strip()
        modified_content.append("Normalized whitespace")

        return current_value

    def _strict_sanitization(
        self,
        value: str,
        removed_content: List[str],
        modified_content: List[str],
        warnings: List[str]
    ) -> str:
        """Apply strict sanitization (comprehensive protection)."""
        current_value = value

        # Remove all SQL injection patterns
        for pattern in self.sql_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed SQL injection pattern")
                self.stats.sql_injection_blocked += 1

        # Remove all XSS patterns
        for pattern in self.xss_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed XSS pattern")
                self.stats.xss_blocked += 1

        # Remove all path traversal patterns
        for pattern in self.path_traversal_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed path traversal pattern")
                self.stats.path_traversal_blocked += 1

        # Remove all command injection patterns
        for pattern in self.command_injection_patterns:
            if pattern.search(current_value):
                current_value = pattern.sub('', current_value)
                removed_content.append("Removed command injection pattern")
                self.stats.command_injection_blocked += 1

        # Remove control characters
        if self.control_char_pattern.search(current_value):
            current_value = self.control_char_pattern.sub('', current_value)
            removed_content.append("Removed control characters")

        # URL encode potentially dangerous characters
        current_value = urllib.parse.quote(current_value, safe=' ')
        modified_content.append("URL encoded special characters")

        # Normalize whitespace aggressively
        current_value = self.newline_pattern.sub(' ', current_value)
        current_value = self.whitespace_pattern.sub(' ', current_value).strip()
        modified_content.append("Aggressively normalized whitespace")

        return current_value

    def _paranoid_sanitization(
        self,
        value: str,
        removed_content: List[str],
        modified_content: List[str],
        warnings: List[str]
    ) -> str:
        """Apply paranoid sanitization (maximum protection)."""
        current_value = value

        # Start with strict sanitization
        current_value = self._strict_sanitization(
            current_value, removed_content, modified_content, warnings
        )

        # Additional paranoid measures

        # Remove any remaining non-alphanumeric characters except basic punctuation
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,-_@")
        filtered_chars = [c for c in current_value if c in allowed_chars]
        filtered_value = ''.join(filtered_chars)

        if len(filtered_value) != len(current_value):
            removed_content.append("Removed non-allowed characters in paranoid mode")
            current_value = filtered_value

        # Convert to lowercase to prevent case-based attacks
        original_case = current_value
        current_value = current_value.lower()
        if current_value != original_case:
            modified_content.append("Converted to lowercase in paranoid mode")

        # Limit length very aggressively
        if len(current_value) > 100:
            current_value = current_value[:100]
            removed_content.append("Truncated to 100 characters in paranoid mode")

        # Add warning about paranoid mode
        warnings.append("Input processed in paranoid mode - functionality may be limited")

        return current_value

    def _normalize_file_path(self, file_path: str) -> str:
        """Normalize file path to prevent directory traversal."""
        # Replace backslashes with forward slashes
        normalized = file_path.replace('\\', '/')

        # Remove multiple consecutive slashes
        normalized = re.sub(r'/+', '/', normalized)

        # Remove leading/trailing slashes
        normalized = normalized.strip('/')

        # URL decode if needed
        try:
            normalized = urllib.parse.unquote(normalized)
        except:
            pass

        return normalized

    def _remove_path_traversal(self, value: str) -> str:
        """Remove path traversal patterns."""
        current_value = value

        # Remove encoded and unencoded traversal patterns
        traversal_patterns = [
            '../', '..\\', '%2e%2e%2f', '%2e%2e%5c',
            '%252e%252e%252f', '%252e%252e%255c',
            '....//', '....\\\\'
        ]

        for pattern in traversal_patterns:
            current_value = current_value.replace(pattern, '')

        return current_value

    def _final_cleanup(self, value: str, warnings: List[str]) -> str:
        """Final cleanup and validation."""
        current_value = value

        # Remove leading/trailing whitespace
        current_value = current_value.strip()

        # Validate encoding
        if not self.validate_encoding(current_value):
            # Try to fix encoding issues
            try:
                current_value = current_value.encode('ascii', errors='ignore').decode('ascii')
                warnings.append("Fixed encoding issues, non-ASCII characters removed")
            except:
                current_value = ""
                warnings.append("Severe encoding issues, value cleared")

        # Ensure result is not empty if original had content
        if not current_value and value.strip():
            current_value = "[SANITIZED]"
            warnings.append("Original value was too dangerous, replaced with placeholder")

        return current_value

    def _update_stats(self, original_value: str, sanitized_value: str, processing_time: float):
        """Update sanitization statistics."""
        self.stats.total_processed += 1
        self.stats.total_processing_time_ms += processing_time

        if original_value != sanitized_value:
            self.stats.total_sanitized += 1

    def _is_safe_for_database(self, value: str) -> bool:
        """Check if value is safe for database operations."""
        # Basic check for dangerous SQL patterns
        dangerous_patterns = ["'", '"', ';', '--', '/*', '*/', 'DROP', 'DELETE', 'UNION', 'EXEC']

        for pattern in dangerous_patterns:
            if pattern in value.upper():
                return False

        return True

    def _is_safe_for_display(self, value: str) -> bool:
        """Check if value is safe for display in UI."""
        # Check for HTML/JavaScript patterns
        dangerous_patterns = ['<', '>', '&', '"', "'", 'javascript:', 'onload', 'onerror']

        for pattern in dangerous_patterns:
            if pattern in value.lower():
                return False

        return True