#!/usr/bin/env python3
"""
Hiring Assessment Runner

This script provides a command-line interface for running the complete
hiring assessment framework with automated evaluation and reporting.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from evaluation.automation.automated_evaluator import AutomatedEvaluator

def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'hiring_assessment_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        ]
    )

def validate_inputs(candidate_name: str, challenge_name: str, solution_path: str) -> bool:
    """Validate input parameters"""
    if not candidate_name or not candidate_name.strip():
        print("Error: Candidate name cannot be empty")
        return False

    if not challenge_name or not challenge_name.strip():
        print("Error: Challenge name cannot be empty")
        return False

    solution_path = Path(solution_path)
    if not solution_path.exists():
        print(f"Error: Solution path {solution_path} does not exist")
        return False

    if not solution_path.is_dir():
        print(f"Error: Solution path {solution_path} is not a directory")
        return False

    # Check for Python files
    python_files = list(solution_path.rglob("*.py"))
    if not python_files:
        print("Warning: No Python files found in solution path")
        return True  # Allow this but warn user

    return True

def generate_assessment_report(evaluation, output_dir: Path) -> Path:
    """Generate comprehensive assessment report"""
    report_data = {
        "assessment_metadata": {
            "candidate_name": evaluation.candidate_name,
            "challenge_name": evaluation.challenge_name,
            "submission_time": evaluation.submission_time.isoformat(),
            "evaluation_time": datetime.now().isoformat(),
            "framework_version": "1.0.0"
        },
        "results": {
            "overall_score": evaluation.overall_score,
            "recommendation": evaluation.recommendation,
            "summary": evaluation.summary
        },
        "detailed_results": []
    }

    # Add detailed evaluation results
    for result in evaluation.evaluation_results:
        score_percent = (result.score / result.max_score) * 100
        result_data = {
            "evaluation_type": result.evaluation_type.value,
            "score": result.score,
            "max_score": result.max_score,
            "percentage": round(score_percent, 1),
            "status": "PASS" if result.score >= result.max_score * 0.7 else "NEEDS_IMPROVEMENT",
            "details": result.details,
            "issues_count": len(result.issues),
            "recommendations_count": len(result.recommendations)
        }

        # Add top issues (limited for readability)
        if result.issues:
            result_data["top_issues"] = result.issues[:10]

        # Add recommendations
        if result.recommendations:
            result_data["recommendations"] = result.recommendations

        report_data["detailed_results"].append(result_data)

    # Add insights and next steps
    report_data["insights"] = generate_insights(evaluation)
    report_data["next_steps"] = generate_next_steps(evaluation)

    # Write report
    report_path = output_dir / f"assessment_report_{evaluation.candidate_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(report_path, 'w') as f:
        json.dump(report_data, f, indent=2)

    return report_path

def generate_insights(evaluation) -> list:
    """Generate insights based on evaluation results"""
    insights = []

    # Overall performance insights
    if evaluation.overall_score >= 90:
        insights.append("Exceptional candidate performance across all areas")
    elif evaluation.overall_score >= 80:
        insights.append("Strong candidate with solid technical foundation")
    elif evaluation.overall_score >= 70:
        insights.append("Good candidate with some areas for development")
    else:
        insights.append("Candidate needs significant development in multiple areas")

    # Specific area insights
    for result in evaluation.evaluation_results:
        score_percent = (result.score / result.max_score) * 100
        if score_percent >= 90:
            insights.append(f"Excellent performance in {result.evaluation_type.value}")
        elif score_percent <= 50:
            insights.append(f"Significant improvement needed in {result.evaluation_type.value}")

    return insights

def generate_next_steps(evaluation) -> list:
    """Generate next steps based on evaluation results"""
    next_steps = []

    if evaluation.recommendation in ["STRONG_HIRE", "HIRE"]:
        next_steps.append("Proceed with final interview round")
        next_steps.append("Conduct reference checks")
        next_steps.append("Prepare offer package")
    elif evaluation.recommendation == "CONSIDER":
        next_steps.append("Schedule follow-up technical discussion")
        next_steps.append("Consider additional assessment in weak areas")
        next_steps.append("Evaluate against other candidates")
    else:
        next_steps.append("Provide constructive feedback")
        next_steps.append("Consider for junior or mid-level roles")
        next_steps.append("Suggest skill development resources")

    # Area-specific next steps
    for result in evaluation.evaluation_results:
        score_percent = (result.score / result.max_score) * 100
        if score_percent < 70:
            if result.evaluation_type.value == "code_quality":
                next_steps.append("Review clean code principles and best practices")
            elif result.evaluation_type.value == "security":
                next_steps.append("Study security fundamentals and threat modeling")
            elif result.evaluation_type.value == "performance":
                next_steps.append("Learn performance optimization techniques")
            elif result.evaluation_type.value == "architecture":
                next_steps.append("Study system design patterns and scalability")

    return list(set(next_steps))  # Remove duplicates

def print_summary(evaluation):
    """Print evaluation summary to console"""
    print(f"\n{'='*80}")
    print(f"HIRING ASSESSMENT RESULTS")
    print(f"{'='*80}")

    print(f"\n👤 Candidate: {evaluation.candidate_name}")
    print(f"🎯 Challenge: {evaluation.challenge_name}")
    print(f"📅 Submitted: {evaluation.submission_time.strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\n📊 OVERALL SCORE: {evaluation.overall_score:.1f}/100")
    print(f"🎯 RECOMMENDATION: {evaluation.recommendation}")
    print(f"📝 SUMMARY: {evaluation.summary}")

    print(f"\n📋 DETAILED RESULTS:")
    for result in evaluation.evaluation_results:
        score_percent = (result.score / result.max_score) * 100
        status = "✅ PASS" if score_percent >= 70 else "❌ NEEDS IMPROVEMENT"

        print(f"\n  {result.evaluation_type.value.title()}:")
        print(f"    Score: {result.score:.1f}/{result.max_score} ({score_percent:.1f}%) {status}")
        print(f"    Issues: {len(result.issues)}")
        print(f"    Recommendations: {len(result.recommendations)}")

        if result.issues:
            print(f"    Top Issues:")
            for issue in result.issues[:3]:  # Show top 3
                print(f"      • {issue}")

    print(f"\n💡 INSIGHTS:")
    insights = generate_insights(evaluation)
    for insight in insights:
        print(f"  • {insight}")

    print(f"\n🚀 NEXT STEPS:")
    next_steps = generate_next_steps(evaluation)
    for step in next_steps:
        print(f"  • {step}")

def main():
    """Main assessment runner"""
    parser = argparse.ArgumentParser(
        description="Run hiring assessment with automated evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_assessment.py John Doe code-review ./solutions/john_doe/
  python run_assessment.py Jane Smith security ./solutions/jane_smith/ --output ./results/
  python run_assessment.py Bob Johnson performance ./solutions/bob/ --verbose
        """
    )

    parser.add_argument("candidate_name", help="Name of the candidate")
    parser.add_argument("challenge_name", help="Name of the challenge (code-review, security, performance, etc.)")
    parser.add_argument("solution_path", help="Path to candidate's solution directory")
    parser.add_argument("--output", "-o", help="Output directory for results", default="./assessment_results/")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--verbose", "-v", help="Enable verbose logging", action="store_true")
    parser.add_argument("--no-automated", help="Skip automated evaluation", action="store_true")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    print(f"🚀 Starting Hiring Assessment")
    print(f"   Candidate: {args.candidate_name}")
    print(f"   Challenge: {args.challenge_name}")
    print(f"   Solution: {args.solution_path}")

    # Validate inputs
    if not validate_inputs(args.candidate_name, args.challenge_name, args.solution_path):
        return 1

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Initialize evaluator
        evaluator = AutomatedEvaluator(Path(args.config) if args.config else None)

        # Run automated evaluation
        if not args.no_automated:
            print(f"\n🔍 Running Automated Evaluation...")
            evaluation = evaluator.evaluate_candidate(
                args.candidate_name,
                args.challenge_name,
                Path(args.solution_path)
            )

            # Export detailed results
            results_path = output_dir / f"automated_results_{args.candidate_name.replace(' ', '_')}.json"
            evaluator.export_results(evaluation, results_path)
            print(f"   Automated results saved to: {results_path}")
        else:
            # Create minimal evaluation without automated scoring
            from evaluation.automation.automated_evaluator import CandidateEvaluation, EvaluationResult, EvaluationType
            from datetime import datetime

            evaluation = CandidateEvaluation(
                candidate_name=args.candidate_name,
                challenge_name=args.challenge_name,
                submission_time=datetime.now(),
                overall_score=0.0,
                summary="Manual evaluation required - automated evaluation skipped"
            )

        # Generate comprehensive report
        print(f"\n📄 Generating Assessment Report...")
        report_path = generate_assessment_report(evaluation, output_dir)
        print(f"   Assessment report saved to: {report_path}")

        # Print summary to console
        print_summary(evaluation)

        print(f"\n✅ Assessment completed successfully!")
        print(f"   Results directory: {output_dir}")

        return 0

    except Exception as e:
        logger.error(f"Assessment failed: {e}")
        print(f"\n❌ Assessment failed: {e}")

        # Create error report
        error_report = {
            "candidate_name": args.candidate_name,
            "challenge_name": args.challenge_name,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

        error_path = output_dir / f"error_report_{args.candidate_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(error_path, 'w') as f:
            json.dump(error_report, f, indent=2)

        print(f"   Error report saved to: {error_path}")

        return 1

if __name__ == "__main__":
    sys.exit(main())