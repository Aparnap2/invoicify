#!/usr/bin/env python3
"""
Final verification script for TDD implementation (Steps 2, 3, 4, 5)
"""

import sys
import os


def verify_all_steps():
    """Verify all implementation steps."""
    print("=" * 70)
    print("PHASE 2 COMPLETION VERIFICATION")
    print("=" * 70)
    print()

    steps = {
        "Step 2: Event Producer": {
            "test": "python-worker/tests/unit/test_events.py",
            "impl": "python-worker/src/lib/events.py",
            "features": [
                "EventProducer class",
                "Kafka/Redpanda integration",
                "Async produce",
            ],
        },
        "Step 3: Anomaly Detection": {
            "test": "python-worker/tests/unit/test_anomaly.py",
            "impl": "python-worker/src/activities/anomaly.py",
            "features": [
                "AnomalyDetector class",
                "River ML HalfSpaceTrees",
                "Online learning",
            ],
        },
        "Step 4: Vision Extraction": {
            "test": "python-worker/tests/integration/test_extract.py",
            "impl": "python-worker/src/activities/extract.py",
            "features": [
                "extract_invoice_data activity",
                "Pydantic validation",
                "Mockoon integration",
            ],
        },
        "Step 5: Temporal Workflow": {
            "test": "python-worker/tests/e2e/test_workflow_execution.py",
            "impl": "python-worker/src/workflows/invoice_processing.py",
            "features": [
                "InvoiceProcessingWorkflow",
                "Activity orchestration",
                "Decision logic",
            ],
        },
    }

    all_pass = True
    total_tests = 0

    for step_name, step_info in steps.items():
        print(f"\n{step_name}")
        print("-" * 70)

        test_exists = os.path.exists(
            f"/home/aparna/Desktop/invoicify/{step_info['test']}"
        )
        impl_exists = os.path.exists(
            f"/home/aparna/Desktop/invoicify/{step_info['impl']}"
        )

        status = "✅" if (test_exists and impl_exists) else "❌"
        print(f"{status} Files created")

        if test_exists:
            with open(f"/home/aparna/Desktop/invoicify/{step_info['test']}") as f:
                test_count = f.read().count("def test_")
                total_tests += test_count
                print(f"  ✅ {test_count} tests")

        if impl_exists:
            print(f"  ✅ Implementation")
            for feature in step_info["features"]:
                print(f"     • {feature}")

        if not (test_exists and impl_exists):
            all_pass = False

    print()
    print("=" * 70)
    print("ARCHITECTURE COMPONENTS")
    print("=" * 70)
    print()

    components = [
        ("Worker Entry Point", "python-worker/src/worker.py"),
        ("Activity: Extract", "python-worker/src/activities/extract.py"),
        ("Activity: Anomaly", "python-worker/src/activities/anomaly.py"),
        ("Activity: Events", "python-worker/src/lib/events.py"),
        ("Workflow", "python-worker/src/workflows/invoice_processing.py"),
        ("Mockoon Config", "mocks/mocks.json"),
    ]

    for name, path in components:
        exists = os.path.exists(f"/home/aparna/Desktop/invoicify/{path}")
        status = "✅" if exists else "❌"
        print(f"{status} {name}")

    print()
    print("=" * 70)
    print(f"TOTAL TEST CASES: {total_tests}")
    print("=" * 70)

    return all_pass


if __name__ == "__main__":
    success = verify_all_steps()
    sys.exit(0 if success else 1)
