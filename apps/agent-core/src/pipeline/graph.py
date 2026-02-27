"""
LangGraph State Machine for Invoice Processing Pipeline.

Implements the complete workflow:
SUBMITTED → EXTRACTING → VALIDATING → ANALYZING → {AUTO_APPROVE | HITL_REQUIRED | BLOCKED} → AUDITING → END

State Graph:
                    ┌─────────────────┐
                    │   START         │
                    │  invoice_data   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  EXTRACTING     │
                    │  Docling PDF    │
                    │  Azure LLM      │
                    │  → InvoiceData  │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │  confidence < 0.75?          │
              └────────┬────────────┬────────┘
                      YES           NO
                       │             │
              ┌────────▼──┐  ┌──────▼──────────┐
              │ NEEDS_CALL │  │   VALIDATING    │
              │ queue voice│  │   Math check    │
              │ call to    │  │   RAG context   │
              │ vendor     │  │   Duplicate det │
              └────────┬───┘  └──────┬──────────┘
                       │              │
              ┌────────▼───┐          │
              │CALL_PENDING│          │
              │ waiting for│          │
              │ transcript │          │
              └────────┬───┘          │
                       │ call result  │
                       └──────────────┤
                                      │
                             ┌────────▼────────┐
                             │   ANALYZING     │
                             │   Trust Battery │
                             │   Risk Score    │
                             │   Anomaly Check │
                             └────────┬────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
     ┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
     │  AUTO_APPROVE   │    │ HITL_REQUIRED   │    │    BLOCKED      │
     │  trust >= CORE  │    │  trust=STANDARD │    │  fraud signal   │
     │  risk < 0.3     │    │  risk 0.3-0.7   │    │  risk > 0.7     │
     │  amount < limit │    │  amount > limit │    │  duplicate det  │
     └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
              │                      │                       │
     ┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
     │   EXECUTING     │    │  AWAITING_HUMAN │    │  FRAUD_ALERT    │
     │  QuickBooks API │    │  notify HITL    │    │  notify + log   │
     └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
              │                      │                       │
              └──────────────────────┴───────────────────────┘
                                      │
                             ┌────────▼────────┐
                             │    AUDITING     │
                             │  Write Cosmos   │
                             │  Index AI Search│
                             │  Emit event     │
                             └────────┬────────┘
                                      │
                             ┌────────▼────────┐
                             │      END        │
                             └─────────────────┘
"""

from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Literal, Optional
from datetime import datetime
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages

from src.schemas.invoice_v2 import (
    InvoiceStatus,
    RiskDecision,
    TrustLevel,
    ExtractedInvoice,
    RiskAnalysis,
    VoiceCallRecord,
    InvoiceDocument,
    AuditLogEntry,
)


# ─────────────────────────────────────────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InvoicePipelineState:
    """
    State for invoice processing pipeline.
    
    All fields are persisted across graph transitions.
    """
    # Input data
    trace_id: str
    invoice_id: str
    r2_url: str
    tenant_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Processing state
    status: InvoiceStatus = InvoiceStatus.SUBMITTED
    current_stage: str = "START"
    
    # Extracted data
    extracted: Optional[ExtractedInvoice] = None
    
    # Risk analysis
    risk: Optional[RiskAnalysis] = None
    
    # Voice call (if needed)
    voice_call: Optional[VoiceCallRecord] = None
    
    # Execution results
    quickbooks_bill_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_decision: Optional[str] = None
    reviewer_notes: Optional[str] = None
    
    # Audit trail
    audit_log: List[AuditLogEntry] = field(default_factory=list)
    
    # Errors
    error_message: Optional[str] = None
    
    # Performance metrics
    stage_latencies: Dict[str, int] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


def add_audit_log(existing: List[AuditLogEntry], new: List[AuditLogEntry]) -> List[AuditLogEntry]:
    """Reducer for audit log entries (append-only)."""
    return existing + new


# ─────────────────────────────────────────────────────────────────────────────
# NODE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

class InvoicePipelineNodes:
    """
    Node functions for invoice processing pipeline.
    
    Each node:
    1. Performs a specific operation (extract, validate, analyze, etc.)
    2. Updates the state
    3. Returns the updated state
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize pipeline nodes.
        
        Args:
            config: Configuration dict with service clients
        """
        self.config = config or {}
        self.redis_client = config.get("redis_client")
        self.cosmos_client = config.get("cosmos_client")
    
    async def extract(self, state: InvoicePipelineState) -> Dict[str, Any]:
        """
        Extract invoice data from PDF.
        
        Uses Docling for PDF → Markdown, then LLM for structured extraction.
        """
        import time
        start = time.perf_counter()
        
        try:
            # Import extractor agent
            from src.agents.extractor import ExtractorAgent
            
            extractor = ExtractorAgent()
            extracted = await extractor.extract_from_url(state.r2_url)
            
            # Update state
            updates = {
                "extracted": extracted,
                "status": InvoiceStatus.EXTRACTING,
                "current_stage": "EXTRACTED",
            }
            
            # Check if confidence is low → needs voice call
            if extracted.extraction_confidence < 0.75 or extracted.missing_fields:
                updates["status"] = InvoiceStatus.CALL_PENDING
                updates["current_stage"] = "NEEDS_CALL"
            
            # Record latency
            latency_ms = int((time.perf_counter() - start) * 1000)
            updates["stage_latencies"] = {"extraction": latency_ms}
            
            # Create audit log entry
            audit_entry = AuditLogEntry(
                partition_key=state.invoice_id,
                invoice_id=state.invoice_id,
                tenant_id=state.tenant_id,
                actor="agent",
                action="EXTRACTED",
                previous_status=InvoiceStatus.SUBMITTED.value,
                new_status=updates["status"].value,
                reason=f"Extraction completed with confidence {extracted.extraction_confidence:.2f}",
                metadata={
                    "extraction_model": extracted.extraction_model,
                    "extraction_latency_ms": latency_ms,
                },
            )
            updates["audit_log"] = [audit_entry]
            
            return updates
            
        except Exception as e:
            return {
                "error_message": f"Extraction failed: {str(e)}",
                "status": InvoiceStatus.FAILED,
            }
    
    async def validate(self, state: InvoicePipelineState) -> Dict[str, Any]:
        """
        Validate extracted invoice data.
        
        Checks:
        - Math validation (line items sum to total)
        - Duplicate detection (via RAG)
        - Contract terms (price variance)
        """
        import time
        start = time.perf_counter()
        
        try:
            # Import critic agent
            from src.agents.critic import CriticAgent
            
            critic = CriticAgent()
            validation_result = await critic.validate(state.extracted)
            
            # Update state
            updates = {
                "status": InvoiceStatus.VALIDATING,
                "current_stage": "VALIDATED",
            }
            
            # Record latency
            latency_ms = int((time.perf_counter() - start) * 1000)
            updates["stage_latencies"] = {"validation": latency_ms}
            
            # Create audit log entry
            audit_entry = AuditLogEntry(
                partition_key=state.invoice_id,
                invoice_id=state.invoice_id,
                tenant_id=state.tenant_id,
                actor="agent",
                action="VALIDATED",
                previous_status=state.status.value,
                new_status=InvoiceStatus.VALIDATING.value,
                reason="Validation completed",
                metadata=validation_result,
            )
            updates["audit_log"] = [audit_entry]
            
            return updates
            
        except Exception as e:
            return {
                "error_message": f"Validation failed: {str(e)}",
                "status": InvoiceStatus.FAILED,
            }
    
    async def analyze(self, state: InvoicePipelineState) -> Dict[str, Any]:
        """
        Analyze risk and make decision.
        
        Uses:
        - Trust Battery (vendor history)
        - RAG context (similar invoices)
        - Risk scoring (anomaly detection)
        """
        import time
        start = time.perf_counter()
        
        try:
            # Import analyst agent
            from src.agents.analyst_agent import AnalystAgent
            
            analyst = AnalystAgent()
            risk_analysis = await analyst.analyze(
                extracted=state.extracted,
                tenant_id=state.tenant_id,
                metadata=state.metadata,
            )
            
            # Update state
            updates = {
                "risk": risk_analysis,
                "status": InvoiceStatus.ANALYZING,
                "current_stage": "ANALYZED",
            }
            
            # Determine next status based on decision
            if risk_analysis.decision == RiskDecision.AUTO_APPROVE:
                updates["status"] = InvoiceStatus.APPROVED
                updates["current_stage"] = "AUTO_APPROVE"
            elif risk_analysis.decision == RiskDecision.HITL_REQUIRED:
                updates["status"] = InvoiceStatus.PENDING_REVIEW
                updates["current_stage"] = "HITL_REQUIRED"
            elif risk_analysis.decision == RiskDecision.BLOCKED:
                updates["status"] = InvoiceStatus.REJECTED
                updates["current_stage"] = "BLOCKED"
            
            # Record latency
            latency_ms = int((time.perf_counter() - start) * 1000)
            updates["stage_latencies"] = {"analysis": latency_ms}
            
            # Create audit log entry
            audit_entry = AuditLogEntry(
                partition_key=state.invoice_id,
                invoice_id=state.invoice_id,
                tenant_id=state.tenant_id,
                actor="agent",
                action=risk_analysis.decision.value,
                previous_status=state.status.value,
                new_status=updates["status"].value,
                reason=risk_analysis.decision_reason,
                metadata={
                    "risk_score": risk_analysis.risk_score,
                    "trust_level": risk_analysis.trust_level.value,
                    "auto_approve_limit": risk_analysis.auto_approve_limit,
                },
            )
            updates["audit_log"] = [audit_entry]
            
            return updates
            
        except Exception as e:
            return {
                "error_message": f"Analysis failed: {str(e)}",
                "status": InvoiceStatus.FAILED,
            }
    
    async def execute(self, state: InvoicePipelineState) -> Dict[str, Any]:
        """
        Execute approved invoice (QuickBooks integration).
        
        Only called for AUTO_APPROVE decisions.
        """
        import time
        start = time.perf_counter()
        
        try:
            # Import executor agent
            from src.agents.executor_agent import ExecutorAgent
            
            executor = ExecutorAgent()
            result = await executor.execute(state.extracted, state.tenant_id)
            
            # Update state
            updates = {
                "quickbooks_bill_id": result.get("bill_id"),
                "current_stage": "EXECUTED",
            }
            
            # Record latency
            latency_ms = int((time.perf_counter() - start) * 1000)
            updates["stage_latencies"] = {"execution": latency_ms}
            
            # Create audit log entry
            audit_entry = AuditLogEntry(
                partition_key=state.invoice_id,
                invoice_id=state.invoice_id,
                tenant_id=state.tenant_id,
                actor="agent",
                action="EXECUTED",
                previous_status=state.status.value,
                new_status=InvoiceStatus.APPROVED.value,
                reason=f"QuickBooks bill created: {result.get('bill_id')}",
                metadata=result,
            )
            updates["audit_log"] = [audit_entry]
            
            return updates
            
        except Exception as e:
            return {
                "error_message": f"Execution failed: {str(e)}",
                "status": InvoiceStatus.FAILED,
            }
    
    async def audit(self, state: InvoicePipelineState) -> Dict[str, Any]:
        """
        Final audit step: persist to Cosmos DB, index in AI Search, emit events.
        """
        import time
        start = time.perf_counter()
        
        try:
            # Build final invoice document
            doc = InvoiceDocument(
                id=state.invoice_id,
                partition_key=state.metadata.get("vendor_name", "Unknown"),
                tenant_id=state.tenant_id,
                trace_id=state.trace_id,
                r2_url=state.r2_url,
                status=state.status,
                extracted=state.extracted,
                risk=state.risk,
                voice_call=state.voice_call,
                quickbooks_bill_id=state.quickbooks_bill_id,
                reviewer_id=state.reviewer_id,
                reviewer_decision=state.reviewer_decision,
                reviewer_notes=state.reviewer_notes,
                submitted_at=state.started_at,
                completed_at=datetime.utcnow(),
                processing_latency_ms=sum(state.stage_latencies.values()),
            )
            
            # Persist to Cosmos DB (placeholder)
            # await self.cosmos_client.upsert_document(doc.dict())
            
            # Index in AI Search (placeholder)
            # await self.search_client.index_document(doc.dict())
            
            # Emit event to Event Grid (placeholder)
            # await self.event_grid_client.emit_event("invoice.processed", doc.dict())
            
            # Update state
            updates = {
                "current_stage": "AUDITED",
                "completed_at": datetime.utcnow(),
            }
            
            # Record latency
            latency_ms = int((time.perf_counter() - start) * 1000)
            updates["stage_latencies"] = {"audit": latency_ms}
            
            return updates
            
        except Exception as e:
            return {
                "error_message": f"Audit failed: {str(e)}",
                "status": InvoiceStatus.FAILED,
            }


# ─────────────────────────────────────────────────────────────────────────────
# EDGE FUNCTIONS (ROUTING)
# ─────────────────────────────────────────────────────────────────────────────

class InvoicePipelineEdges:
    """Edge functions for conditional routing."""
    
    @staticmethod
    def route_after_extraction(state: InvoicePipelineState) -> Literal["validate", "queue_voice_call"]:
        """Route based on extraction confidence."""
        if state.extracted and (state.extracted.extraction_confidence < 0.75 or state.extracted.missing_fields):
            return "queue_voice_call"
        return "validate"
    
    @staticmethod
    def route_after_analysis(state: InvoicePipelineState) -> Literal["execute", "await_human", "fraud_alert", "audit"]:
        """Route based on risk decision."""
        if not state.risk:
            return "audit"
        
        decision = state.risk.decision
        if decision == RiskDecision.AUTO_APPROVE:
            return "execute"
        elif decision == RiskDecision.HITL_REQUIRED:
            return "await_human"
        elif decision == RiskDecision.BLOCKED:
            return "fraud_alert"
        else:
            return "audit"
    
    @staticmethod
    def route_after_execution(state: InvoicePipelineState) -> Literal["audit"]:
        """After execution, always go to audit."""
        return "audit"
    
    @staticmethod
    def route_after_human(state: InvoicePipelineState) -> Literal["audit"]:
        """After human decision, always go to audit."""
        return "audit"
    
    @staticmethod
    def route_after_fraud(state: InvoicePipelineState) -> Literal["audit"]:
        """After fraud alert, always go to audit."""
        return "audit"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class InvoicePipeline:
    """
    Main invoice processing pipeline.
    
    Usage:
        pipeline = InvoicePipeline()
        result = await pipeline.run({
            "trace_id": "trace-123",
            "invoice_id": "inv-001",
            "r2_url": "https://...",
            "tenant_id": "tenant-001",
        })
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize pipeline.
        
        Args:
            config: Configuration dict with service clients
        """
        self.config = config or {}
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the state graph."""
        # Create state graph with typed state
        builder = StateGraph(InvoicePipelineState)
        
        # Initialize nodes
        nodes = InvoicePipelineNodes(self.config)
        edges = InvoicePipelineEdges()
        
        # Add nodes
        builder.add_node("extract", nodes.extract)
        builder.add_node("validate", nodes.validate)
        builder.add_node("analyze", nodes.analyze)
        builder.add_node("execute", nodes.execute)
        builder.add_node("audit", nodes.audit)
        
        # Add edges
        builder.add_edge(START, "extract")
        
        # Conditional routing after extraction
        builder.add_conditional_edges(
            "extract",
            edges.route_after_extraction,
            {
                "validate": "validate",
                "queue_voice_call": "audit",  # Skip to audit for voice call path
            },
        )
        
        # After validation → analysis
        builder.add_edge("validate", "analyze")
        
        # Conditional routing after analysis
        builder.add_conditional_edges(
            "analyze",
            edges.route_after_analysis,
            {
                "execute": "execute",
                "await_human": "audit",
                "fraud_alert": "audit",
                "audit": "audit",
            },
        )
        
        # After execution → audit
        builder.add_edge("execute", "audit")
        
        # End state
        builder.add_edge("audit", END)
        
        # Compile with checkpointer
        checkpointer = InMemorySaver()
        graph = builder.compile(checkpointer=checkpointer)
        
        return graph
    
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the pipeline.
        
        Args:
            input_data: Input data with trace_id, invoice_id, r2_url, tenant_id
            
        Returns:
            Final state as dict
        """
        # Create initial state
        initial_state = InvoicePipelineState(
            trace_id=input_data["trace_id"],
            invoice_id=input_data["invoice_id"],
            r2_url=input_data["r2_url"],
            tenant_id=input_data["tenant_id"],
            metadata=input_data.get("metadata", {}),
        )
        
        # Run graph
        config = {"configurable": {"thread_id": input_data["trace_id"]}}
        final_state = await self.graph.ainvoke(initial_state, config)
        
        # Convert to dict
        return {
            "trace_id": final_state["trace_id"],
            "invoice_id": final_state["invoice_id"],
            "status": final_state["status"].value,
            "decision": final_state["risk"].decision.value if final_state.get("risk") else None,
            "risk_score": final_state["risk"].risk_score if final_state.get("risk") else None,
            "extraction_confidence": final_state["extracted"].extraction_confidence if final_state.get("extracted") else None,
            "processing_latency_ms": sum(final_state.get("stage_latencies", {}).values()),
            "quickbooks_bill_id": final_state.get("quickbooks_bill_id"),
            "error": final_state.get("error_message"),
        }
