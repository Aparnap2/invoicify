"""
Append-Only Audit Logger for AP Workflow.

Every node in the workflow writes an audit log entry with:
- trace_id for correlation
- node_name for tracking
- input_hash (SHA256 of node input)
- output_hash (SHA256 of node output)
- status (success/error/skipped)
- created_at timestamp

This ensures full traceability and idempotency verification.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import structlog

from src.schemas.ap_models import (
    AuditLogEntry,
    NodeName,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Hashing Utilities
# ─────────────────────────────────────────────────────────────────────────────


def compute_hash(data: Any) -> str:
    """
    Compute SHA256 hash of data.
    
    Handles dicts, lists, strings, and other JSON-serializable types.
    """
    if data is None:
        return hashlib.sha256(b"").hexdigest()
    
    # Convert to JSON string with consistent ordering
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()


def compute_input_hash(node_name: str, state_input: dict) -> str:
    """Compute hash of node input."""
    input_data = {
        "node": node_name,
        "trace_id": state_input.get("trace_id"),
        "idempotency_key": state_input.get("idempotency_key"),
        # Include key fields that affect processing
        "extracted_invoice": state_input.get("extracted_invoice"),
    }
    return compute_hash(input_data)


def compute_output_hash(node_name: str, node_output: dict) -> str:
    """Compute hash of node output."""
    output_data = {
        "node": node_name,
        "result": node_output,
    }
    return compute_hash(output_data)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Logger
# ─────────────────────────────────────────────────────────────────────────────


class AuditLogger:
    """
    Append-only audit logger for the AP workflow.
    
    Writes to database with trace_id correlation.
    """
    
    def __init__(self):
        self._db = None
    
    @property
    def db(self):
        """Lazy import to avoid circular imports."""
        if self._db is None:
            from src.db import db
            self._db = db
        return self._db
    
    async def log_node_execution(
        self,
        trace_id: str,
        node_name: NodeName,
        state_input: dict,
        node_output: dict,
        status: str = "success",
        details: Optional[dict[str, Any]] = None,
    ) -> UUID:
        """
        Log a node execution to the audit trail.
        
        Args:
            trace_id: Trace ID for correlation
            node_name: Name of the node being executed
            state_input: Input state to the node
            node_output: Output from the node
            status: "success" | "error" | "skipped"
            details: Additional details to log
            
        Returns:
            UUID of the created audit log entry
        """
        # Compute hashes
        input_hash = compute_input_hash(node_name.value, state_input)
        output_hash = compute_output_hash(node_name.value, node_output)
        
        # Build details
        log_details = {
            "input_summary": {
                "trace_id": trace_id,
                "idempotency_key": state_input.get("idempotency_key"),
            },
            "status": status,
        }
        
        if details:
            log_details.update(details)
        
        # Add output summary (truncated for storage)
        if node_output:
            log_details["output_summary"] = {
                "node": node_name.value,
                "has_result": bool(node_output),
            }
        
        try:
            log_id = await self.db.create_audit_log(
                trace_id=trace_id,
                node_name=node_name.value,
                input_hash=input_hash,
                output_hash=output_hash,
                status=status,
                details=log_details,
            )
            
            logger.info(
                "audit_logged",
                trace_id=trace_id,
                node=node_name.value,
                status=status,
                input_hash=input_hash[:8],
                output_hash=output_hash[:8],
            )
            
            return log_id
            
        except Exception as e:
            # Audit logging should never fail the workflow
            logger.error(
                "audit_log_failed",
                trace_id=trace_id,
                node=node_name.value,
                error=str(e),
            )
            raise
    
    async def log_workflow_start(self, trace_id: str, idempotency_key: str) -> None:
        """Log workflow start."""
        logger.info(
            "workflow_started",
            trace_id=trace_id,
            idempotency_key=idempotency_key[:8],
        )
    
    async def log_workflow_end(
        self,
        trace_id: str,
        final_decision: str,
        status: str,
    ) -> None:
        """Log workflow end."""
        logger.info(
            "workflow_completed",
            trace_id=trace_id,
            final_decision=final_decision,
            status=status,
        )
    
    async def get_audit_trail(self, trace_id: str) -> list[dict[str, Any]]:
        """Get complete audit trail for a trace."""
        return await self.db.get_audit_logs(trace_id)


# Global audit logger instance
audit_logger = AuditLogger()


# ─────────────────────────────────────────────────────────────────────────────
# Decorator for Auto-Logging
# ─────────────────────────────────────────────────────────────────────────────


def with_audit_log(node_name: NodeName):
    """
    Decorator to automatically log node execution.
    
    Usage:
        @with_audit_log(NodeName.INGEST)
        async def ingest_node(state: dict) -> dict:
            ...
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def wrapper(state: dict) -> dict:
            trace_id = state.get("trace_id", "unknown")
            
            try:
                # Log start
                await audit_logger.log_node_execution(
                    trace_id=trace_id,
                    node_name=node_name,
                    state_input=state,
                    node_output={},
                    status="started",
                )
                
                # Execute node
                result = await func(state)
                
                # Log success
                await audit_logger.log_node_execution(
                    trace_id=trace_id,
                    node_name=node_name,
                    state_input=state,
                    node_output=result,
                    status="success",
                )
                
                return result
                
            except Exception as e:
                # Log error
                await audit_logger.log_node_execution(
                    trace_id=trace_id,
                    node_name=node_name,
                    state_input=state,
                    node_output={"error": str(e)},
                    status="error",
                )
                raise
    
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Standalone Functions (for direct use)
# ─────────────────────────────────────────────────────────────────────────────


async def log_node(
    trace_id: str,
    node_name: NodeName,
    state_input: dict,
    node_output: dict,
    status: str = "success",
) -> None:
    """
    Standalone function to log a node execution.
    
    Wrapper around AuditLogger for convenience.
    """
    await audit_logger.log_node_execution(
        trace_id=trace_id,
        node_name=node_name,
        state_input=state_input,
        node_output=node_output,
        status=status,
    )


async def get_trail(trace_id: str) -> list[dict[str, Any]]:
    """Get audit trail for a trace."""
    return await audit_logger.get_audit_trail(trace_id)
