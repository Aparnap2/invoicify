"""
Security validation rule schemas and data structures for defense-in-depth validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Pattern
from pydantic import BaseModel, Field, validator
import re


class SecurityThreatLevel(str, Enum):
    """Security threat severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SanitizationLevel(str, Enum):
    """Input sanitization levels."""
    LENIENT = "lenient"
    NORMAL = "normal"
    STRICT = "strict"
    PARANOID = "paranoid"


class ValidationLayer(str, Enum):
    """Defense-in-depth validation layers."""
    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class ThreatType(str, Enum):
    """Types of security threats."""
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    FILE_UPLOAD_MALWARE = "file_upload_malware"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DATA_EXFILTRATION = "data_exfiltration"
    BUSINESS_LOGIC_ABUSE = "business_logic_abuse"
    AUTHENTICATION_BYPASS = "authentication_bypass"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class SecurityPattern(BaseModel):
    """Security threat pattern definition."""
    name: str
    description: str
    threat_type: ThreatType
    threat_level: SecurityThreatLevel
    pattern: str
    pattern_type: str = "regex"  # regex, string, function
    is_case_sensitive: bool = True
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


class AllowlistRule(BaseModel):
    """Allowlist validation rule for critical fields."""
    field_name: str
    allowed_values: List[str]
    allowlist_type: str = "exact"  # exact, pattern, range
    is_strict: bool = True
    default_value: Optional[str] = None
    description: str = ""
    enabled: bool = True

    @validator('allowed_values')
    def validate_allowed_values(cls, v):
        if not v:
            raise ValueError('allowed_values cannot be empty')
        return v


class SecurityRule(BaseModel):
    """Comprehensive security validation rule."""
    name: str
    category: str
    layer: ValidationLayer
    description: str
    threat_type: Optional[ThreatType] = None
    threat_level: SecurityThreatLevel = SecurityThreatLevel.MEDIUM

    # Rule configuration
    enabled: bool = True
    priority: int = Field(default=5, ge=1, le=10)

    # Patterns and conditions
    patterns: List[SecurityPattern] = Field(default_factory=list)
    allowlist_rules: List[AllowlistRule] = Field(default_factory=list)
    denylist_patterns: List[str] = Field(default_factory=list)

    # Validation parameters
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    allowed_characters: Optional[str] = None
    forbidden_characters: Optional[str] = None

    # Business rules
    business_rules: Dict[str, Any] = Field(default_factory=dict)

    # Metadata
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class ValidationRuleSchema(BaseModel):
    """Complete validation rule schema for structured security validation."""
    version: str
    description: str
    rules: List[SecurityRule]

    # Global configuration
    global_settings: Dict[str, Any] = Field(default_factory=lambda: {
        "strict_mode": False,
        "fail_fast": False,
        "max_validation_time_ms": 5000,
        "enable_security_monitoring": True,
        "log_all_validations": False
    })

    # Layer-specific settings
    layer_settings: Dict[str, Dict[str, Any]] = Field(default_factory=lambda: {
        "syntactic": {
            "required_fields": ["vendor_name", "invoice_number", "total_amount"],
            "field_formats": {
                "invoice_number": r"^[A-Z0-9\-_]{3,50}$",
                "total_amount": r"^\d{1,10}(\.\d{2})?$",
                "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            }
        },
        "semantic": {
            "business_rules": {
                "max_invoice_amount": 1000000,
                "max_invoice_age_days": 365,
                "required_vendor_fields": ["name", "tax_id"]
            }
        },
        "security": {
            "threat_detection_enabled": True,
            "block_suspicious_requests": True,
            "rate_limit_per_minute": 100,
            "max_file_size_mb": 50
        },
        "compliance": {
            "gdpr_enabled": True,
            "pci_dss_enabled": False,
            "audit_logging": True,
            "data_retention_days": 2555
        }
    })

    class Config:
        use_enum_values = True


class ThreatDetectionResult(BaseModel):
    """Result of threat detection analysis."""
    is_threat: bool
    threat_type: Optional[ThreatType] = None
    threat_level: SecurityThreatLevel
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_patterns: List[str] = Field(default_factory=list)
    field: Optional[str] = None
    original_value: Optional[str] = None
    sanitized_value: Optional[str] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=10.0)
    recommendation: str = ""
    requires_immediate_action: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class SanitizationResult(BaseModel):
    """Result of input sanitization process."""
    success: bool
    sanitized_value: str
    original_value: str
    sanitization_level: SanitizationLevel
    removed_content: List[str] = Field(default_factory=list)
    modified_content: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_safe_for_database: bool = True
    is_safe_for_display: bool = True
    processing_time_ms: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class SecurityEvent(BaseModel):
    """Security event for monitoring and alerting."""
    id: Optional[str] = None
    event_type: str
    threat_type: Optional[ThreatType] = None
    threat_level: SecurityThreatLevel
    source_ip: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    endpoint: Optional[str] = None
    field: Optional[str] = None

    # Event details
    original_value: Optional[str] = None
    detected_pattern: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None

    # Additional context
    details: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class SecurityAlert(BaseModel):
    """Security alert generated from event analysis."""
    id: Optional[str] = None
    title: str
    description: str
    severity: SecurityThreatLevel
    alert_type: str

    # Source information
    source_ips: List[str] = Field(default_factory=list)
    affected_users: List[str] = Field(default_factory=list)
    affected_endpoints: List[str] = Field(default_factory=list)

    # Alert details
    event_count: int = 0
    time_window_minutes: int = 60
    first_event: Optional[datetime] = None
    last_event: Optional[datetime] = None

    # Response information
    requires_immediate_action: bool = False
    auto_resolved: bool = False
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Recommended actions
    recommended_actions: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class ThreatStatistics(BaseModel):
    """Threat statistics for security monitoring."""
    total_events: int = 0
    events_by_type: Dict[str, int] = Field(default_factory=dict)
    events_by_level: Dict[str, int] = Field(default_factory=dict)
    events_by_source: Dict[str, int] = Field(default_factory=dict)

    # Specific threat counts
    sql_injection_attempts: int = 0
    xss_attempts: int = 0
    path_traversal_attempts: int = 0
    command_injection_attempts: int = 0
    file_upload_attempts: int = 0
    rate_limit_violations: int = 0

    # Trending data
    hourly_counts: Dict[str, int] = Field(default_factory=dict)
    daily_counts: Dict[str, int] = Field(default_factory=dict)

    # Risk metrics
    current_risk_score: float = Field(default=0.0, ge=0.0, le=10.0)
    risk_trend: str = "stable"  # increasing, decreasing, stable

    # Response metrics
    alerts_generated: int = 0
    auto_blocked_requests: int = 0
    manual_interventions: int = 0

    class Config:
        use_enum_values = True


class AttackPattern(BaseModel):
    """Detected attack pattern for correlation analysis."""
    pattern_type: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    description: str

    # Pattern details
    event_count: int = 0
    affected_sources: List[str] = Field(default_factory=list)
    affected_fields: List[str] = Field(default_factory=list)
    time_span_minutes: int = 0

    # Pattern characteristics
    is_coordinated: bool = False
    attack_vector: Optional[str] = None
    target_systems: List[str] = Field(default_factory=list)

    # Timeline
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    # Response
    severity: SecurityThreatLevel = SecurityThreatLevel.MEDIUM
    recommended_response: str = ""
    auto_mitigation_triggered: bool = False

    class Config:
        use_enum_values = True


class RiskScore(BaseModel):
    """Comprehensive risk score calculation."""
    overall_score: float = Field(default=0.0, ge=0.0, le=10.0)
    trend: str = "stable"  # increasing, decreasing, stable

    # Component scores
    sql_injection_risk: float = Field(default=0.0, ge=0.0, le=10.0)
    xss_risk: float = Field(default=0.0, ge=0.0, le=10.0)
    data_exfiltration_risk: float = Field(default=0.0, ge=0.0, le=10.0)
    authentication_risk: float = Field(default=0.0, ge=0.0, le=10.0)
    business_logic_risk: float = Field(default=0.0, ge=0.0, le=10.0)

    # Risk factors
    failed_authentication_count: int = 0
    suspicious_source_count: int = 0
    blocked_request_count: int = 0
    unusual_pattern_count: int = 0

    # Context
    calculation_time: datetime = Field(default_factory=datetime.now)
    time_window_hours: int = 24

    class Config:
        use_enum_values = True


class DefenseInDepthResult(BaseModel):
    """Complete defense-in-depth validation result."""

    # Overall result
    passed: bool
    overall_threat_level: SecurityThreatLevel
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Layer results
    syntactic_validation: Optional[Dict[str, Any]] = None
    semantic_validation: Optional[Dict[str, Any]] = None
    security_validation: Optional[Dict[str, Any]] = None
    compliance_validation: Optional[Dict[str, Any]] = None

    # Security analysis
    threat_detections: List[ThreatDetectionResult] = Field(default_factory=list)
    sanitization_results: List[SanitizationResult] = Field(default_factory=list)
    security_events: List[SecurityEvent] = Field(default_factory=list)

    # Processing information
    processing_time_ms: float
    layers_executed: List[ValidationLayer] = Field(default_factory=list)
    rules_applied: List[str] = Field(default_factory=list)

    # Recommendations
    security_recommendations: List[str] = Field(default_factory=list)
    blocked_operations: List[str] = Field(default_factory=list)

    # Metadata
    validated_at: datetime = Field(default_factory=datetime.now)
    validator_version: str = "1.0.0"
    correlation_id: Optional[str] = None

    class Config:
        use_enum_values = True


# Predefined security patterns for common threats
SQL_INJECTION_PATTERNS = [
    SecurityPattern(
        name="SQL Injection - DROP TABLE",
        description="Detects SQL DROP TABLE injection attempts",
        threat_type=ThreatType.SQL_INJECTION,
        threat_level=SecurityThreatLevel.CRITICAL,
        pattern=r"(?i)(\bDROP\s+TABLE\b|\bDELETE\s+FROM\b|\bTRUNCATE\s+TABLE\b)",
        confidence=0.95,
        tags=["sql_injection", "destructive", "critical"]
    ),
    SecurityPattern(
        name="SQL Injection - UNION SELECT",
        description="Detects SQL UNION SELECT injection attempts",
        threat_type=ThreatType.SQL_INJECTION,
        threat_level=SecurityThreatLevel.HIGH,
        pattern=r"(?i)(\bUNION\s+SELECT\b|\bUNION\s+ALL\s+SELECT\b)",
        confidence=0.90,
        tags=["sql_injection", "data_exfiltration", "high"]
    ),
    SecurityPattern(
        name="SQL Injection - OR 1=1",
        description="Detects classic SQL injection bypass attempts",
        threat_type=ThreatType.SQL_INJECTION,
        threat_level=SecurityThreatLevel.HIGH,
        pattern=r"(?i)('|\s)*OR\s+1\s*=\s*1('|\s)*",
        confidence=0.85,
        tags=["sql_injection", "authentication_bypass", "high"]
    ),
]

XSS_PATTERNS = [
    SecurityPattern(
        name="XSS - Script Tag",
        description="Detects script tag injection",
        threat_type=ThreatType.XSS,
        threat_level=SecurityThreatLevel.HIGH,
        pattern=r"(?i)<\s*script[^>]*>.*?<\s*/\s*script\s*>",
        confidence=0.95,
        tags=["xss", "script_injection", "high"]
    ),
    SecurityPattern(
        name="XSS - JavaScript Protocol",
        description="Detects javascript: protocol injection",
        threat_type=ThreatType.XSS,
        threat_level=SecurityThreatLevel.MEDIUM,
        pattern=r"(?i)javascript\s*:",
        confidence=0.80,
        tags=["xss", "protocol_injection", "medium"]
    ),
    SecurityPattern(
        name="XSS - Event Handler",
        description="Detects event handler injection",
        threat_type=ThreatType.XSS,
        threat_level=SecurityThreatLevel.MEDIUM,
        pattern=r"(?i)on\w+\s*=",
        confidence=0.75,
        tags=["xss", "event_handler", "medium"]
    ),
]

PATH_TRAVERSAL_PATTERNS = [
    SecurityPattern(
        name="Path Traversal - Directory Traversal",
        description="Detects directory traversal attempts",
        threat_type=ThreatType.PATH_TRAVERSAL,
        threat_level=SecurityThreatLevel.HIGH,
        pattern=r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
        confidence=0.90,
        tags=["path_traversal", "file_access", "high"]
    ),
    SecurityPattern(
        name="Path Traversal - File Protocol",
        description="Detects file protocol usage",
        threat_type=ThreatType.PATH_TRAVERSAL,
        threat_level=SecurityThreatLevel.MEDIUM,
        pattern=r"(?i)(file://|ftp://|http://|https://)",
        confidence=0.70,
        tags=["path_traversal", "protocol", "medium"]
    ),
]

COMMAND_INJECTION_PATTERNS = [
    SecurityPattern(
        name="Command Injection - Shell Commands",
        description="Detects shell command injection",
        threat_type=ThreatType.COMMAND_INJECTION,
        threat_level=SecurityThreatLevel.CRITICAL,
        pattern=r"(;|\||&|`|\$\(|\${)",
        confidence=0.80,
        tags=["command_injection", "shell", "critical"]
    ),
    SecurityPattern(
        name="Command Injection - Common Commands",
        description="Detects common command injection commands",
        threat_type=ThreatType.COMMAND_INJECTION,
        threat_level=SecurityThreatLevel.HIGH,
        pattern=r"(?i)(\b(cat|ls|dir|whoami|id|pwd|rm|del|type)\b)",
        confidence=0.75,
        tags=["command_injection", "system_commands", "high"]
    ),
]

# Default security rule collections
DEFAULT_SECURITY_RULES = [
    SecurityRule(
        name="SQL Injection Protection",
        category="database_security",
        layer=ValidationLayer.SECURITY,
        description="Protects against SQL injection attacks",
        threat_type=ThreatType.SQL_INJECTION,
        threat_level=SecurityThreatLevel.CRITICAL,
        patterns=SQL_INJECTION_PATTERNS,
        priority=10,
        tags=["sql_injection", "database", "critical"]
    ),
    SecurityRule(
        name="XSS Protection",
        category="web_security",
        layer=ValidationLayer.SECURITY,
        description="Protects against cross-site scripting attacks",
        threat_type=ThreatType.XSS,
        threat_level=SecurityThreatLevel.HIGH,
        patterns=XSS_PATTERNS,
        priority=9,
        tags=["xss", "web_security", "high"]
    ),
    SecurityRule(
        name="Path Traversal Protection",
        category="file_security",
        layer=ValidationLayer.SECURITY,
        description="Protects against path traversal attacks",
        threat_type=ThreatType.PATH_TRAVERSAL,
        threat_level=SecurityThreatLevel.HIGH,
        patterns=PATH_TRAVERSAL_PATTERNS,
        priority=8,
        tags=["path_traversal", "file_security", "high"]
    ),
    SecurityRule(
        name="Command Injection Protection",
        category="system_security",
        layer=ValidationLayer.SECURITY,
        description="Protects against command injection attacks",
        threat_type=ThreatType.COMMAND_INJECTION,
        threat_level=SecurityThreatLevel.CRITICAL,
        patterns=COMMAND_INJECTION_PATTERNS,
        priority=10,
        tags=["command_injection", "system_security", "critical"]
    ),
]

# Default allowlist rules for critical fields
DEFAULT_ALLOWLIST_RULES = [
    AllowlistRule(
        field_name="currency",
        allowed_values=["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"],
        allowlist_type="exact",
        is_strict=True,
        description="Allowed currency codes"
    ),
    AllowlistRule(
        field_name="country_code",
        allowed_values=["US", "CA", "GB", "DE", "FR", "IT", "ES", "NL", "AU", "JP"],
        allowlist_type="exact",
        is_strict=True,
        description="Allowed country codes"
    ),
    AllowlistRule(
        field_name="payment_terms",
        allowed_values=["NET30", "NET60", "NET90", "COD", "IMMEDIATE", "PIA"],
        allowlist_type="exact",
        is_strict=False,
        description="Allowed payment terms"
    ),
]