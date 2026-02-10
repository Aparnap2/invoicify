"""
Manual test script to verify temporal activities work
Run with: python temporal/test_manual.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporal.activities.agents import analyst_evaluate, critic_review, AnalystProposal
from decimal import Decimal


async def test_analyst():
    """Test analyst activity."""
    print("\n=== Testing Analyst Activity ===")
    
    invoice_data = {
        "vendor_name": "Test Vendor",
        "total_amount": 1000.00,
        "invoice_number": "INV-001",
        "due_date": "2025-03-15",
        "currency": "USD",
        "overall_confidence": 0.95,
    }
    
    try:
        result = await analyst_evaluate(invoice_data)
        print(f"✓ Analyst returned: {result.proposed_action}")
        print(f"  Confidence: {result.confidence:.2%}")
        print(f"  Anomalies: {len(result.anomalies)}")
        print(f"  Reasoning: {result.reasoning[0]}")
        return True
    except Exception as e:
        print(f"✗ Analyst failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_critic():
    """Test critic activity."""
    print("\n=== Testing Critic Activity ===")
    
    # Set environment variables for financial context
    os.environ["CURRENT_CASH"] = "50000"
    os.environ["MONTHLY_BURN_RATE"] = "15000"
    os.environ["SAFETY_BUFFER"] = "10000"
    os.environ["STRATEGY_MODE"] = "OPTIMIZE"
    
    invoice_data = {
        "vendor_name": "AWS",
        "total_amount": 1000.00,
        "invoice_number": "INV-001",
        "due_date": "2025-03-15",
        "currency": "USD",
        "trust_level": 2,
    }
    
    analyst_proposal = AnalystProposal(
        proposed_action="AUTO_APPROVE",
        confidence=0.9,
        anomalies=[],
        vendor_patterns=[],
        reasoning=["Normal invoice"],
    )
    
    try:
        result = await critic_review(invoice_data, analyst_proposal)
        print(f"✓ Critic returned: can_proceed={result['can_proceed']}")
        print(f"  Blocked: {result['blocked']}")
        print(f"  Risk Score: {result['risk_score']:.2f}")
        print(f"  Signals: {len(result['signals'])}")
        print(f"  Signal types: {[s['type'] for s in result['signals']]}")
        return True
    except Exception as e:
        print(f"✗ Critic failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_critic_blocks_dangerous_payment():
    """Test critic blocks dangerous payment."""
    print("\n=== Testing Critic Blocks Dangerous Payment ===")
    
    # Set dangerous financial context
    os.environ["CURRENT_CASH"] = "10500"  # Payment would leave $9500
    os.environ["SAFETY_BUFFER"] = "10000"
    os.environ["MONTHLY_BURN_RATE"] = "15000"
    
    invoice_data = {
        "vendor_name": "Expensive Vendor",
        "total_amount": 1000.00,
        "invoice_number": "INV-DANGER",
        "due_date": "2025-03-15",
        "currency": "USD",
        "trust_level": 2,
    }
    
    analyst_proposal = AnalystProposal(
        proposed_action="AUTO_APPROVE",
        confidence=0.9,
        anomalies=[],
        vendor_patterns=[],
        reasoning=["Normal invoice"],
    )
    
    try:
        result = await critic_review(invoice_data, analyst_proposal)
        print(f"✓ Critic returned: can_proceed={result['can_proceed']}")
        print(f"  Blocked: {result['blocked']}")
        print(f"  Block reason: {result['block_reason']}")
        
        if result['blocked']:
            print("  ✓ Correctly blocked dangerous payment!")
            return True
        else:
            print("  ✗ Should have blocked but didn't!")
            return False
    except Exception as e:
        print(f"✗ Critic failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("TEMPORAL ACTIVITIES MANUAL TEST")
    print("=" * 60)
    
    results = []
    
    results.append(await test_analyst())
    results.append(await test_critic())
    results.append(await test_critic_blocks_dangerous_payment())
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
