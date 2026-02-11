"""
Real integration test with actual Neo4j connection
Run with: ai/.venv/bin/python temporal/test_real_integration.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporal.activities.agents import analyst_evaluate, critic_review, AnalystProposal
from temporal.infrastructure.neo4j import Neo4jClient


async def test_neo4j_connection():
    """Test real Neo4j connection."""
    print("\n=== Testing Neo4j Connection ===")
    
    # Use host.docker.internal or localhost
    os.environ["NEO4J_URI"] = "bolt://localhost:7687"
    os.environ["NEO4J_USER"] = "neo4j"
    os.environ["NEO4J_PASSWORD"] = "founderos_secret"
    
    client = Neo4jClient()
    
    try:
        await client.connect()
        print("✓ Connected to Neo4j")
        
        # Try to query
        invoices = await client.get_invoices_by_vendor("TestVendor")
        print(f"✓ Query successful, found {len(invoices)} invoices")
        
        await client.close()
        return True
    except Exception as e:
        print(f"✗ Neo4j connection failed: {e}")
        return False


async def test_analyst_with_neo4j():
    """Test analyst with real Neo4j backend."""
    print("\n=== Testing Analyst with Neo4j ===")
    
    os.environ["NEO4J_URI"] = "bolt://localhost:7687"
    os.environ["NEO4J_USER"] = "neo4j"
    os.environ["NEO4J_PASSWORD"] = "founderos_secret"
    
    invoice_data = {
        "vendor_name": "AWS",
        "total_amount": 1000.00,
        "invoice_number": "INV-TEST-001",
        "due_date": "2025-03-15",
        "currency": "USD",
        "overall_confidence": 0.95,
    }
    
    try:
        result = await analyst_evaluate(invoice_data)
        print(f"✓ Analyst returned: {result.proposed_action}")
        print(f"  Confidence: {result.confidence:.2%}")
        print(f"  Anomalies: {len(result.anomalies)}")
        if result.anomalies:
            print(f"  First anomaly: {result.anomalies[0].type}")
        return True
    except Exception as e:
        print(f"✗ Analyst failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_critic_all_checks():
    """Test all 5 critic safety checks."""
    print("\n=== Testing Critic - All 5 Safety Checks ===")
    
    # Set financial context
    os.environ["CURRENT_CASH"] = "50000"
    os.environ["MONTHLY_BURN_RATE"] = "15000"
    os.environ["SAFETY_BUFFER"] = "10000"
    os.environ["STRATEGY_MODE"] = "OPTIMIZE"
    os.environ["PAYROLL_DATE"] = "15"
    os.environ["PAYROLL_AMOUNT"] = "25000"
    
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
        
        print(f"✓ Critic completed review")
        print(f"  Can proceed: {result['can_proceed']}")
        print(f"  Blocked: {result['blocked']}")
        print(f"  Risk score: {result['risk_score']:.2f}")
        print(f"  Signals generated: {len(result['signals'])}")
        
        # Verify all 5 signals
        signal_types = [s['type'] for s in result['signals']]
        expected = ['RUNWAY', 'STRATEGY', 'CONTRACT', 'TRUST', 'BUDGET']
        
        print("\n  Signal breakdown:")
        for signal in result['signals']:
            print(f"    - {signal['type']}: {signal['severity']} - {signal['message'][:60]}...")
        
        missing = set(expected) - set(signal_types)
        if missing:
            print(f"\n  ✗ Missing signals: {missing}")
            return False
        
        print(f"\n  ✓ All 5 priority matrix checks present!")
        return True
        
    except Exception as e:
        print(f"✗ Critic failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_critic_blocks_dangerous():
    """Test critic blocks dangerous payment."""
    print("\n=== Testing Critic - Dangerous Payment Blocking ===")
    
    # Dangerous context: payment would go below safety buffer
    os.environ["CURRENT_CASH"] = "10500"
    os.environ["SAFETY_BUFFER"] = "10000"
    os.environ["MONTHLY_BURN_RATE"] = "15000"
    os.environ["STRATEGY_MODE"] = "SURVIVAL"
    
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
        
        if result['blocked']:
            print(f"✓ Correctly blocked dangerous payment")
            print(f"  Reason: {result['block_reason']}")
            return True
        else:
            print(f"✗ Should have blocked but didn't!")
            print(f"  Can proceed: {result['can_proceed']}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_critic_survival_mode():
    """Test critic in SURVIVAL mode."""
    print("\n=== Testing Critic - SURVIVAL Mode ===")
    
    # SURVIVAL mode: block payments >10% of cash
    os.environ["CURRENT_CASH"] = "50000"
    os.environ["STRATEGY_MODE"] = "SURVIVAL"
    os.environ["MONTHLY_BURN_RATE"] = "15000"
    os.environ["SAFETY_BUFFER"] = "10000"
    
    invoice_data = {
        "vendor_name": "Large Vendor",
        "total_amount": 6000.00,  # >10% of $50k
        "invoice_number": "INV-LARGE",
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
        
        strategy_signal = next(s for s in result['signals'] if s['type'] == 'STRATEGY')
        
        if strategy_signal['severity'] == 'CRITICAL':
            print(f"✓ SURVIVAL mode correctly flagged large payment")
            print(f"  Message: {strategy_signal['message']}")
            return True
        else:
            print(f"✗ SURVIVAL mode should have flagged as CRITICAL")
            print(f"  Got severity: {strategy_signal['severity']}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests."""
    print("=" * 70)
    print("REAL INTEGRATION TEST - Temporal Activities")
    print("=" * 70)
    
    results = []
    
    # Test Neo4j connection (optional - skip if not running)
    print("\n[Optional] Testing Neo4j connection...")
    neo4j_result = await test_neo4j_connection()
    if neo4j_result:
        results.append(await test_analyst_with_neo4j())
    else:
        print("  Skipping analyst Neo4j test (Neo4j not available)")
    
    # Test critic (doesn't need Neo4j)
    results.append(await test_critic_all_checks())
    results.append(await test_critic_blocks_dangerous())
    results.append(await test_critic_survival_mode())
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ ALL TESTS PASSED!")
    else:
        print(f"✗ {total - passed} test(s) failed")
    
    print("=" * 70)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
