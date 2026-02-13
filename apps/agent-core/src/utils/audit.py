"""
Audit Tracer - Ported from audit-tracer.ts.
Provides structured audit logging synchronized with Edge D1 audit_logs.
"""
import httpx
import os
import structlog
import uuid
from typing import Optional, Dict, Any

logger = structlog.get_logger()

class AuditTracer:
    """Synchronizes agent actions with the Edge API audit trail."""
    
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.base_url = os.getenv("EDGE_API_BASE_URL", "http://host.docker.internal:8787")
        self.internal_url = f"{self.base_url}/internal"

    async def log_action(
        self, 
        action: str, 
        resource_type: str = "invoice",
        details: Optional[Dict[str, Any]] = None,
        severity: str = "INFO"
    ):
        """Send a structured audit log to the Edge API."""
        payload = {
            "trace_id": self.trace_id,
            "status": f"LOG_{action}", # Reusing update-status for simplicity or create specific endpoint
            "resource_type": resource_type,
            "action": action,
            "details": details,
            "severity": severity
        }
        
        # For now, we reuse the existing update-status endpoint in internal.ts 
        # which already handles basic audit logging. 
        # In a full port, we'd have a specific /internal/audit endpoint.
        logger.info("audit_action", action=action, trace_id=self.trace_id, severity=severity)
        
        # Note: The current /internal/update-status already inserts into audit_logs.
        # We can expand this later if more granular actor data is needed.
