import structlog
from typing import Dict, Any
from src.activities.validation import validate_invoice_math
from src.agents.trust_manager import TrustBatteryManager
from src.utils.timing import timed

logger = structlog.get_logger()

async def analyze_invoice(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = invoice_data.get("invoice_number", "unknown")
    vendor_name = invoice_data.get("vendor_name", "unknown")
    total_amount = float(invoice_data.get("total_amount") or 0)
    
    log = logger.bind(trace_id=trace_id, vendor=vendor_name)
    log.info("analysis_started")

    async with timed("invoice_analysis", trace_id):
        # 1. Mathematical Validation (Ported from critic.ts)
        async with timed("math_validation", trace_id):
            math_result = validate_invoice_math(invoice_data)
    if not math_result["is_valid"]:
        log.warning("math_validation_failed", issues=math_result["issues"])
        return {
            "decision": "HITL_REQUIRED",
            "risk_score": 0.8,
            "reasoning": f"Math Validation Failed: {', '.join(math_result['issues'])}"
        }

    # 2. Trust Battery Check (Ported from trust-battery.ts)
    trust_manager = TrustBatteryManager()
    trust_check = await trust_manager.check_auto_approve_eligibility(vendor_name, total_amount)
    
    # 3. Critic Agent Evaluation (Deep Analysis)
    try:
        from src.agents.critic import get_critic_agent, FinancialContext
        from src.schemas.invoice import InvoiceExtracted
        
        # Mock context for now
        ctx = FinancialContext(
            current_cash=50000.0, monthly_burn_rate=15000.0, 
            runway_days=100.0, safety_buffer=5000.0,
            strategy_mode="OPTIMIZE", payroll_amount=10000.0
        )
        
        critic = get_critic_agent()
        extracted = InvoiceExtracted(**invoice_data)
        
        evaluation = await critic.review(
            invoice_data=extracted,
            financial_context=ctx,
            trust_level=1, # Default to level 1 for safety
            trust_threshold=trust_check["threshold"]
        )
        
        # Decision logic considering Trust + Critic
        if evaluation.blocked:
            decision = "REJECT"
        elif trust_check["eligible"] and evaluation.risk_score < 0.3:
            decision = "AUTO_APPROVE"
        else:
            decision = "HITL_REQUIRED"
            
        log.info("analysis_complete", decision=decision, risk_score=evaluation.risk_score)
        
        return {
            "decision": decision,
            "risk_score": evaluation.risk_score,
            "reasoning": f"Trust: {trust_check['trust_level']}. Reasoning: {'. '.join(evaluation.reasoning)}",
            "signals": [s.model_dump() for s in evaluation.signals],
        }

    except Exception as e:
        log.error("critic_evaluation_failed", error=str(e))
        return {
            "decision": "HITL_REQUIRED",
            "risk_score": 1.0,
            "reasoning": f"Internal system error during deep analysis: {str(e)}"
        }
