"""
Comprehensive test suite for defense-in-depth validation system.
Tests all security layers: input sanitization, security validation, compliance validation, and monitoring.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

from app.services.validation_engine import ValidationEngine, ReasonTaxonomy
from app.services.security_validator import SecurityValidator, SecurityContext
from app.services.input_sanitizer import InputSanitizer, SanitizationLevel
from app.services.security_monitor import SecurityMonitor, MonitoringConfig, SecurityEvent
from app.schemas.validation_rules import (
    SecurityThreatLevel,
    ThreatType,
    DefenseInDepthResult,
    SecurityRule,
    ValidationLayer,
    SQL_INJECTION_PATTERNS,
    XSS_PATTERNS,
    PATH_TRAVERSAL_PATTERNS,
    COMMAND_INJECTION_PATTERNS
)


class TestInputSanitizer:
    """Test input sanitization service."""

    @pytest.fixture
    def sanitizer(self):
        """Create input sanitizer instance."""
        return InputSanitizer(default_level=SanitizationLevel.NORMAL)

    @pytest.fixture
    def strict_sanitizer(self):
        """Create strict input sanitizer instance."""
        return InputSanitizer(default_level=SanitizationLevel.STRICT)

    @pytest.fixture
    def paranoid_sanitizer(self):
        """Create paranoid input sanitizer instance."""
        return InputSanitizer(default_level=SanitizationLevel.PARANOID)

    @pytest.mark.asyncio
    async def test_sql_injection_sanitization(self, sanitizer):
        """Test SQL injection pattern sanitization."""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "UNION SELECT * FROM passwords",
            "'; EXEC xp_cmdshell('dir'); --"
        ]

        for malicious_input in malicious_inputs:
            result = sanitizer.sanitize(malicious_input, field_name="invoice_number")

            # Should sanitize dangerous SQL patterns
            assert result.success
            assert "DROP" not in result.sanitized_value.upper()
            assert "UNION" not in result.sanitized_value.upper()
            assert "EXEC" not in result.sanitized_value.upper()
            assert result.is_safe_for_database

    @pytest.mark.asyncio
    async def test_xss_sanitization(self, sanitizer):
        """Test XSS attack sanitization."""
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src='x' onerror='alert(1)'>",
            "<iframe src='javascript:alert(1)'></iframe>"
        ]

        for malicious_input in malicious_inputs:
            result = sanitizer.sanitize(malicious_input, field_name="description")

            # Should sanitize XSS patterns
            assert result.success
            assert "<script" not in result.sanitized_value.lower()
            assert "javascript:" not in result.sanitized_value.lower()
            assert "onerror=" not in result.sanitized_value.lower()
            assert result.is_safe_for_display

    def test_field_specific_sanitization(self, sanitizer):
        """Test field-specific sanitization rules."""
        # Test invoice number field
        result = sanitizer.sanitize("INV-001'; DROP TABLE;", field_name="invoice_number")
        assert result.success
        assert "DROP" not in result.sanitized_value
        assert len(result.sanitized_value) <= 50  # Max length for invoice numbers

        # Test amount field
        result = sanitizer.sanitize("$1,234.56'; SELECT * FROM", field_name="total_amount")
        assert result.success
        assert "$" not in result.sanitized_value
        assert "," not in result.sanitized_value

        # Test vendor name field
        result = sanitizer.sanitize("Acme Corp<script>", field_name="vendor_name")
        assert result.success
        assert "<script" not in result.sanitized_value.lower()


class TestSecurityValidator:
    """Test security validation service."""

    @pytest.fixture
    def validator(self):
        """Create security validator instance."""
        return SecurityValidator(enable_threat_intelligence=True)

    @pytest.fixture
    def security_context(self):
        """Create security context for testing."""
        return SecurityContext(
            source_ip="192.168.1.100",
            user_id="test_user",
            user_agent="Mozilla/5.0 Test Browser",
            request_id="req_123"
        )

    @pytest.mark.asyncio
    async def test_sql_injection_detection(self, validator, security_context):
        """Test SQL injection attack detection."""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "' OR '1'='1' --",
            "UNION SELECT password FROM users",
            "'; EXEC sp_configure 'show advanced options', 1; --"
        ]

        for malicious_input in malicious_inputs:
            result = await validator.validate_field(
                "invoice_number", malicious_input, security_context
            )

            assert result.is_threat
            assert result.threat_type == ThreatType.SQL_INJECTION
            assert result.threat_level in [SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL]
            assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_xss_detection(self, validator, security_context):
        """Test XSS attack detection."""
        malicious_inputs = [
            "<script>alert(document.cookie)</script>",
            "javascript:void(document.location='http://evil.com')",
            "<img src=x onerror=alert('xss')>",
            "<body onload=alert('xss')>"
        ]

        for malicious_input in malicious_inputs:
            result = await validator.validate_field(
                "description", malicious_input, security_context
            )

            assert result.is_threat
            assert result.threat_type == ThreatType.XSS
            assert result.threat_level in [SecurityThreatLevel.HIGH, SecurityThreatLevel.MEDIUM]
            assert result.confidence > 0.7

    @pytest.mark.asyncio
    async def test_file_upload_validation(self, validator):
        """Test file upload security validation."""
        # Test dangerous file type
        malicious_file = {
            "filename": "malware.exe",
            "content_type": "application/x-executable",
            "size": 1024 * 1024  # 1MB
        }

        result = await validator.validate_file_upload(malicious_file)
        assert result.is_threat
        assert result.threat_type == ThreatType.FILE_UPLOAD_MALWARE
        assert not result.is_safe
        assert "Dangerous file type" in " ".join(result.issues)

    @pytest.mark.asyncio
    async def test_business_logic_validation(self, validator):
        """Test business logic abuse detection."""
        # Test negative amount
        result = await validator.validate_field("total_amount", "-1000.00")
        assert result.is_threat
        assert "negative_amount" in result.matched_patterns

        # Test excessive amount
        result = await validator.validate_field("total_amount", "50000000.00")
        assert result.is_threat
        assert "excessive_amount" in result.matched_patterns


class TestDefenseInDepthValidation:
    """Test integrated defense-in-depth validation."""

    @pytest.fixture
    def validation_engine(self):
        """Create validation engine with all security features enabled."""
        return ValidationEngine(
            enable_security_validation=True,
            enable_sanitization=True
        )

    @pytest.fixture
    def security_context(self):
        """Create security context."""
        return SecurityContext(
            source_ip="192.168.1.100",
            user_id="test_user",
            request_id="req_123"
        )

    @pytest.fixture
    def sample_extraction_data(self):
        """Sample invoice extraction data for testing."""
        return {
            "header": {
                "vendor_name": "Acme Corp",
                "invoice_number": "INV-001",
                "total_amount": "1000.00",
                "invoice_date": "2023-01-01",
                "description": "Office supplies"
            },
            "lines": [
                {
                    "description": "Laptop computer",
                    "quantity": "1",
                    "unit_price": "800.00",
                    "total_amount": "800.00"
                },
                {
                    "description": "Mouse",
                    "quantity": "2",
                    "unit_price": "100.00",
                    "total_amount": "200.00"
                }
            ],
            "confidence": {
                "overall": 0.95
            }
        }

    @pytest.mark.asyncio
    async def test_clean_data_validation(self, validation_engine, sample_extraction_data, security_context):
        """Test validation with clean data."""
        result = await validation_engine.validate_defense_in_depth(
            sample_extraction_data,
            invoice_id="test_invoice_1",
            context=security_context
        )

        assert result.passed
        assert result.overall_threat_level == SecurityThreatLevel.LOW
        assert result.confidence_score > 0.8
        assert len(result.layers_executed) == 4  # All layers should execute
        assert ValidationLayer.SYNTACTIC in result.layers_executed
        assert ValidationLayer.SECURITY in result.layers_executed
        assert ValidationLayer.COMPLIANCE in result.layers_executed

    @pytest.mark.asyncio
    async def test_malicious_data_detection(self, validation_engine, sample_extraction_data, security_context):
        """Test validation with malicious data."""
        # Inject malicious content
        malicious_data = sample_extraction_data.copy()
        malicious_data["header"]["invoice_number"] = "INV-001'; DROP TABLE invoices; --"
        malicious_data["header"]["description"] = "<script>alert('xss')</script> Office supplies"

        result = await validation_engine.validate_defense_in_depth(
            malicious_data,
            invoice_id="test_invoice_2",
            context=security_context
        )

        assert not result.passed
        assert result.overall_threat_level in [SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL]
        assert len(result.threat_detections) > 0

        # Check specific threat detections
        threat_types = [td.threat_type for td in result.threat_detections]
        assert ThreatType.SQL_INJECTION in threat_types
        assert ThreatType.XSS in threat_types

        # Check sanitization results
        assert len(result.sanitization_results) > 0
        sanitization_success = all(sr.success for sr in result.sanitization_results)
        assert sanitization_success

    @pytest.mark.asyncio
    async def test_compliance_violation_detection(self, validation_engine, sample_extraction_data):
        """Test compliance violation detection."""
        # Add potential GDPR violation (SSN)
        gdpr_data = sample_extraction_data.copy()
        gdpr_data["header"]["vendor_name"] = "John Doe (SSN: 123-45-6789)"

        # Add potential PCI DSS violation (credit card)
        pci_data = sample_extraction_data.copy()
        pci_data["lines"][0]["description"] = "Payment for card 4111-1111-1111-1111"

        # Test GDPR data
        gdpr_result = await validation_engine.validate_defense_in_depth(gdpr_data)
        if gdpr_result.compliance_validation:
            assert gdpr_result.compliance_validation["violations"] > 0

        # Test PCI DSS data
        pci_result = await validation_engine.validate_defense_in_depth(pci_data)
        if pci_result.compliance_validation:
            assert pci_result.compliance_validation["violations"] > 0

    @pytest.mark.asyncio
    async def test_error_handling(self, validation_engine):
        """Test graceful error handling."""
        # Test with malformed data
        malformed_data = {
            "header": None,  # Invalid header
            "lines": "not a list",  # Invalid lines
            "confidence": "invalid"  # Invalid confidence
        }

        result = await validation_engine.validate_defense_in_depth(malformed_data)

        # Should handle errors gracefully
        assert isinstance(result, DefenseInDepthResult)
        assert not result.passed  # Should fail due to errors
        assert result.overall_threat_level == SecurityThreatLevel.CRITICAL
        assert len(result.security_recommendations) > 0


class TestSecurityMonitoring:
    """Test security monitoring service."""

    @pytest.fixture
    def monitor(self):
        """Create security monitor instance."""
        config = MonitoringConfig(
            max_events_per_source=100,
            event_retention_hours=1,
            auto_block_enabled=True,
            auto_block_threshold=5
        )
        return SecurityMonitor(config)

    @pytest.fixture
    def sample_security_event(self):
        """Create sample security event."""
        return SecurityEvent(
            event_type="threat_detected",
            threat_type=ThreatType.SQL_INJECTION,
            threat_level=SecurityThreatLevel.HIGH,
            source_ip="192.168.1.100",
            user_id="test_user",
            field="invoice_number",
            original_value="'; DROP TABLE users; --",
            confidence=0.95
        )

    @pytest.mark.asyncio
    async def test_event_processing(self, monitor, sample_security_event):
        """Test security event processing."""
        await monitor.start_monitoring()

        # Process event
        success = await monitor.process_security_event(sample_security_event)
        assert success

        # Check statistics
        stats = monitor.get_threat_statistics()
        assert stats.total_events == 1
        assert stats.sql_injection_attempts == 1
        assert stats.events_by_level["high"] == 1

        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_alert_generation(self, monitor, sample_security_event):
        """Test alert generation."""
        await monitor.start_monitoring()

        # Process critical event
        critical_event = SecurityEvent(
            event_type="threat_detected",
            threat_type=ThreatType.COMMAND_INJECTION,
            threat_level=SecurityThreatLevel.CRITICAL,
            source_ip="192.168.1.300",
            field="filename",
            original_value="file.txt; rm -rf /",
            confidence=1.0
        )

        await monitor.process_security_event(critical_event)

        # Check for alerts
        active_alerts = monitor.get_active_alerts()
        assert len(active_alerts) > 0

        # Should have critical alert
        critical_alerts = [a for a in active_alerts if a.severity == SecurityThreatLevel.CRITICAL]
        assert len(critical_alerts) > 0

        await monitor.stop_monitoring()


class TestIntegration:
    """Integration tests for complete defense-in-depth system."""

    @pytest.mark.asyncio
    async def test_complete_security_pipeline(self):
        """Test complete security pipeline from input to monitoring."""
        # Create all components
        validation_engine = ValidationEngine(
            enable_security_validation=True,
            enable_sanitization=True
        )
        monitor = SecurityMonitor()

        await monitor.start_monitoring()

        # Prepare malicious data
        malicious_data = {
            "header": {
                "vendor_name": "Test Corp<script>alert('xss')</script>",
                "invoice_number": "INV-001'; DROP TABLE invoices; --",
                "total_amount": "1000.00",
                "description": "Office supplies'; EXEC xp_cmdshell('dir'); --"
            },
            "lines": [
                {
                    "description": "Laptop with card 4111-1111-1111-1111",
                    "quantity": "1",
                    "unit_price": "800.00",
                    "total_amount": "800.00"
                }
            ],
            "confidence": {"overall": 0.85}
        }

        # Create security context
        context = SecurityContext(
            source_ip="192.168.1.100",
            user_id="test_user",
            request_id="integration_test_123"
        )

        # Process through validation engine
        result = await validation_engine.validate_defense_in_depth(
            malicious_data,
            invoice_id="integration_test_invoice",
            context=context
        )

        # Process result through monitor
        await monitor.process_validation_result(result)

        # Verify results
        assert isinstance(result, DefenseInDepthResult)
        assert not result.passed  # Should fail due to threats
        assert result.overall_threat_level in [SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL]

        # Check that threats were detected
        threat_types = [td.threat_type for td in result.threat_detections]
        assert ThreatType.XSS in threat_types
        assert ThreatType.SQL_INJECTION in threat_types

        # Check monitoring statistics
        stats = monitor.get_threat_statistics()
        assert stats.total_events > 0

        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """Test system performance under load."""
        validation_engine = ValidationEngine()
        monitor = SecurityMonitor()

        await monitor.start_monitoring()

        # Process multiple requests concurrently
        tasks = []
        for i in range(20):  # Reduced for test performance
            data = {
                "header": {
                    "vendor_name": f"Vendor {i}",
                    "invoice_number": f"INV-{i:03d}",
                    "total_amount": "100.00",
                    "description": f"Test item {i}"
                },
                "lines": [
                    {
                        "description": f"Item {i}",
                        "quantity": "1",
                        "unit_price": "100.00",
                        "total_amount": "100.00"
                    }
                ],
                "confidence": {"overall": 0.9}
            }

            context = SecurityContext(
                source_ip=f"192.168.1.{100 + (i % 20)}",
                user_id=f"user_{i % 10}",
                request_id=f"req_{i}"
            )

            task = validation_engine.validate_defense_in_depth(
                data, invoice_id=f"test_{i}", context=context
            )
            tasks.append(task)

        # Execute all tasks concurrently
        import time
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Verify performance
        assert len(results) == 20
        average_time_per_request = total_time / 20
        assert average_time_per_request < 1.0  # Should be fast

        # Most should pass (clean data)
        passed_count = sum(1 for r in results if r.passed)
        assert passed_count >= 18  # Most should pass

        await monitor.stop_monitoring()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])