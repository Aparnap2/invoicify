#!/usr/bin/env python3
"""
Automated Hiring Assessment Evaluator

This tool provides automated evaluation of candidate solutions for the hiring
assessment challenges, including code quality analysis, security scanning,
and performance testing.
"""

import ast
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import subprocess
import tempfile
import requests
import bandit
from radon.complexity import cc_visit
from radon.metrics import mi_visit, h_visit
import pylint.lint
from pylint.reporters import JSONReporter

logger = logging.getLogger(__name__)

class EvaluationType(Enum):
    CODE_QUALITY = "code_quality"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"

@dataclass
class EvaluationResult:
    """Single evaluation result"""
    evaluation_type: EvaluationType
    score: float
    max_score: float
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

@dataclass
class CandidateEvaluation:
    """Complete candidate evaluation"""
    candidate_name: str
    challenge_name: str
    submission_time: datetime
    overall_score: float
    evaluation_results: List[EvaluationResult] = field(default_factory=list)
    summary: str = ""
    recommendation: str = ""

    def add_result(self, result: EvaluationResult):
        """Add an evaluation result"""
        self.evaluation_results.append(result)

    def calculate_overall_score(self) -> float:
        """Calculate overall score from all evaluations"""
        if not self.evaluation_results:
            return 0.0

        # Weight different evaluation types
        weights = {
            EvaluationType.CODE_QUALITY: 0.35,
            EvaluationType.SECURITY: 0.25,
            EvaluationType.PERFORMANCE: 0.20,
            EvaluationType.ARCHITECTURE: 0.15,
            EvaluationType.DOCUMENTATION: 0.05
        }

        total_score = 0.0
        total_weight = 0.0

        for result in self.evaluation_results:
            weight = weights.get(result.evaluation_type, 0.1)
            normalized_score = (result.score / result.max_score) * 100
            total_score += normalized_score * weight
            total_weight += weight

        return total_score / total_weight if total_weight > 0 else 0.0

class CodeQualityEvaluator:
    """Evaluates code quality metrics"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate(self, solution_path: Path) -> EvaluationResult:
        """Evaluate code quality of a Python solution"""
        start_time = time.time()

        details = {}
        issues = []
        recommendations = []
        score = 0.0

        try:
            # Read all Python files
            python_files = list(solution_path.rglob("*.py"))
            if not python_files:
                return EvaluationResult(
                    EvaluationType.CODE_QUALITY,
                    0, 20,
                    {"error": "No Python files found"},
                    ["No code to evaluate"],
                    ["Please submit Python code"]
                )

            # Initialize metrics
            total_complexity = 0
            total_maintainability = 0
            total_halstead = 0
            pylint_score = 0
            security_issues = 0

            for py_file in python_files:
                try:
                    # Read file content
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Parse AST
                    try:
                        tree = ast.parse(content)
                    except SyntaxError as e:
                        issues.append(f"Syntax error in {py_file}: {e}")
                        continue

                    # Radon complexity analysis
                    complexity = cc_visit(content)
                    total_complexity += sum(complex.complexity for complex in complexity)

                    # Radon maintainability index
                    maintainability = mi_visit(content, multi=True)
                    total_maintainability += sum(m.mi for m in maintainability)

                    # Halstead metrics
                    halstead = h_visit(content)
                    total_halstead += sum(h.difficulty for h in halstead)

                    # Pylint analysis
                    try:
                        reporter = JSONReporter()
                        pylint.lint.Run([str(py_file)], reporter=reporter, exit=False)
                        pylint_messages = reporter.messages

                        # Count issues by type
                        error_count = len([m for m in pylint_messages if m.msg_id.startswith('E')])
                        warning_count = len([m for m in pylint_messages if m.msg_id.startswith('W')])
                        refactor_count = len([m for m in pylint_messages if m.msg_id.startswith('R')])

                        # Calculate Pylint score (simplified)
                        pylint_score += max(0, 10 - (error_count * 2 + warning_count + refactor_count * 0.5))

                        # Collect specific issues
                        for msg in pylint_messages[:10]:  # Limit to top 10 issues
                            if msg.msg_id.startswith('E'):
                                issues.append(f"{py_file}:{msg.line}: {msg.msg_id}: {msg.msg}")

                    except Exception as e:
                        self.logger.warning(f"Pylint failed for {py_file}: {e}")

                except Exception as e:
                    self.logger.error(f"Error processing {py_file}: {e}")
                    continue

            # Calculate quality metrics
            file_count = len(python_files)
            avg_complexity = total_complexity / file_count if file_count > 0 else 0
            avg_maintainability = total_maintainability / file_count if file_count > 0 else 0
            avg_pylint_score = pylint_score / file_count if file_count > 0 else 0

            details.update({
                "file_count": file_count,
                "avg_complexity": round(avg_complexity, 2),
                "avg_maintainability": round(avg_maintainability, 2),
                "pylint_score": round(avg_pylint_score, 2),
                "total_issues": len(issues)
            })

            # Calculate score based on quality metrics
            # Maintainability Index: higher is better (0-100)
            maintainability_score = min(20, avg_maintainability / 5)

            # Pylint Score: higher is better (0-10)
            pylint_score_norm = min(20, avg_pylint_score * 2)

            # Complexity: lower is better
            complexity_score = max(0, 20 - avg_complexity)

            # Issue penalty
            issue_penalty = min(10, len(issues) * 0.5)

            score = maintainability_score + pylint_score_norm + complexity_score - issue_penalty
            score = max(0, min(20, score))  # Clamp to 0-20 range

            # Generate recommendations
            if avg_complexity > 10:
                recommendations.append("Consider reducing cyclomatic complexity by extracting methods")
            if avg_maintainability < 50:
                recommendations.append("Improve code maintainability with better structure and documentation")
            if len(issues) > 20:
                recommendations.append("Address code quality issues identified by static analysis")
            if not issues:
                recommendations.append("Excellent code quality! Consider adding more comprehensive tests")

        except Exception as e:
            self.logger.error(f"Code quality evaluation failed: {e}")
            details["error"] = str(e)
            score = 0

        evaluation_time = time.time() - start_time
        details["evaluation_time"] = round(evaluation_time, 2)

        return EvaluationResult(
            EvaluationType.CODE_QUALITY,
            score, 20,
            details,
            issues,
            recommendations
        )

class SecurityEvaluator:
    """Evaluates security aspects of code"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate(self, solution_path: Path) -> EvaluationResult:
        """Evaluate security of a Python solution"""
        start_time = time.time()

        details = {}
        issues = []
        recommendations = []
        score = 10.0  # Start with perfect score

        try:
            python_files = list(solution_path.rglob("*.py"))
            if not python_files:
                return EvaluationResult(
                    EvaluationType.SECURITY,
                    0, 10,
                    {"error": "No Python files found"},
                    ["No code to evaluate"],
                    ["Please submit Python code"]
                )

            # Run Bandit security analysis
            security_issues = []
            high_severity = 0
            medium_severity = 0
            low_severity = 0

            for py_file in python_files:
                try:
                    # Run bandit on each file
                    result = bandit.core.manager.Manager(
                        bandit.config.BanditConfig(),
                        bandit.core.manager._get_plugin_manager()
                    )

                    result.discover_files([str(py_file)], True)
                    result.run_tests()

                    # Collect issues
                    for issue in result.get_issue_list():
                        if issue.test_id.startswith('B'):  # Security issues
                            severity = issue.severity.lower()
                            if severity == 'high':
                                high_severity += 1
                                score -= 2
                            elif severity == 'medium':
                                medium_severity += 1
                                score -= 1
                            elif severity == 'low':
                                low_severity += 1
                                score -= 0.5

                            security_issues.append({
                                "file": issue.fname,
                                "line": issue.lineno,
                                "severity": severity,
                                "issue": issue.text,
                                "test_id": issue.test_id
                            })

                except Exception as e:
                    self.logger.warning(f"Bandit analysis failed for {py_file}: {e}")

            # Additional security pattern checks
            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Check for security anti-patterns
                    security_patterns = [
                        (r'eval\s*\(', "Use of eval() function - potential code injection"),
                        (r'exec\s*\(', "Use of exec() function - potential code injection"),
                        (r'pickle\.loads?\s*\(', "Use of pickle - potential code execution"),
                        (r'shell=True', "shell=True in subprocess - potential command injection"),
                        (r'input\s*\(', "Use of input() - potential injection in some contexts"),
                        (r'password.*=.*["\'].*["\']', "Hardcoded password detected"),
                        (r'api_key.*=.*["\'].*["\']', "Hardcoded API key detected"),
                        (r'secret.*=.*["\'].*["\']', "Hardcoded secret detected"),
                        (r'token.*=.*["\'].*["\']', "Hardcoded token detected"),
                        (r'hashlib\.md5\s*\(', "Use of MD5 hash - consider stronger alternatives")
                    ]

                    for pattern, message in security_patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            line_num = content[:match.start()].count('\n') + 1
                            security_issues.append({
                                "file": str(py_file),
                                "line": line_num,
                                "severity": "medium",
                                "issue": message,
                                "test_id": "CUSTOM_PATTERN"
                            })
                            medium_severity += 1
                            score -= 1

                except Exception as e:
                    self.logger.error(f"Error reading {py_file}: {e}")

            # Check for security best practices
            security_good_practices = 0

            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Look for security-conscious patterns
                    if re.search(r'try\s*:.*except\s+Exception', content, re.DOTALL):
                        security_good_practices += 1  # Exception handling

                    if re.search(r'logging\.getLogger', content):
                        security_good_practices += 1  # Logging

                    if re.search(r'sanitize|validate|clean', content, re.IGNORECASE):
                        security_good_practices += 1  # Input validation

                    if re.search(r'hashlib|bcrypt|scrypt', content):
                        security_good_practices += 1  # Cryptographic functions

                    if re.search(r'jwt|oauth|auth', content, re.IGNORECASE):
                        security_good_practices += 1  # Authentication

                except Exception as e:
                    self.logger.error(f"Error analyzing security practices in {py_file}: {e}")

            # Add bonus for security practices
            score += min(3, security_good_practices * 0.5)

            # Format issues for display
            for issue in security_issues[:20]:  # Limit to top 20
                issues.append(
                    f"{Path(issue['file']).name}:{issue['line']} "
                    f"[{issue['severity'].upper()}] {issue['issue']}"
                )

            details.update({
                "high_severity_issues": high_severity,
                "medium_severity_issues": medium_severity,
                "low_severity_issues": low_severity,
                "total_security_issues": len(security_issues),
                "security_good_practices": security_good_practices
            })

            # Generate recommendations
            if high_severity > 0:
                recommendations.append("Address high-severity security issues immediately")
            if medium_severity > 5:
                recommendations.append("Review and fix medium-severity security issues")
            if security_good_practices < 3:
                recommendations.append("Implement more security best practices (validation, logging, etc.)")
            if not security_issues and security_good_practices > 5:
                recommendations.append("Excellent security practices! Consider security testing")

        except Exception as e:
            self.logger.error(f"Security evaluation failed: {e}")
            details["error"] = str(e)
            score = 0

        # Clamp score
        score = max(0, min(10, score))

        evaluation_time = time.time() - start_time
        details["evaluation_time"] = round(evaluation_time, 2)

        return EvaluationResult(
            EvaluationType.SECURITY,
            score, 10,
            details,
            issues,
            recommendations
        )

class PerformanceEvaluator:
    """Evaluates performance aspects of code"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate(self, solution_path: Path) -> EvaluationResult:
        """Evaluate performance of a Python solution"""
        start_time = time.time()

        details = {}
        issues = []
        recommendations = []
        score = 10.0

        try:
            python_files = list(solution_path.rglob("*.py"))
            if not python_files:
                return EvaluationResult(
                    EvaluationType.PERFORMANCE,
                    0, 10,
                    {"error": "No Python files found"},
                    ["No code to evaluate"],
                    ["Please submit Python code"]
                )

            performance_issues = []
            good_practices = 0

            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    lines = content.split('\n')

                    # Performance anti-patterns
                    performance_patterns = [
                        (r'for.*in.*range\(len\(', "Use enumerate() instead of range(len())"),
                        (r'\.keys\(\).*in.*\.keys\(\)', "Use set operations for membership testing"),
                        (r'sum\(\[.*for.*in.*\]\)', "Use generator expressions instead of list comprehensions in sum()"),
                        (r'while.*True.*break', "Consider using for loop instead of while True"),
                        (r'\+\=\s*\[.*\]', "Use extend() instead of += for lists"),
                        (r'if.*in.*\.keys\(\):', "Use dict key lookup directly"),
                        (r'if.*len\(.*\)\s*>\s*0', "Use truthiness instead of len() > 0"),
                        (r'try\s*:.*except\s*:', "Catch specific exceptions instead of bare except"),
                        (r'import.*\*', "Avoid wildcard imports"),
                        (r'global\s+\w+', "Minimize use of global variables")
                    ]

                    for pattern, message in performance_patterns:
                        matches = re.finditer(pattern, content)
                        for match in matches:
                            line_num = content[:match.start()].count('\n') + 1
                            performance_issues.append({
                                "file": str(py_file),
                                "line": line_num,
                                "issue": message,
                                "pattern": pattern
                            })
                            score -= 0.5

                    # Look for performance best practices
                    if re.search(r'async\s+def|await\s+', content):
                        good_practices += 1  # Async programming

                    if re.search(r'@cache|@lru_cache', content):
                        good_practices += 1  # Caching

                    if re.search(r'with\s+open\(', content):
                        good_practices += 1  # Context managers

                    if re.search(r'yield\s+|from\s+\w+\s+import\s+.*yield', content):
                        good_practices += 1  # Generators

                    if re.search(r'multiprocessing|threading|asyncio', content):
                        good_practices += 1  # Concurrency

                except Exception as e:
                    self.logger.error(f"Error analyzing performance in {py_file}: {e}")

            # Check for algorithmic complexity issues
            complexity_issues = []
            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Nested loops check
                    nested_loops = len(re.findall(r'for.*:.*for.*:', content, re.DOTALL))
                    if nested_loops > 2:
                        complexity_issues.append(f"Potentially O(n²) complexity in {py_file}")
                        score -= 1

                    # Recursive functions
                    recursive_functions = len(re.findall(r'def\s+\w+.*:\s*.*return\s+\w+\(', content, re.DOTALL))
                    if recursive_functions > 0 and not re.search(r'@\w*cache', content):
                        complexity_issues.append(f"Recursive function without memoization in {py_file}")
                        score -= 0.5

                except Exception as e:
                    self.logger.error(f"Error checking complexity in {py_file}: {e}")

            # Format issues
            for issue in performance_issues[:15]:  # Limit to top 15
                issues.append(
                    f"{Path(issue['file']).name}:{issue['line']} {issue['issue']}"
                )

            for issue in complexity_issues[:5]:  # Limit to top 5
                issues.append(issue)

            details.update({
                "performance_issues": len(performance_issues),
                "complexity_issues": len(complexity_issues),
                "good_practices": good_practices,
                "nested_loops": nested_loops if 'nested_loops' in locals() else 0,
                "recursive_functions": recursive_functions if 'recursive_functions' in locals() else 0
            })

            # Add bonus for good practices
            score += min(3, good_practices * 0.3)

            # Generate recommendations
            if len(performance_issues) > 10:
                recommendations.append("Address performance anti-patterns for better efficiency")
            if nested_loops > 3:
                recommendations.append("Consider optimizing nested loops or using better algorithms")
            if good_practices < 3:
                recommendations.append("Implement more performance best practices (caching, async, etc.)")
            if not performance_issues and good_practices > 3:
                recommendations.append("Excellent performance practices! Consider load testing")

        except Exception as e:
            self.logger.error(f"Performance evaluation failed: {e}")
            details["error"] = str(e)
            score = 0

        # Clamp score
        score = max(0, min(10, score))

        evaluation_time = time.time() - start_time
        details["evaluation_time"] = round(evaluation_time, 2)

        return EvaluationResult(
            EvaluationType.PERFORMANCE,
            score, 10,
            details,
            issues,
            recommendations
        )

class AutomatedEvaluator:
    """Main automated evaluator that coordinates all evaluations"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self._load_config(config_path) if config_path else {}
        self.logger = logging.getLogger(__name__)

        # Initialize evaluators
        self.code_evaluator = CodeQualityEvaluator()
        self.security_evaluator = SecurityEvaluator()
        self.performance_evaluator = PerformanceEvaluator()

    def _load_config(self, config_path: Path) -> Dict:
        """Load evaluation configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load config from {config_path}: {e}")
            return {}

    def evaluate_candidate(
        self,
        candidate_name: str,
        challenge_name: str,
        solution_path: Path
    ) -> CandidateEvaluation:
        """Evaluate a complete candidate solution"""
        self.logger.info(f"Evaluating {candidate_name} for {challenge_name}")

        evaluation = CandidateEvaluation(
            candidate_name=candidate_name,
            challenge_name=challenge_name,
            submission_time=datetime.now(),
            overall_score=0.0
        )

        # Run all evaluations
        try:
            # Code Quality Evaluation
            code_result = self.code_evaluator.evaluate(solution_path)
            evaluation.add_result(code_result)

            # Security Evaluation
            security_result = self.security_evaluator.evaluate(solution_path)
            evaluation.add_result(security_result)

            # Performance Evaluation
            performance_result = self.performance_evaluator.evaluate(solution_path)
            evaluation.add_result(performance_result)

            # Calculate overall score
            evaluation.overall_score = evaluation.calculate_overall_score()

            # Generate summary and recommendation
            evaluation.summary = self._generate_summary(evaluation)
            evaluation.recommendation = self._generate_recommendation(evaluation.overall_score)

        except Exception as e:
            self.logger.error(f"Evaluation failed for {candidate_name}: {e}")
            evaluation.summary = f"Evaluation failed: {str(e)}"
            evaluation.recommendation = "MANUAL_REVIEW_REQUIRED"

        return evaluation

    def _generate_summary(self, evaluation: CandidateEvaluation) -> str:
        """Generate evaluation summary"""
        summary_parts = []

        # Overall score
        summary_parts.append(f"Overall Score: {evaluation.overall_score:.1f}/100")

        # Individual scores
        for result in evaluation.evaluation_results:
            score_percent = (result.score / result.max_score) * 100
            summary_parts.append(f"{result.evaluation_type.value.title()}: {score_percent:.1f}%")

        # Key strengths
        strengths = []
        for result in evaluation.evaluation_results:
            if result.score >= result.max_score * 0.8:
                strengths.append(result.evaluation_type.value)

        if strengths:
            summary_parts.append(f"Strengths: {', '.join(strengths)}")

        # Key issues
        total_issues = sum(len(result.issues) for result in evaluation.evaluation_results)
        if total_issues > 0:
            summary_parts.append(f"Issues Found: {total_issues}")

        return " | ".join(summary_parts)

    def _generate_recommendation(self, score: float) -> str:
        """Generate hiring recommendation based on score"""
        if score >= 90:
            return "STRONG_HIRE"
        elif score >= 80:
            return "HIRE"
        elif score >= 70:
            return "CONSIDER"
        elif score >= 60:
            return "MAYBE"
        else:
            return "NO_HIRE"

    def export_results(self, evaluation: CandidateEvaluation, output_path: Path):
        """Export evaluation results to JSON"""
        results = {
            "candidate_name": evaluation.candidate_name,
            "challenge_name": evaluation.challenge_name,
            "submission_time": evaluation.submission_time.isoformat(),
            "overall_score": evaluation.overall_score,
            "recommendation": evaluation.recommendation,
            "summary": evaluation.summary,
            "evaluations": []
        }

        for result in evaluation.evaluation_results:
            eval_data = {
                "type": result.evaluation_type.value,
                "score": result.score,
                "max_score": result.max_score,
                "details": result.details,
                "issues": result.issues[:10],  # Limit to top 10
                "recommendations": result.recommendations
            }
            results["evaluations"].append(eval_data)

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        self.logger.info(f"Results exported to {output_path}")

def main():
    """Command line interface for the evaluator"""
    import argparse

    parser = argparse.ArgumentParser(description="Automated Hiring Assessment Evaluator")
    parser.add_argument("candidate_name", help="Name of the candidate")
    parser.add_argument("challenge_name", help="Name of the challenge")
    parser.add_argument("solution_path", help="Path to candidate solution")
    parser.add_argument("--output", help="Output path for results", default="evaluation_results.json")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--verbose", help="Verbose logging", action="store_true")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run evaluation
    evaluator = AutomatedEvaluator(Path(args.config) if args.config else None)

    solution_path = Path(args.solution_path)
    if not solution_path.exists():
        print(f"Error: Solution path {solution_path} does not exist")
        return 1

    evaluation = evaluator.evaluate_candidate(
        args.candidate_name,
        args.challenge_name,
        solution_path
    )

    # Print results
    print(f"\n{'='*60}")
    print(f"Evaluation Results for {args.candidate_name}")
    print(f"{'='*60}")
    print(f"Overall Score: {evaluation.overall_score:.1f}/100")
    print(f"Recommendation: {evaluation.recommendation}")
    print(f"Summary: {evaluation.summary}")
    print(f"\nDetailed Results:")

    for result in evaluation.evaluation_results:
        score_percent = (result.score / result.max_score) * 100
        print(f"  {result.evaluation_type.value.title()}: {score_percent:.1f}% ({result.score:.1f}/{result.max_score})")

        if result.issues:
            print(f"    Issues ({len(result.issues)}):")
            for issue in result.issues[:5]:  # Show top 5
                print(f"      - {issue}")

        if result.recommendations:
            print(f"    Recommendations:")
            for rec in result.recommendations:
                print(f"      - {rec}")

    # Export results
    evaluator.export_results(evaluation, Path(args.output))
    print(f"\nResults exported to {args.output}")

    return 0

if __name__ == "__main__":
    exit(main())