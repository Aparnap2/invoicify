"""LangGraph workflow for invoice processing with Analyst-Critic pattern."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.agents.analyst import AnalystAgent, AnalystProposal, get_analyst_agent
from app.agents.critic import CriticAgent, CriticReview, FinancialContext, get_critic_agent
from app.agents.extractor import get_extractor_agent, InvoiceExtractionResult
from app.clients.neo4j_client import get_neo4j_client
from app.config import get_settings
from app.services.langfuse import (
    get_langfuse_client,
    InvoiceWorkflowTracer,
    create_workflow_trace,
)
from app.services.trust_battery import TrustBatteryService, get_trust_battery_service
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceExtracted,
    InvoiceStatus,
    POValidationResult,
    DuplicateCheck,
    ApprovalRequest,
    ApprovalAction,
    ApprovalStatus,
    RiskLevel,
    ProcessingResult,
)

logger = logging.getLogger(__name__)


class InvoiceState(TypedDict):
    """State for the invoice processing graph with Analyst-Critic pattern."""

    # Input
    invoice_data: InvoiceCreate
    raw_content: str

    # Processing state
    invoice_id: str
    status: InvoiceStatus
    extracted_data: InvoiceExtracted | None
    raw_text: str

    # Validation results
    po_validation: POValidationResult | None
    duplicate_check: DuplicateCheck | None

    # Analyst-Critic pattern
    financial_context: dict | None  # Current cash, burn rate, runway, etc.
    analyst_proposal: AnalystProposal | None  # Analyst's recommendation
    critic_review: CriticReview | None  # Critic's safety review
    trust_battery: dict | None  # Vendor trust level and history
    reasoning_chain: list[str] | None  # Step-by-step reasoning

    # Approval state
    requires_approval: bool
    approval_request: ApprovalRequest | None
    approval_action: ApprovalAction | None

    # Output
    result: ProcessingResult | None
    error: str | None


def create_invoice_workflow() -> StateGraph:
    """Create the invoice processing workflow graph with Analyst-Critic pattern."""

    builder = StateGraph(InvoiceState)

    # Add nodes
    builder.add_node("extract_fields", extract_fields_node)
    builder.add_node("validate_po", validate_po_node)
    builder.add_node("check_duplicates", check_duplicates_node)

    # Analyst-Critic pattern nodes
    builder.add_node("load_context", load_context_node)  # Load financial context + trust battery
    builder.add_node("analyst_propose", analyst_propose_node)  # Analyst makes recommendation
    builder.add_node("critic_review", critic_review_node)  # Critic does safety checks
    builder.add_node("execute_action", execute_action_node)  # Execute proposed action

    # Legacy escalation nodes (fallback)
    builder.add_node("decide_escalation", decide_escalation_node)
    builder.add_node("request_approval", request_approval_node)
    builder.add_node("process_approval", process_approval_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_exception", handle_exception_node)

    # Set entry point
    builder.set_entry_point("extract_fields")

    # Core flow: extract -> validate -> duplicate
    builder.add_edge("extract_fields", "validate_po")
    builder.add_edge("validate_po", "check_duplicates")
    builder.add_edge("check_duplicates", "load_context")

    # Analyst-Critic pattern
    builder.add_edge("load_context", "analyst_propose")
    builder.add_edge("analyst_propose", "critic_review")

    # Conditional: based on Critic's decision
    builder.add_conditional_edges(
        "critic_review",
        route_action,
        {
            "auto_approve": "finalize",
            "hitl_required": "request_approval",
            "delay_payment": "finalize",  # Mark as delayed
            "reject": "finalize",  # Mark as rejected
            "exception": "handle_exception",
        },
    )

    # Legacy approval flow (for HITL cases)
    builder.add_edge("request_approval", "process_approval")
    builder.add_edge("process_approval", "finalize")

    # Execute action node before finalize (for special actions)
    builder.add_edge("execute_action", "finalize")

    # Finalization
    builder.add_edge("finalize", END)
    builder.add_edge("handle_exception", END)

    return builder


def route_action(state: InvoiceState) -> str:
    """Route based on Critic's review and Analyst's proposal."""

    critic = state.get("critic_review")
    analyst = state.get("analyst_proposal")

    if not critic:
        return "exception"

    # Priority 1: If Critic blocked, reject
    if critic.blocked:
        logger.info(f"Invoice {state.get('invoice_id')} blocked by Critic: {critic.block_reason}")
        return "reject"

    # Priority 2: If Analyst recommended HITL, go to approval
    if analyst and analyst.proposed_action == "HITL_REQUIRED":
        return "hitl_required"

    # Priority 3: If Analyst recommended delay, mark as delayed
    if analyst and analyst.proposed_action == "DELAY_PAYMENT":
        return "delay_payment"

    # Priority 4: If Analyst recommended reject
    if analyst and analyst.proposed_action == "REJECT":
        return "reject"

    # Priority 5: If Critic says proceed and auto-approve eligible
    if critic.can_proceed:
        signals = [s for s in critic.signals if s.type == "TRUST"]
        for signal in signals:
            if signal.severity == "INFO":
                return "auto_approve"

    # Default: HITL required
    return "hitl_required"


async def load_context_node(state: InvoiceState) -> InvoiceState:
    """Load financial context and vendor trust battery."""
    logger.info(f"Loading context for invoice {state.get('invoice_id')}")

    settings = get_settings()
    extracted = state.get("extracted_data")

    if not extracted:
        return {**state, "error": "No extracted data for context loading"}

    # Build financial context
    financial_context = FinancialContext(
        current_cash=50000.0,  # In production, fetch from DB/API
        monthly_burn_rate=15000.0,  # In production, calculate from historical data
        runway_days=100.0,
        payroll_date="15",  # 15th of month
        payroll_amount=25000.0,
        safety_buffer=settings.safety_buffer,
        strategy_mode=settings.strategy_mode,
        auto_approve_threshold=1000.0,
        budgets={"Software": 5000.0, "Infrastructure": 10000.0, "Services": 3000.0},
        category_limits={"Software": 8000.0, "Infrastructure": 15000.0, "Services": 5000.0},
    )

    # Get vendor trust battery from Neo4j or service
    trust_service = get_trust_battery_service()
    vendor_name = extracted.vendor_name

    trust_info = {
        "vendor_name": vendor_name,
        "trust_level": 2,  # Default to STANDARD
        "total_decisions": 0,
        "auto_approved_count": 0,
        "manual_review_count": 0,
        "success_rate": 1.0,
    }

    try:
        trust_level = await trust_service.get_vendor_trust(vendor_name)
        trust_info["trust_level"] = trust_level.value
        trust_info["total_decisions"] = 10  # Mock data
        trust_info["auto_approved_count"] = 8
        trust_info["manual_review_count"] = 2
        trust_info["success_rate"] = 0.95
    except Exception as e:
        logger.warning(f"Could not load trust battery for {vendor_name}: {e}")

    # Build reasoning chain
    reasoning_chain = [
        f"[{datetime.now().isoformat()}] Loaded financial context: cash=${financial_context.current_cash:.0f}, runway={financial_context.runway_days:.0f} days",
        f"[{datetime.now().isoformat()}] Loaded trust battery for {vendor_name}: Level {trust_info['trust_level']}",
        f"[{datetime.now().isoformat()}] Strategy mode: {financial_context.strategy_mode}",
    ]

    return {
        **state,
        "status": InvoiceStatus.VALIDATING,
        "financial_context": financial_context.model_dump(),
        "trust_battery": trust_info,
        "reasoning_chain": reasoning_chain,
    }


async def analyst_propose_node(state: InvoiceState) -> InvoiceState:
    """Analyst node: Pattern detection and proposal generation."""
    logger.info(f"Analyst proposing action for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    financial_context_dict = state.get("financial_context")
    trust_info = state.get("trust_battery")
    reasoning_chain = state.get("reasoning_chain", [])

    if not extracted:
        return {**state, "error": "No extracted data for analyst"}

    # Build FinancialContext from dict
    if financial_context_dict:
        financial_context = FinancialContext(**financial_context_dict)
    else:
        settings = get_settings()
        financial_context = FinancialContext()

    # Get trust level
    from app.services.trust_battery import TrustLevel
    trust_level = TrustLevel(trust_info.get("trust_level", 2))

    try:
        analyst = get_analyst_agent()
        proposal = await analyst.analyze(
            invoice_data=extracted,
            financial_context=financial_context,
            trust_level=trust_level,
            trust_threshold=1000.0,  # From settings
        )

        # Update reasoning chain
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Analyst detected {len(proposal.anomalies)} anomaly(ies)")
        for anomaly in proposal.anomalies:
            reasoning_chain.append(f"  - {anomaly}")
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Analyst proposal: {proposal.proposed_action.value}")
        reasoning_chain.append(f"  - Confidence: {proposal.confidence:.0%}")
        reasoning_chain.append(f"  - Reasoning: {proposal.reasoning}")

        return {
            **state,
            "status": InvoiceStatus.VALIDATING,
            "analyst_proposal": proposal,
            "reasoning_chain": reasoning_chain,
        }

    except Exception as e:
        logger.error(f"Analyst error: {e}")
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Analyst error: {str(e)}")
        return {
            **state,
            "error": f"Analyst failed: {str(e)}",
            "reasoning_chain": reasoning_chain,
        }


async def critic_review_node(state: InvoiceState) -> InvoiceState:
    """Critic node: Safety checks using Priority Matrix."""
    logger.info(f"Critic reviewing invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    financial_context_dict = state.get("financial_context")
    analyst_proposal = state.get("analyst_proposal")
    trust_info = state.get("trust_battery")
    reasoning_chain = state.get("reasoning_chain", [])

    if not extracted:
        return {**state, "error": "No extracted data for critic"}

    # Build FinancialContext from dict
    if financial_context_dict:
        financial_context = FinancialContext(**financial_context_dict)
    else:
        financial_context = FinancialContext()

    # Get trust level
    trust_level = trust_info.get("trust_level", 2)
    settings = get_settings()

    try:
        critic = get_critic_agent()
        review = await critic.review(
            invoice_data=extracted,
            financial_context=financial_context,
            trust_level=trust_level,
            trust_threshold=1000.0,
        )

        # Update reasoning chain
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Critic safety check results:")
        for signal in review.signals:
            reasoning_chain.append(f"  - [{signal.type}] {signal.severity}: {signal.message}")
            reasoning_chain.append(f"    -> {signal.recommendation}")
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Critic decision: {'PROCEED' if review.can_proceed else 'BLOCKED'}")
        reasoning_chain.append(f"  - Risk score: {review.risk_score:.0%}")

        return {
            **state,
            "status": InvoiceStatus.VALIDATING,
            "critic_review": review,
            "reasoning_chain": reasoning_chain,
        }

    except Exception as e:
        logger.error(f"Critic error: {e}")
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Critic error: {str(e)}")
        return {
            **state,
            "error": f"Critic failed: {str(e)}",
            "reasoning_chain": reasoning_chain,
        }


async def execute_action_node(state: InvoiceState) -> InvoiceState:
    """Execute the approved action (update Neo4j, trust battery, etc.)."""
    logger.info(f"Executing action for invoice {state.get('invoice_id')}")

    analyst_proposal = state.get("analyst_proposal")
    critic_review = state.get("critic_review")
    extracted = state.get("extracted_data")
    reasoning_chain = state.get("reasoning_chain", [])

    if not analyst_proposal or not extracted:
        return {**state, "error": "No proposal or extracted data"}

    action = analyst_proposal.proposed_action

    # Update vendor trust battery based on outcome
    try:
        trust_service = get_trust_battery_service()
        neo4j_client = get_neo4j_client()

        if action == "AUTO_APPROVE":
            await trust_service.record_decision(
                vendor_name=extracted.vendor_name,
                decision="APPROVED",
                was_auto_approved=True,
            )
            reasoning_chain.append(f"[{datetime.now().isoformat()}] Updated trust battery for {extracted.vendor_name}: +1 auto-approve")
        elif action == "HITL_REQUIRED":
            await trust_service.record_decision(
                vendor_name=extracted.vendor_name,
                decision="PENDING_REVIEW",
                was_auto_approved=False,
            )
            reasoning_chain.append(f"[{datetime.now().isoformat()}] Updated trust battery for {extracted.vendor_name}: marked for manual review")
        elif action == "DELAY_PAYMENT":
            reasoning_chain.append(f"[{datetime.now().isoformat()}] Payment delayed for {extracted.vendor_name}: {analyst_proposal.reasoning}")
        elif action == "REJECT":
            await trust_service.record_decision(
                vendor_name=extracted.vendor_name,
                decision="REJECTED",
                was_auto_approved=False,
            )
            reasoning_chain.append(f"[{datetime.now().isoformat()}] Updated trust battery for {extracted.vendor_name}: rejection recorded")

        # Create invoice record in Neo4j
        await neo4j_client.create_invoice(
            invoice_id=str(state["invoice_id"]),
            vendor_name=extracted.vendor_name,
            amount=float(extracted.total_amount),
            status=action.value,
            due_date=str(extracted.due_date),
        )
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Created invoice record in knowledge graph")

    except Exception as e:
        logger.warning(f"Could not update trust/Neo4j: {e}")
        reasoning_chain.append(f"[{datetime.now().isoformat()}] Warning: Could not update trust/Neo4j: {str(e)}")

    return {
        **state,
        "reasoning_chain": reasoning_chain,
    }


def should_approve(state: InvoiceState) -> str:
    """Determine if invoice needs approval."""
    settings = get_settings()

    # Check confidence
    if state.get("extracted_data"):
        confidence = state["extracted_data"].overall_confidence
        if confidence < settings.extraction_confidence_threshold:
            return "exception"

    # Check PO validation
    if state.get("po_validation") and not state["po_validation"].is_valid:
        if not state["po_validation"].is_within_tolerance:
            return "exception"

    # Check duplicates
    if state.get("duplicate_check") and state["duplicate_check"].is_duplicate:
        return "exception"

    # Check amount thresholds for approval
    if state.get("extracted_data"):
        total = float(state["extracted_data"].total_amount)
        if total > 10000:  # High value requires approval
            return "approve"

    return "finalize"


async def extract_fields_node(state: InvoiceState) -> InvoiceState:
    """Extract fields from raw invoice content."""
    invoice_id = state.get("invoice_id")
    logger.info(f"Extracting fields for invoice {invoice_id}")

    start_time = time.time()

    try:
        extractor = get_extractor_agent()
        result = await extractor.extract_from_text(state["raw_content"])

        duration_ms = (time.time() - start_time) * 1000

        if result.success and result.data:
            # Trace the extraction
            await InvoiceWorkflowTracer.trace_extraction(
                invoice_id=invoice_id,
                raw_content=state["raw_content"][:500],  # Truncate for tracing
                extracted_data=result.data.model_dump(),
                duration_ms=duration_ms,
            )

            return {
                **state,
                "status": InvoiceStatus.EXTRACTED,
                "extracted_data": result.data,
                "raw_text": state["raw_content"],
            }
        else:
            return {
                **state,
                "status": InvoiceStatus.EXCEPTION,
                "error": result.error or "Extraction failed",
            }

    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return {
            **state,
            "status": InvoiceStatus.EXCEPTION,
            "error": str(e),
        }


async def validate_po_node(state: InvoiceState) -> InvoiceState:
    """Validate PO matching."""
    logger.info(f"Validating PO for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data to validate"}

    # Simulate PO validation (in production, query database)
    po_number = extracted.po_number

    if po_number:
        # Simulate PO lookup
        validation = POValidationResult(
            is_valid=True,
            po_number=po_number,
            po_amount=extracted.total_amount,
            invoice_amount=extracted.total_amount,
            variance=Decimal("0"),
            variance_percentage=0.0,
        )
    else:
        validation = POValidationResult(
            is_valid=False,
            po_number=None,
            invoice_amount=extracted.total_amount,
            errors=["No PO number provided"],
        )

    return {
        **state,
        "status": InvoiceStatus.VALIDATING,
        "po_validation": validation,
    }


async def check_duplicates_node(state: InvoiceState) -> InvoiceState:
    """Check for duplicate invoices."""
    logger.info(f"Checking duplicates for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data to check"}

    # Simulate duplicate check (in production, query database)
    duplicate_check = DuplicateCheck(
        is_duplicate=False,
        potential_duplicates=[],
        match_fields={
            "vendor": extracted.vendor_name,
            "invoice_number": extracted.invoice_number,
            "amount": str(extracted.total_amount),
        },
    )

    return {
        **state,
        "duplicate_check": duplicate_check,
    }


async def decide_escalation_node(state: InvoiceState) -> InvoiceState:
    """Decide if escalation is needed."""
    logger.info(f"Deciding escalation for invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    # Calculate risk level
    total = float(extracted.total_amount)
    if total > 50000:
        risk_level = RiskLevel.CRITICAL
    elif total > 10000:
        risk_level = RiskLevel.HIGH
    elif total > 1000:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW

    decision = should_approve(state)

    return {
        **state,
        "requires_approval": decision == "approve",
        "risk_level": risk_level,
    }


async def request_approval_node(state: InvoiceState) -> InvoiceState:
    """Request human approval with interrupt."""

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    # Create approval request
    approval_request = ApprovalRequest(
        invoice_id=state["invoice_id"],
        reason="Invoice requires approval based on amount or validation",
        risk_level=state.get("risk_level", RiskLevel.MEDIUM),
        suggested_action="Review and approve/reject",
        extracted_data=extracted,
    )

    # Interrupt for human review
    interrupt_data = {
        "action": "invoice_approval",
        "invoice_id": str(approval_request.invoice_id),
        "vendor": extracted.vendor_name,
        "amount": str(extracted.total_amount),
        "currency": extracted.currency,
        "due_date": str(extracted.due_date),
        "po_number": extracted.po_number or "Not provided",
        "risk_level": approval_request.risk_level.value,
        "message": f"Invoice for {extracted.vendor_name} for {extracted.currency} {extracted.total_amount} requires approval",
    }

    # This will pause the graph and return control
    interrupt_result = interrupt(interrupt_data)

    # Process the human response
    if isinstance(interrupt_result, dict):
        action = interrupt_result.get("action", "approve")
        if action == "approve":
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.APPROVED,
                comments=interrupt_result.get("comments"),
                approver_id=interrupt_result.get("approver_id", "unknown"),
                approver_email=interrupt_result.get("approver_email", "unknown"),
            )
        elif action == "reject":
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.REJECTED,
                comments=interrupt_result.get("reason", "Rejected by approver"),
                approver_id=interrupt_result.get("approver_id", "unknown"),
                approver_email=interrupt_result.get("approver_email", "unknown"),
            )
        else:
            approval_action = ApprovalAction(
                invoice_id=state["invoice_id"],
                decision=ApprovalStatus.PENDING,
                comments="No action taken",
                approver_id="unknown",
                approver_email="unknown",
            )
    else:
        approval_action = ApprovalAction(
            invoice_id=state["invoice_id"],
            decision=ApprovalStatus.PENDING,
            comments="Invalid response",
            approver_id="unknown",
            approver_email="unknown",
        )

    return {
        **state,
        "status": InvoiceStatus.APPROVAL_PENDING,
        "approval_request": approval_request,
        "approval_action": approval_action,
    }


async def process_approval_node(state: InvoiceState) -> InvoiceState:
    """Process the approval decision."""
    logger.info(f"Processing approval for invoice {state.get('invoice_id')}")

    action = state.get("approval_action")
    if not action:
        return {**state, "error": "No approval action"}

    if action.decision == ApprovalStatus.APPROVED:
        new_status = InvoiceStatus.APPROVED
    elif action.decision == ApprovalStatus.REJECTED:
        new_status = InvoiceStatus.REJECTED
    else:
        new_status = InvoiceStatus.APPROVAL_PENDING

    return {
        **state,
        "status": new_status,
    }


async def finalize_node(state: InvoiceState) -> InvoiceState:
    """Finalize the invoice processing."""
    logger.info(f"Finalizing invoice {state.get('invoice_id')}")

    extracted = state.get("extracted_data")
    if not extracted:
        return {**state, "error": "No extracted data"}

    result = ProcessingResult(
        invoice_id=state["invoice_id"],
        status=state.get("status", InvoiceStatus.EXTRACTED),
        extraction=extracted,
        po_validation=state.get("po_validation"),
        duplicate_check=state.get("duplicate_check"),
        requires_approval=state.get("requires_approval", False),
        approval_request=state.get("approval_request"),
    )

    return {
        **state,
        "status": state.get("status", InvoiceStatus.EXTRACTED),
        "result": result,
    }


async def handle_exception_node(state: InvoiceState) -> InvoiceState:
    """Handle exception case."""
    logger.error(f"Exception for invoice {state.get('invoice_id')}: {state.get('error')}")

    result = ProcessingResult(
        invoice_id=state["invoice_id"],
        status=InvoiceStatus.EXCEPTION,
        extraction=state.get("extracted_data"),
        error_message=state.get("error", "Unknown error"),
        requires_approval=False,
    )

    return {
        **state,
        "status": InvoiceStatus.EXCEPTION,
        "result": result,
    }


class InvoiceWorkflow:
    """Workflow orchestrator for invoice processing."""

    def __init__(self):
        """Initialize the workflow."""
        self.builder = create_invoice_workflow()
        self.checkpointer = MemorySaver()
        self.graph = self.builder.compile(checkpointer=self.checkpointer)

    async def process_invoice(
        self,
        invoice_data: InvoiceCreate,
        raw_content: str,
        thread_id: str | None = None,
    ) -> ProcessingResult:
        """Process an invoice through the workflow."""
        import time

        import uuid

        thread_id = thread_id or str(uuid.uuid4())
        invoice_id = str(uuid4())
        workflow_start = time.time()

        initial_state: InvoiceState = {
            "invoice_data": invoice_data,
            "raw_content": raw_content,
            "invoice_id": invoice_id,
            "status": InvoiceStatus.NEW,
            "extracted_data": None,
            "raw_text": "",
            "po_validation": None,
            "duplicate_check": None,
            # Analyst-Critic pattern state
            "financial_context": None,
            "analyst_proposal": None,
            "critic_review": None,
            "trust_battery": None,
            "reasoning_chain": None,
            # Approval state
            "requires_approval": False,
            "approval_request": None,
            "approval_action": None,
            # Output
            "result": None,
            "error": None,
        }

        config = {"configurable": {"thread_id": thread_id}}

        # Start workflow trace
        trace = create_workflow_trace(
            invoice_id=invoice_id,
            input_data={
                "vendor": invoice_data.vendor_name,
                "amount": str(invoice_data.total_amount),
                "thread_id": thread_id,
            },
        )

        try:
            result = await self.graph.ainvoke(initial_state, config=config)
            duration_ms = (time.time() - workflow_start) * 1000

            # Trace workflow completion
            await InvoiceWorkflowTracer.trace_workflow_completion(
                invoice_id=invoice_id,
                workflow_id=thread_id,
                final_status=result.get("status", InvoiceStatus.EXCEPTION).value,
                duration_ms=duration_ms,
            )

            trace.end(output={"status": result.get("status")})

            return result.get("result") or ProcessingResult(
                invoice_id=invoice_id,
                status=InvoiceStatus.EXCEPTION,
                extraction=None,
                requires_approval=False,
                error_message=result.get("error", "Unknown error"),
            )
        except Exception as e:
            duration_ms = (time.time() - workflow_start) * 1000
            logger.error(f"Workflow error: {e}")

            # Trace error
            await InvoiceWorkflowTracer.trace_workflow_completion(
                invoice_id=invoice_id,
                workflow_id=thread_id,
                final_status="error",
                duration_ms=duration_ms,
            )

            trace.end(output={"error": str(e)})

            return ProcessingResult(
                invoice_id=invoice_id,
                status=InvoiceStatus.EXCEPTION,
                extraction=None,
                requires_approval=False,
                error_message=str(e),
            )

    async def resume_with_approval(
        self,
        thread_id: str,
        decision: dict,
    ) -> ProcessingResult:
        """Resume workflow after human approval."""
        config = {"configurable": {"thread_id": thread_id}}

        command = Command(resume=decision)
        result = await self.graph.ainvoke(command, config=config)

        return result.get("result")


# Singleton workflow instance
_workflow: InvoiceWorkflow | None = None


def get_invoice_workflow() -> InvoiceWorkflow:
    """Get the singleton workflow instance."""
    global _workflow
    if _workflow is None:
        _workflow = InvoiceWorkflow()
    return _workflow
