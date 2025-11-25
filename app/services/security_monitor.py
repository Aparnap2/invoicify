"""
Security monitoring service for comprehensive threat tracking and alerting.
Implements real-time security event monitoring, correlation, and automated response.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import time
import json

from app.schemas.validation_rules import (
    SecurityThreatLevel,
    ThreatType,
    SecurityEvent,
    SecurityAlert,
    ThreatStatistics,
    AttackPattern,
    RiskScore,
    DefenseInDepthResult
)

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels for monitoring."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MonitoringConfig:
    """Configuration for security monitoring."""
    # Event tracking
    max_events_per_source: int = 1000
    event_retention_hours: int = 24
    alert_retention_days: int = 30

    # Thresholds
    threat_threshold_critical: int = 5
    threat_threshold_high: int = 10
    threat_threshold_medium: int = 25

    # Rate limiting
    rate_limit_window_minutes: int = 5
    rate_limit_critical_threshold: int = 10
    rate_limit_high_threshold: int = 50
    rate_limit_medium_threshold: int = 100

    # Pattern detection
    attack_pattern_window_minutes: int = 15
    min_events_for_pattern: int = 3
    correlation_threshold: float = 0.7

    # Automated responses
    auto_block_enabled: bool = True
    auto_block_threshold: int = 10
    alert_webhook_url: Optional[str] = None
    alert_email_recipients: List[str] = field(default_factory=list)


@dataclass
class SourceStatistics:
    """Statistics for a specific source (IP, user, etc.)."""
    source_id: str
    source_type: str  # ip, user, session
    total_events: int = 0
    threats_detected: int = 0
    critical_events: int = 0
    high_events: int = 0
    medium_events: int = 0
    low_events: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    is_blocked: bool = False
    blocked_at: Optional[datetime] = None
    risk_score: float = 0.0


class SecurityMonitor:
    """
    Advanced security monitoring service with real-time threat detection.

    Features:
    - Real-time security event tracking and correlation
    - Attack pattern detection and analysis
    - Automated alert generation and escalation
    - Risk scoring and trending analysis
    - Source reputation scoring and automated blocking
    - Performance-optimized event processing
    - Configurable alerting and response automation
    - Integration with external monitoring systems
    """

    def __init__(self, config: Optional[MonitoringConfig] = None):
        """Initialize security monitor with configuration."""
        self.config = config or MonitoringConfig()

        # Event storage
        self.events: deque = deque(maxlen=self.config.max_events_per_source * 100)
        self.source_events: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.config.max_events_per_source))
        self.source_stats: Dict[str, SourceStatistics] = {}

        # Alert storage
        self.alerts: List[SecurityAlert] = []
        self.active_alerts: Dict[str, SecurityAlert] = {}

        # Pattern detection
        self.detected_patterns: List[AttackPattern] = []
        self.correlation_cache: Dict[str, float] = {}

        # Blocked sources
        self.blocked_sources: Set[str] = set()
        self.source_reputation: Dict[str, float] = {}

        # Statistics
        self.global_stats = ThreatStatistics()

        # Background tasks
        self._monitoring_active = False
        self._cleanup_task = None
        self._pattern_detection_task = None

        # Event handlers
        self.event_handlers: List[Callable[[SecurityEvent], None]] = []
        self.alert_handlers: List[Callable[[SecurityAlert], None]] = []

        logger.info("SecurityMonitor initialized")

    async def start_monitoring(self):
        """Start background monitoring tasks."""
        if self._monitoring_active:
            return

        self._monitoring_active = True

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_old_events())

        # Start pattern detection task
        self._pattern_detection_task = asyncio.create_task(self._detect_attack_patterns())

        logger.info("Security monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring tasks."""
        self._monitoring_active = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._pattern_detection_task:
            self._pattern_detection_task.cancel()
            try:
                await self._pattern_detection_task
            except asyncio.CancelledError:
                pass

        logger.info("Security monitoring stopped")

    def add_event_handler(self, handler: Callable[[SecurityEvent], None]):
        """Add custom event handler."""
        self.event_handlers.append(handler)

    def add_alert_handler(self, handler: Callable[[SecurityAlert], None]):
        """Add custom alert handler."""
        self.alert_handlers.append(handler)

    async def process_security_event(self, event: SecurityEvent) -> bool:
        """
        Process a security event and trigger alerts if needed.

        Args:
            event: Security event to process

        Returns:
            True if event was processed successfully, False otherwise
        """
        try:
            # Add timestamp if not present
            if not event.timestamp:
                event.timestamp = datetime.now()

            # Store event
            self.events.append(event)

            # Update source statistics
            await self._update_source_statistics(event)

            # Update global statistics
            self._update_global_statistics(event)

            # Check for immediate alerts
            await self._check_immediate_alerts(event)

            # Call custom event handlers
            for handler in self.event_handlers:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, handler, event
                    )
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

            return True

        except Exception as e:
            logger.error(f"Error processing security event: {e}")
            return False

    async def process_validation_result(self, result: DefenseInDepthResult):
        """
        Process defense-in-depth validation result and extract security events.

        Args:
            result: Defense-in-depth validation result
        """
        try:
            # Process threat detections as security events
            for threat in result.threat_detections:
                event = SecurityEvent(
                    event_type="threat_detected",
                    threat_type=threat.threat_type,
                    threat_level=threat.threat_level,
                    field=threat.field,
                    original_value=threat.original_value,
                    confidence=threat.confidence,
                    details=threat.details,
                    correlation_id=getattr(result, 'correlation_id', None)
                )
                await self.process_security_event(event)

            # Process security events from validation
            for event in result.security_events:
                await self.process_security_event(event)

            # Check for high-risk validation results
            if not result.passed and result.overall_threat_level in [
                SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL
            ]:
                alert = SecurityAlert(
                    title="Validation Security Failure",
                    description=f"Defense-in-depth validation failed with {result.overall_threat_level.value} threat level",
                    severity=result.overall_threat_level,
                    alert_type="validation_failure",
                    event_count=len(result.threat_detections),
                    details={
                        "validation_result": result.dict(),
                        "recommendations": result.security_recommendations
                    }
                )
                await self._create_alert(alert)

        except Exception as e:
            logger.error(f"Error processing validation result: {e}")

    async def check_source_reputation(self, source_id: str) -> Dict[str, Any]:
        """
        Check reputation score for a source.

        Args:
            source_id: Source identifier (IP, user ID, etc.)

        Returns:
            Reputation analysis
        """
        stats = self.source_stats.get(source_id)
        if not stats:
            return {
                "source_id": source_id,
                "reputation_score": 1.0,
                "risk_level": "unknown",
                "is_blocked": False,
                "events_count": 0
            }

        # Calculate reputation score
        reputation_score = self._calculate_reputation_score(stats)

        # Determine risk level
        if reputation_score >= 0.8:
            risk_level = "low"
        elif reputation_score >= 0.6:
            risk_level = "medium"
        elif reputation_score >= 0.4:
            risk_level = "high"
        else:
            risk_level = "critical"

        return {
            "source_id": source_id,
            "reputation_score": reputation_score,
            "risk_level": risk_level,
            "is_blocked": stats.is_blocked,
            "events_count": stats.total_events,
            "threats_detected": stats.threats_detected,
            "critical_events": stats.critical_events,
            "high_events": stats.high_events,
            "first_seen": stats.first_seen.isoformat(),
            "last_seen": stats.last_seen.isoformat()
        }

    def get_threat_statistics(self, time_window_hours: int = 24) -> ThreatStatistics:
        """
        Get threat statistics for the specified time window.

        Args:
            time_window_hours: Time window in hours

        Returns:
            Threat statistics
        """
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)

        # Filter events by time window
        recent_events = [
            event for event in self.events
            if event.timestamp >= cutoff_time
        ]

        # Calculate statistics
        stats = ThreatStatistics(
            total_events=len(recent_events),
            events_by_type=defaultdict(int),
            events_by_level=defaultdict(int),
            events_by_source=defaultdict(int)
        )

        for event in recent_events:
            # Count by threat type
            if event.threat_type:
                stats.events_by_type[event.threat_type.value] += 1

            # Count by threat level
            stats.events_by_level[event.threat_level.value] += 1

            # Count by source
            source_key = event.source_ip or event.user_id or "unknown"
            stats.events_by_source[source_key] += 1

        # Update specific threat counts
        stats.sql_injection_attempts = stats.events_by_type.get("sql_injection", 0)
        stats.xss_attempts = stats.events_by_type.get("xss", 0)
        stats.path_traversal_attempts = stats.events_by_type.get("path_traversal", 0)
        stats.command_injection_attempts = stats.events_by_type.get("command_injection", 0)
        stats.rate_limit_violations = stats.events_by_type.get("rate_limit_exceeded", 0)

        # Calculate current risk score
        stats.current_risk_score = self._calculate_global_risk_score(stats)

        return stats

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[SecurityAlert]:
        """
        Get active security alerts.

        Args:
            severity: Optional severity filter

        Returns:
            List of active alerts
        """
        alerts = list(self.active_alerts.values())

        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """
        Acknowledge a security alert.

        Args:
            alert_id: Alert ID to acknowledge
            acknowledged_by: User acknowledging the alert

        Returns:
            True if alert was acknowledged, False otherwise
        """
        if alert_id not in self.active_alerts:
            return False

        alert = self.active_alerts[alert_id]
        alert.resolved_at = datetime.now()
        alert.resolved_by = acknowledged_by
        alert.resolution_notes = f"Manually acknowledged by {acknowledged_by}"

        # Move from active to resolved
        self.alerts.append(alert)
        del self.active_alerts[alert_id]

        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")

        # Call alert handlers
        for handler in self.alert_handlers:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, handler, alert
                )
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

        return True

    def block_source(self, source_id: str, reason: str, duration_hours: int = 24):
        """
        Block a source (IP, user, etc.) temporarily.

        Args:
            source_id: Source identifier
            reason: Reason for blocking
            duration_hours: Duration of block in hours
        """
        self.blocked_sources.add(source_id)

        if source_id in self.source_stats:
            self.source_stats[source_id].is_blocked = True
            self.source_stats[source_id].blocked_at = datetime.now()

        # Create alert
        alert = SecurityAlert(
            title="Source Blocked",
            description=f"Source {source_id} blocked due to: {reason}",
            severity=SecurityThreatLevel.HIGH,
            alert_type="source_blocked",
            affected_endpoints=[source_id],
            recommended_actions=[
                f"Monitor source {source_id} for continued activity",
                f"Review recent events from {source_id}",
                f"Consider permanent blocking if activity continues"
            ]
        )

        self.active_alerts[alert.id] = alert
        logger.warning(f"Source {source_id} blocked: {reason}")

    def unblock_source(self, source_id: str):
        """Unblock a previously blocked source."""
        self.blocked_sources.discard(source_id)

        if source_id in self.source_stats:
            self.source_stats[source_id].is_blocked = False
            self.source_stats[source_id].blocked_at = None

        logger.info(f"Source {source_id} unblocked")

    # Private methods

    async def _update_source_statistics(self, event: SecurityEvent):
        """Update statistics for the event source."""
        source_key = event.source_ip or event.user_id or "unknown"

        if source_key not in self.source_stats:
            self.source_stats[source_key] = SourceStatistics(
                source_id=source_key,
                source_type="ip" if event.source_ip else "user"
            )

        stats = self.source_stats[source_key]
        stats.total_events += 1
        stats.last_seen = event.timestamp

        # Update threat level counts
        if event.threat_level == SecurityThreatLevel.CRITICAL:
            stats.critical_events += 1
        elif event.threat_level == SecurityThreatLevel.HIGH:
            stats.high_events += 1
        elif event.threat_level == SecurityThreatLevel.MEDIUM:
            stats.medium_events += 1
        else:
            stats.low_events += 1

        # Update threat count
        if event.threat_type:
            stats.threats_detected += 1

        # Update risk score
        stats.risk_score = self._calculate_source_risk_score(stats)

        # Store event for source
        self.source_events[source_key].append(event)

    def _update_global_statistics(self, event: SecurityEvent):
        """Update global threat statistics."""
        self.global_stats.total_events += 1

        if event.threat_type:
            threat_key = event.threat_type.value
            self.global_stats.events_by_type[threat_key] = (
                self.global_stats.events_by_type.get(threat_key, 0) + 1
            )

        if event.threat_level:
            level_key = event.threat_level.value
            self.global_stats.events_by_level[level_key] = (
                self.global_stats.events_by_level.get(level_key, 0) + 1
            )

        source_key = event.source_ip or event.user_id or "unknown"
        self.global_stats.events_by_source[source_key] = (
            self.global_stats.events_by_source.get(source_key, 0) + 1
        )

    async def _check_immediate_alerts(self, event: SecurityEvent):
        """Check for immediate alert conditions."""
        # Critical threats always create alerts
        if event.threat_level == SecurityThreatLevel.CRITICAL:
            alert = SecurityAlert(
                title="Critical Security Threat Detected",
                description=f"Critical {event.threat_type.value} threat from {event.source_ip or event.user_id}",
                severity=SecurityThreatLevel.CRITICAL,
                alert_type="critical_threat",
                threat_type=event.threat_type,
                source_ips=[event.source_ip] if event.source_ip else [],
                affected_users=[event.user_id] if event.user_id else [],
                details=event.details
            )
            await self._create_alert(alert)

        # Check source event rate
        source_key = event.source_ip or event.user_id
        if source_key:
            recent_source_events = [
                e for e in self.source_events[source_key]
                if e.timestamp >= datetime.now() - timedelta(minutes=self.config.rate_limit_window_minutes)
            ]

            if len(recent_source_events) >= self.config.rate_limit_critical_threshold:
                alert = SecurityAlert(
                    title="High Rate Security Events Detected",
                    description=f"High rate of security events from {source_key}: {len(recent_source_events)} events in {self.config.rate_limit_window_minutes} minutes",
                    severity=SecurityThreatLevel.HIGH,
                    alert_type="high_event_rate",
                    source_ips=[source_key] if event.source_ip else [],
                    affected_users=[source_key] if event.user_id else [],
                    event_count=len(recent_source_events),
                    time_window_minutes=self.config.rate_limit_window_minutes
                )
                await self._create_alert(alert)

                # Auto-block if enabled and threshold exceeded
                if (self.config.auto_block_enabled and
                    len(recent_source_events) >= self.config.auto_block_threshold):
                    self.block_source(source_key, "Automated block due to high event rate")

    async def _create_alert(self, alert: SecurityAlert):
        """Create and process a security alert."""
        alert.id = f"alert_{int(time.time())}_{len(self.alerts)}"
        alert.created_at = datetime.now()

        # Store alert
        self.active_alerts[alert.id] = alert

        logger.warning(f"Security alert created: {alert.title}")

        # Call alert handlers
        for handler in self.alert_handlers:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, handler, alert
                )
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

        # Send notifications (placeholder for webhook/email integration)
        await self._send_alert_notification(alert)

    async def _send_alert_notification(self, alert: SecurityAlert):
        """Send alert notification via configured channels."""
        try:
            # Webhook notification
            if self.config.alert_webhook_url:
                # This would integrate with a webhook service
                logger.info(f"Alert webhook would be sent to {self.config.alert_webhook_url}")

            # Email notification
            if self.config.alert_email_recipients:
                # This would integrate with an email service
                logger.info(f"Alert email would be sent to {self.config.alert_email_recipients}")

        except Exception as e:
            logger.error(f"Error sending alert notification: {e}")

    async def _cleanup_old_events(self):
        """Background task to clean up old events."""
        while self._monitoring_active:
            try:
                cutoff_time = datetime.now() - timedelta(hours=self.config.event_retention_hours)
                alert_cutoff_time = datetime.now() - timedelta(days=self.config.alert_retention_days)

                # Clean up old events
                self.events = deque(
                    (event for event in self.events if event.timestamp >= cutoff_time),
                    maxlen=self.config.max_events_per_source * 100
                )

                # Clean up old resolved alerts
                self.alerts = [
                    alert for alert in self.alerts
                    if alert.resolved_at and alert.resolved_at >= alert_cutoff_time
                ]

                # Clean up old source events
                for source_key in list(self.source_events.keys()):
                    self.source_events[source_key] = deque(
                        (event for event in self.source_events[source_key] if event.timestamp >= cutoff_time),
                        maxlen=self.config.max_events_per_source
                    )

                await asyncio.sleep(3600)  # Run every hour

            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(300)  # Retry in 5 minutes

    async def _detect_attack_patterns(self):
        """Background task to detect attack patterns."""
        while self._monitoring_active:
            try:
                # Get recent events for pattern analysis
                cutoff_time = datetime.now() - timedelta(minutes=self.config.attack_pattern_window_minutes)
                recent_events = [
                    event for event in self.events
                    if event.timestamp >= cutoff_time
                ]

                if len(recent_events) >= self.config.min_events_for_pattern:
                    await self._analyze_attack_patterns(recent_events)

                await asyncio.sleep(300)  # Run every 5 minutes

            except Exception as e:
                logger.error(f"Error in pattern detection task: {e}")
                await asyncio.sleep(60)  # Retry in 1 minute

    async def _analyze_attack_patterns(self, events: List[SecurityEvent]):
        """Analyze events for attack patterns."""
        try:
            # Group events by threat type
            events_by_type = defaultdict(list)
            for event in events:
                if event.threat_type:
                    events_by_type[event.threat_type].append(event)

            # Look for patterns in each threat type
            for threat_type, type_events in events_by_type.items():
                if len(type_events) >= self.config.min_events_for_pattern:
                    pattern = await self._detect_pattern_for_threat_type(threat_type, type_events)
                    if pattern:
                        self.detected_patterns.append(pattern)

                        # Create alert for detected pattern
                        alert = SecurityAlert(
                            title="Attack Pattern Detected",
                            description=f"Coordinated {threat_type.value} attack pattern detected",
                            severity=pattern.severity,
                            alert_type="attack_pattern",
                            source_ips=pattern.affected_sources,
                            details=pattern.__dict__
                        )
                        await self._create_alert(alert)

        except Exception as e:
            logger.error(f"Error analyzing attack patterns: {e}")

    async def _detect_pattern_for_threat_type(
        self, threat_type: ThreatType, events: List[SecurityEvent]
    ) -> Optional[AttackPattern]:
        """Detect pattern for specific threat type."""
        try:
            # Analyze source distribution
            sources = set()
            for event in events:
                source_key = event.source_ip or event.user_id
                if source_key:
                    sources.add(source_key)

            # Check for coordinated attack (multiple sources or multiple events from same source)
            is_coordinated = len(sources) > 1 or len(events) >= 10

            # Calculate time span
            if events:
                time_span = max(event.timestamp for event in events) - min(event.timestamp for event in events)
                time_span_minutes = int(time_span.total_seconds() / 60)
            else:
                time_span_minutes = 0

            # Determine severity based on event count and threat type
            if len(events) >= 20 or threat_type in [ThreatType.SQL_INJECTION, ThreatType.COMMAND_INJECTION]:
                severity = SecurityThreatLevel.HIGH
            elif len(events) >= 10:
                severity = SecurityThreatLevel.MEDIUM
            else:
                severity = SecurityThreatLevel.LOW

            return AttackPattern(
                pattern_type=f"{threat_type.value}_attack",
                confidence=min(1.0, len(events) / 20.0),
                description=f"{len(events)} {threat_type.value} events detected",
                event_count=len(events),
                affected_sources=list(sources),
                time_span_minutes=time_span_minutes,
                is_coordinated=is_coordinated,
                attack_vector=str(threat_type.value),
                severity=severity,
                recommended_response=self._get_pattern_response(threat_type, severity)
            )

        except Exception as e:
            logger.error(f"Error detecting pattern for threat type {threat_type}: {e}")
            return None

    def _get_pattern_response(self, threat_type: ThreatType, severity: SecurityThreatLevel) -> str:
        """Get recommended response for attack pattern."""
        if severity == SecurityThreatLevel.HIGH:
            return f"Immediate blocking and investigation recommended for {threat_type.value} attack"
        elif severity == SecurityThreatLevel.MEDIUM:
            return f"Enhanced monitoring and potential blocking for {threat_type.value} activity"
        else:
            return f"Monitor {threat_type.value} activity and investigate if it continues"

    def _calculate_reputation_score(self, stats: SourceStatistics) -> float:
        """Calculate reputation score for a source."""
        if stats.total_events == 0:
            return 1.0

        # Base score starts at 1.0
        score = 1.0

        # Penalty for threats detected
        threat_ratio = stats.threats_detected / stats.total_events
        score -= threat_ratio * 0.5

        # Penalty for high-severity events
        high_severity_ratio = (stats.critical_events + stats.high_events) / stats.total_events
        score -= high_severity_ratio * 0.3

        # Bonus for low activity
        if stats.total_events < 10:
            score += 0.1

        # Penalty if blocked
        if stats.is_blocked:
            score -= 0.5

        return max(0.0, min(1.0, score))

    def _calculate_source_risk_score(self, stats: SourceStatistics) -> float:
        """Calculate risk score for a source."""
        base_score = 0.0

        # Add score based on event counts by severity
        base_score += stats.critical_events * 2.0
        base_score += stats.high_events * 1.5
        base_score += stats.medium_events * 1.0
        base_score += stats.low_events * 0.5

        # Adjust by threat ratio
        if stats.total_events > 0:
            threat_ratio = stats.threats_detected / stats.total_events
            base_score *= (1 + threat_ratio)

        # Cap at 10.0
        return min(10.0, base_score)

    def _calculate_global_risk_score(self, stats: ThreatStatistics) -> float:
        """Calculate global risk score from statistics."""
        base_score = 0.0

        # Weight by threat type severity
        base_score += stats.sql_injection_attempts * 2.0
        base_score += stats.command_injection_attempts * 2.0
        base_score += stats.xss_attempts * 1.5
        base_score += stats.path_traversal_attempts * 1.5
        base_score += stats.file_upload_attempts * 1.0

        # Adjust by total event count
        if stats.total_events > 0:
            base_score = base_score * (stats.total_events / 100.0)

        # Cap at 10.0
        return min(10.0, base_score)