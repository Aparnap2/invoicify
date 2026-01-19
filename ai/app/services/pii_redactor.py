"""
PII Redaction Service

Detects and redacts personally identifiable information (PII) from text.
Uses pattern-based detection with support for Microsoft Presidio-style configuration.

This service:
1. Detects PII entities (SSN, credit cards, emails, phones, etc.)
2. Redacts or masks detected PII
3. Supports multiple redaction modes
4. Returns detection metadata for audit

Usage:
    from app.services.pii_redactor import PIIRedactor, RedactionMode

    redactor = PIIRedactor()
    result = redactor.redact("SSN: 123-45-6789")

    print(result.redacted_text)  # Redacted output
    print(result.findings)       # Detection metadata
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Pattern
import re
import hashlib


class RedactionMode(Enum):
    """Mode for PII redaction."""
    MASK = "mask"       # Replace with asterisks: *****
    REPLACE = "replace"  # Replace with placeholder: [REDACTED]
    HASH = "hash"       # Replace with hash: abc123...
    DELETE = "delete"   # Remove entirely


class PIIType(Enum):
    """Types of PII entities."""
    SSN = "US_SSN"
    CREDIT_CARD = "CREDIT_CARD"
    PHONE = "PHONE_NUMBER"
    EMAIL = "EMAIL_ADDRESS"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    ROUTING_NUMBER = "ROUTING_NUMBER"
    PASSPORT = "PASSPORT"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    IP_ADDRESS = "IP_ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    NAME = "PERSON_NAME"
    ADDRESS = "ADDRESS"
    CUSTOM = "CUSTOM"


@dataclass
class PIIFinding:
    """Represents a detected PII entity."""
    entity_type: str
    text: str
    start: int
    end: int
    score: float = 1.0
    redaction: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "score": self.score,
        }


@dataclass
class RedactionResult:
    """Result of PII redaction operation."""
    original_text: str
    redacted_text: str
    findings: List[PIIFinding]
    mode: RedactionMode
    entities_redacted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "redacted_text": self.redacted_text,
            "findings": [f.to_dict() for f in self.findings],
            "mode": self.mode.value,
            "entities_redacted": self.entities_redacted,
        }


class PIIPattern:
    """Compiled PII pattern for detection."""

    def __init__(self, name: str, pattern: str, score: float = 1.0):
        self.name = name
        self.regex: Pattern[str] = re.compile(pattern, re.IGNORECASE)
        self.score = score


# Pre-defined PII patterns
DEFAULT_PATTERNS = {
    PIIType.SSN: PIIPattern(
        PIIType.SSN.value,
        r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        0.95,
    ),
    PIIType.CREDIT_CARD: PIIPattern(
        PIIType.CREDIT_CARD.value,
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b",
        0.95,
    ),
    PIIType.PHONE: PIIPattern(
        PIIType.PHONE.value,
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        0.85,
    ),
    PIIType.EMAIL: PIIPattern(
        PIIType.EMAIL.value,
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        0.95,
    ),
    PIIType.BANK_ACCOUNT: PIIPattern(
        PIIType.BANK_ACCOUNT.value,
        r"\b\d{8,17}\b",
        0.8,
    ),
    PIIType.ROUTING_NUMBER: PIIPattern(
        PIIType.ROUTING_NUMBER.value,
        r"\b\d{9}\b",
        0.9,
    ),
    PIIType.IP_ADDRESS: PIIPattern(
        PIIType.IP_ADDRESS.value,
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        0.75,
    ),
    PIIType.DATE_OF_BIRTH: PIIPattern(
        PIIType.DATE_OF_BIRTH.value,
        r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b",
        0.85,
    ),
}


class PIIRedactor:
    """
    PII detection and redaction service.

    Uses regex patterns to detect PII entities and redact them
    according to the configured mode.

    Args:
        mode: Redaction mode to use
        custom_patterns: Additional PII patterns to detect
        enabled_types: PII types to detect (default: all)
    """

    def __init__(
        self,
        mode: RedactionMode = RedactionMode.MASK,
        custom_patterns: Optional[List[Dict[str, Any]]] = None,
        enabled_types: Optional[List[PIIType]] = None,
    ):
        self.mode = mode
        self.patterns: Dict[PIIType, PIIPattern] = {}

        # Add default patterns for enabled types
        if enabled_types is None:
            enabled_types = list(PIIType)

        for pii_type in enabled_types:
            if pii_type in DEFAULT_PATTERNS:
                self.patterns[pii_type] = DEFAULT_PATTERNS[pii_type]

        # Add custom patterns
        if custom_patterns:
            for pattern_config in custom_patterns:
                pii_type = PIIType.CUSTOM
                self.patterns[pii_type] = PIIPattern(
                    name=pattern_config.get("name", "CUSTOM"),
                    pattern=pattern_config["pattern"],
                    score=pattern_config.get("score", 0.8),
                )

    def redact(self, text: str) -> RedactionResult:
        """
        Detect and redact PII from text.

        Args:
            text: Input text to redact

        Returns:
            RedactionResult with redacted text and detection metadata
        """
        if not text:
            return RedactionResult(
                original_text=text or "",
                redacted_text=text or "",
                findings=[],
                mode=self.mode,
            )

        findings: List[PIIFinding] = []
        text_parts: List[str] = []
        last_end = 0

        # Find all PII entities
        for pii_type, pattern in self.patterns.items():
            for match in pattern.regex.finditer(text):
                findings.append(
                    PIIFinding(
                        entity_type=pattern.name,
                        text=match.group(),
                        start=match.start(),
                        end=match.end(),
                        score=pattern.score,
                        redaction=self._create_redaction(match.group()),
                    )
                )

        # Sort by position
        findings.sort(key=lambda x: x.start)

        # Remove overlapping findings (keep highest score)
        findings = self._remove_overlaps(findings)

        # Build redacted text
        for finding in findings:
            # Add text before this finding
            text_parts.append(text[last_end:finding.start])
            # Add redacted version
            text_parts.append(finding.redaction)
            last_end = finding.end

        # Add remaining text
        text_parts.append(text[last_end:])

        redacted_text = "".join(text_parts)
        entities_redacted = list(set(f.entity_type for f in findings))

        return RedactionResult(
            original_text=text,
            redacted_text=redacted_text,
            findings=findings,
            mode=self.mode,
            entities_redacted=entities_redacted,
        )

    def _create_redaction(self, text: str) -> str:
        """Create redaction string based on mode."""
        if self.mode == RedactionMode.MASK:
            return "*" * len(text)
        elif self.mode == RedactionMode.REPLACE:
            return "[REDACTED]"
        elif self.mode == RedactionMode.HASH:
            return hashlib.md5(text.encode()).hexdigest()[:8]
        elif self.mode == RedactionMode.DELETE:
            return ""
        return text

    def _remove_overlaps(self, findings: List[PIIFinding]) -> List[PIIFinding]:
        """Remove overlapping findings, keeping highest score."""
        if not findings:
            return []

        # Sort by start position first, then by score descending
        # This ensures we process in order and keep highest score for overlaps
        sorted_findings = sorted(findings, key=lambda x: (x.start, -x.score))

        result: List[PIIFinding] = []
        last_end = 0

        for finding in sorted_findings:
            if finding.start >= last_end:
                result.append(finding)
                last_end = finding.end

        return result

    def detect_only(self, text: str) -> List[PIIFinding]:
        """
        Detect PII without redacting.

        Args:
            text: Input text to analyze

        Returns:
            List of PIIFinding objects
        """
        result = self.redact(text)
        return result.findings

    def redact_invoice(self, invoice_text: str) -> RedactionResult:
        """
        Redact PII specifically for invoice documents.

        Optimized for invoice-specific patterns like bank info and contact details.
        """
        # Enable all financial PII types
        financial_types = [
            PIIType.SSN,
            PIIType.CREDIT_CARD,
            PIIType.BANK_ACCOUNT,
            PIIType.ROUTING_NUMBER,
            PIIType.PHONE,
            PIIType.EMAIL,
        ]

        # Create specialized redactor for invoices
        invoice_redactor = PIIRedactor(
            mode=self.mode,
            enabled_types=financial_types,
        )

        return invoice_redactor.redact(invoice_text)


def create_redactor(
    mode: str = "mask",
    strict: bool = False,
) -> PIIRedactor:
    """
    Factory function to create a PII redactor.

    Args:
        mode: Redaction mode ('mask', 'replace', 'hash', 'delete')
        strict: If True, use more aggressive detection

    Returns:
        Configured PIIRedactor instance
    """
    try:
        redaction_mode = RedactionMode(mode)
    except ValueError:
        redaction_mode = RedactionMode.MASK

    if strict:
        # Enable all PII types with high sensitivity
        enabled_types = list(PIIType)
    else:
        # Standard set of common PII types
        enabled_types = [
            PIIType.SSN,
            PIIType.CREDIT_CARD,
            PIIType.PHONE,
            PIIType.EMAIL,
            PIIType.BANK_ACCOUNT,
            PIIType.ROUTING_NUMBER,
        ]

    return PIIRedactor(mode=redaction_mode, enabled_types=enabled_types)
