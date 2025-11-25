# Security Challenge: Defense-in-Depth Middleware

## 🎯 Challenge Overview

You need to build a comprehensive security middleware system for an API that processes sensitive financial data (invoices, payments, vendor information). The system must implement defense-in-depth security principles and handle multiple security threats.

## 📋 Context

The AP Intake system processes:
- **Sensitive Data**: Vendor information, payment amounts, banking details
- **Compliance Requirements**: GDPR, PCI-DSS, SOX compliance
- **Threat Model**: Web-based attacks, injection attacks, data exfiltration
- **Performance Requirements**: Must not significantly impact API response times

## 🛡️ Requirements

### Core Security Features
1. **Input Validation & Sanitization**
   - Detect and prevent injection attacks (SQL, XSS, Command)
   - Validate data formats and ranges
   - Sanitize user inputs before processing

2. **Security Headers**
   - Implement comprehensive security headers
   - Support environment-specific configurations
   - Handle CSP (Content Security Policy) properly

3. **Threat Detection**
   - Real-time threat detection and blocking
   - Rate limiting and abuse prevention
   - Logging and alerting for security events

4. **Compliance Validation**
   - Detect and mask sensitive data (PII, PCI)
   - Ensure audit logging for compliance
   - Data retention and privacy controls

## 🏗️ Architecture Requirements

- **Middleware Pattern**: Must be implemented as FastAPI middleware
- **Configuration**: Environment-aware security settings
- **Performance**: Minimal impact on request processing
- **Monitoring**: Comprehensive security event logging
- **Extensibility**: Easy to add new security rules

## 🔧 Starter Code

```python
# security_challenge_starter.py
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityEvent:
    threat_type: str
    threat_level: ThreatLevel
    source_ip: str
    user_agent: str
    request_path: str
    detected_at: str
    details: Dict

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    TODO: Implement comprehensive security middleware
    """

    def __init__(self, app, environment: str = "production"):
        super().__init__(app)
        self.environment = environment
        self.logger = logging.getLogger(__name__)

        # TODO: Initialize security configurations

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        TODO: Implement comprehensive security checks
        """
        # Get request metadata
        source_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        request_path = request.url.path

        # TODO: Implement security checks

        # Process request
        response = await call_next(request)

        # TODO: Add security headers

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"
```

## 🎯 Your Tasks

### Task 1: Input Sanitization Engine (25 points)
Implement comprehensive input validation and sanitization:

- **Injection Detection**: SQL, XSS, Command injection patterns
- **Data Validation**: Format, length, and range validation
- **Sanitization**: Safe data cleaning and normalization
- **Performance**: Efficient pattern matching and caching

### Task 2: Security Headers Implementation (25 points)
Build environment-aware security headers:

- **Standard Headers**: HSTS, CSP, XSS Protection, etc.
- **Environment Configs**: Development vs staging vs production
- **Dynamic Headers**: Request-specific security headers
- **Performance**: Minimal overhead header generation

### Task 3: Threat Detection System (25 points)
Create real-time threat detection and response:

- **Pattern Matching**: Advanced regex and heuristic detection
- **Rate Limiting**: Request rate and frequency monitoring
- **Event Logging**: Comprehensive security event tracking
- **Response Actions**: Blocking, alerting, and mitigation

### Task 4: Compliance Framework (25 points)
Implement compliance and privacy controls:

- **PII Detection**: Personal information identification
- **Data Masking**: Sensitive data protection
- **Audit Logging**: Compliance-ready event logging
- **Privacy Controls**: Data handling and retention

## 📊 Evaluation Criteria

### Security Implementation (60 points)
- **Threat Coverage**: Comprehensive threat detection and prevention
- **Defense in Depth**: Multiple security layers
- **Compliance**: GDPR/PCI-DSS requirement fulfillment
- **Best Practices**: Industry security standards

### Code Quality (25 points)
- **Architecture**: Clean, maintainable code structure
- **Performance**: Efficient security processing
- **Error Handling**: Robust error management
- **Documentation**: Clear security design documentation

### Testing & Validation (15 points)
- **Test Coverage**: Comprehensive security test cases
- **Edge Cases**: Proper handling of edge cases
- **Performance**: Security overhead measurements
- **Monitoring**: Security metrics and alerting

## 💡 Threat Patterns to Consider

```python
# Example threat patterns (implement more comprehensive detection)
THREAT_PATTERNS = {
    "sql_injection": [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bOR\b.*=\s*['\"][^'\"]*['\"])",
        r"(\bAND\b.*=\s*['\"][^'\"]*['\"])",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(\bINSERT\b.*\bINTO\b)",
    ],
    "xss": [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
    ],
    "command_injection": [
        r"[;&|`$()]",
        r"\b\w+\s*\.\s*\w+",
        r"\/\bin\b",
    ],
    "path_traversal": [
        r"\.\.[\/\\]",
        r"%2e%2e[\/\\]",
        r"\.\.%2f",
    ]
}
```

## 🧪 Testing Requirements

Your solution should include tests for:

1. **Security Effectiveness**
   - Injection attack prevention
   - Threat detection accuracy
   - False positive analysis

2. **Performance Testing**
   - Request processing overhead
   - Memory usage analysis
   - Throughput impact measurement

3. **Compliance Validation**
   - PII detection accuracy
   - Data masking effectiveness
   - Audit logging completeness

## 📚 Reference Materials

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Security Headers Best Practices](https://securityheaders.com/)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [GDPR Compliance Guide](https://gdpr.eu/)

## 🚀 Bonus Challenges

- **Advanced Threat Intelligence**: Implement ML-based anomaly detection
- **Zero-Trust Architecture**: Extend to full zero-trust implementation
- **Security Analytics**: Build security dashboard and metrics
- **Automated Response**: Implement automated threat response

---

**Time Limit**: 3 hours
**Difficulty**: 🔴 Expert
**Focus**: Security architecture and defense-in-depth implementation