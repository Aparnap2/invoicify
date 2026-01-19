"""
LLM Evaluation Service

Evaluation metrics for invoice extraction quality:
- Hallucination detection
- Faithfulness to source
- Answer correctness
- Contextual relevance

Uses local LLM (Ollama) for evaluation when available.

Usage:
    from app.services.evals import EvaluationPipeline, HallucinationMetric

    metric = HallucinationMetric(threshold=0.7)
    score = metric.measure(actual_output, context)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
from pydantic import BaseModel, Field
import json


class MetricType(Enum):
    """Types of evaluation metrics."""
    HALLUCINATION = "hallucination"
    FAITHFULNESS = "faithfulness"
    ANSWER_CORRECTNESS = "answer_correctness"
    CONTEXTUAL_RELEVANCE = "contextual_relevance"
    EXTRACTION_ACCURACY = "extraction_accuracy"


@dataclass
class MetricResult:
    """Result of a metric evaluation."""
    metric_type: MetricType
    score: float  # 0.0 to 1.0
    threshold: float
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_type": self.metric_type.value,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "details": self.details,
            "error": self.error,
        }


@dataclass
class EvaluationResult:
    """Result of a full evaluation."""
    overall_score: float
    passed: bool
    metric_results: List[MetricResult]
    overall_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "passed": self.passed,
            "metric_results": [r.to_dict() for r in self.metric_results],
            "overall_details": self.overall_details,
        }


class BaseMetric:
    """Base class for evaluation metrics."""

    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self.metric_type = MetricType.HALLUCINATION

    def measure(self, actual_output: str, context: str) -> MetricResult:
        """Measure the metric. Override in subclasses."""
        raise NotImplementedError


class HallucinationMetric(BaseMetric):
    """
    Detects hallucinations in LLM outputs.

    Checks if the extracted data is consistent with the source context.
    """

    def __init__(self, threshold: float = 0.7, llm_client=None):
        super().__init__(threshold)
        self.metric_type = MetricType.HALLUCINATION
        self.llm_client = llm_client

    def measure(self, actual_output: str, context: str) -> MetricResult:
        """Measure hallucination score."""
        try:
            # Parse outputs if they're JSON
            actual_data = self._parse_output(actual_output)
            context_data = self._parse_output(context)

            # Calculate overlap
            overlap_score = self._calculate_overlap(actual_data, context_data)

            # Also check for contradictory information
            contradiction_score = self._check_contradictions(actual_data, context_data)

            # Combined score (weighted average)
            score = (overlap_score * 0.7) + (contradiction_score * 0.3)

            return MetricResult(
                metric_type=self.metric_type,
                score=score,
                threshold=self.threshold,
                passed=score >= self.threshold,
                details={
                    "overlap_score": overlap_score,
                    "contradiction_score": contradiction_score,
                    "output_length": len(actual_output),
                    "context_length": len(context),
                },
            )

        except Exception as e:
            return MetricResult(
                metric_type=self.metric_type,
                score=0.0,
                threshold=self.threshold,
                passed=False,
                error=str(e),
            )

    def _parse_output(self, text: str) -> Dict[str, Any]:
        """Parse JSON output or return raw text as dict."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def _calculate_overlap(self, actual: Dict, context: Dict) -> float:
        """Calculate how much of actual output is supported by context."""
        if not actual:
            return 0.0

        # Check if numeric values are close
        score = 1.0
        matches = 0
        total = 0

        for key, value in actual.items():
            if isinstance(value, (int, float)):
                total += 1
                # Look for similar keys in context
                context_value = self._find_value(context, key)
                if context_value is not None:
                    if isinstance(context_value, (int, float)):
                        if context_value != 0:
                            diff = abs(value - context_value) / context_value
                            if diff < 0.01:  # Within 1%
                                matches += 1
                            elif diff < 0.1:  # Within 10%
                                matches += 0.5

        if total == 0:
            # Fall back to string similarity
            actual_str = str(actual).lower()
            context_str = str(context).lower()
            common = set(actual_str.split()) & set(context_str.split())
            if common:
                score = len(common) / len(set(actual_str.split()))
            else:
                score = 0.5  # Neutral
        else:
            score = matches / total if total > 0 else 0.5

        return max(0.0, min(1.0, score))

    def _find_value(self, d: Dict, key: str) -> Any:
        """Find a value by key, searching nested dicts."""
        key_lower = key.lower()
        for k, v in d.items():
            if k.lower() == key_lower:
                return v
            if isinstance(v, dict):
                result = self._find_value(v, key)
                if result is not None:
                    return result
        return None

    def _check_contradictions(self, actual: Dict, context: Dict) -> float:
        """Check for direct contradictions."""
        contradictions = 0
        comparisons = 0

        for key, value in actual.items():
            if isinstance(value, (int, float)):
                context_value = self._find_value(context, key)
                if context_value is not None and isinstance(context_value, (int, float)):
                    comparisons += 1
                    if context_value != 0:
                        diff = abs(value - context_value) / context_value
                        if diff > 1.0:  # More than 100% different
                            contradictions += 1

        return 1.0 - (contradictions / comparisons) if comparisons > 0 else 1.0


class FaithfulnessMetric(BaseMetric):
    """
    Measures faithfulness of extraction to source document.

    Ensures all claims in extraction are supported by source.
    """

    def __init__(self, threshold: float = 0.8, llm_client=None):
        super().__init__(threshold)
        self.metric_type = MetricType.FAITHFULNESS
        self.llm_client = llm_client

    def measure(self, actual_output: str, context: str) -> MetricResult:
        """Measure faithfulness score."""
        try:
            actual_data = self._parse_output(actual_output)
            context_data = self._parse_output(context)

            # Check if all extracted fields exist in context
            field_score = self._check_fields(actual_data, context_data)

            # Check if values are consistent
            value_score = self._check_values(actual_data, context_data)

            score = (field_score * 0.4) + (value_score * 0.6)

            return MetricResult(
                metric_type=self.metric_type,
                score=score,
                threshold=self.threshold,
                passed=score >= self.threshold,
                details={
                    "field_score": field_score,
                    "value_score": value_score,
                    "fields_extracted": len(actual_data),
                    "fields_in_context": len(context_data),
                },
            )

        except Exception as e:
            return MetricResult(
                metric_type=self.metric_type,
                score=0.0,
                threshold=self.threshold,
                passed=False,
                error=str(e),
            )

    def _parse_output(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def _check_fields(self, actual: Dict, context: Dict) -> float:
        """Check if extracted fields exist in context."""
        if not actual:
            return 0.0

        context_str = str(context).lower()
        matches = 0

        for key in actual.keys():
            if key.lower() in context_str or self._value_exists(context, key):
                matches += 1

        return matches / len(actual)

    def _value_exists(self, d: Dict, key: str) -> bool:
        """Check if a key exists in nested dict."""
        key_lower = key.lower()
        for k in d.keys():
            if k.lower() == key_lower:
                return True
            if isinstance(d[k], dict):
                if self._value_exists(d[k], key):
                    return True
        return False

    def _check_values(self, actual: Dict, context: Dict) -> float:
        """Check if extracted values are in context."""
        if not actual:
            return 0.0

        context_str = str(context)
        matches = 0

        for value in actual.values():
            if isinstance(value, (int, float)):
                str_val = str(value)
                if str_val in context_str:
                    matches += 1
            elif isinstance(value, str):
                if value.lower() in context_str.lower():
                    matches += 1

        return matches / len(actual) if actual else 0.0


class AnswerCorrectnessMetric(BaseMetric):
    """
    Measures correctness of answers against expected output.
    """

    def __init__(self, threshold: float = 0.9, llm_client=None):
        super().__init__(threshold)
        self.metric_type = MetricType.ANSWER_CORRECTNESS
        self.llm_client = llm_client

    def measure(self, actual_output: str, expected_output: str) -> MetricResult:
        """Measure correctness against expected output."""
        try:
            actual = self._parse_output(actual_output)
            expected = self._parse_output(expected_output)

            # Exact match for keys
            actual_keys = set(str(k).lower() for k in actual.keys())
            expected_keys = set(str(k).lower() for k in expected.keys())

            key_match = len(actual_keys & expected_keys) / len(expected_keys) if expected_keys else 1.0

            # Value matching for numeric fields
            value_matches = 0
            value_comparisons = 0

            for key in expected_keys:
                expected_val = self._get_value(expected, key)
                actual_val = self._get_value(actual, key)

                if expected_val is not None and actual_val is not None:
                    value_comparisons += 1
                    if isinstance(expected_val, (int, float)) and isinstance(actual_val, (int, float)):
                        if expected_val != 0:
                            diff = abs(actual_val - expected_val) / expected_val
                            if diff < 0.01:
                                value_matches += 1
                            elif diff < 0.05:
                                value_matches += 0.5
                        elif actual_val == 0:
                            value_matches += 1
                    elif str(expected_val).lower() == str(actual_val).lower():
                        value_matches += 1

            value_score = value_matches / value_comparisons if value_comparisons > 0 else 1.0

            # Combined score
            score = (key_match * 0.3) + (value_score * 0.7)

            return MetricResult(
                metric_type=self.metric_type,
                score=score,
                threshold=self.threshold,
                passed=score >= self.threshold,
                details={
                    "key_match": key_match,
                    "value_score": value_score,
                    "value_comparisons": value_comparisons,
                },
            )

        except Exception as e:
            return MetricResult(
                metric_type=self.metric_type,
                score=0.0,
                threshold=self.threshold,
                passed=False,
                error=str(e),
            )

    def _parse_output(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def _get_value(self, d: Dict, key: str) -> Any:
        key_lower = key.lower()
        for k, v in d.items():
            if k.lower() == key_lower:
                return v
        return None


class ContextualRelevanceMetric(BaseMetric):
    """
    Measures relevance of extraction to the query.
    """

    def __init__(self, threshold: float = 0.7, llm_client=None):
        super().__init__(threshold)
        self.metric_type = MetricType.CONTEXTUAL_RELEVANCE
        self.llm_client = llm_client

    def measure(self, actual_output: str, query: str, context: str) -> MetricResult:
        """Measure contextual relevance."""
        try:
            # Check if output contains information relevant to query
            query_keywords = set(query.lower().split())

            # Extract words from output
            output_words = set(str(actual_output).lower().split())

            # Check keyword overlap
            relevant_words = query_keywords & output_words
            keyword_score = len(relevant_words) / len(query_keywords) if query_keywords else 1.0

            # Check if output contains contextually relevant info
            context_score = self._check_context_relevance(actual_output, context)

            score = (keyword_score * 0.4) + (context_score * 0.6)

            return MetricResult(
                metric_type=self.metric_type,
                score=score,
                threshold=self.threshold,
                passed=score >= self.threshold,
                details={
                    "keyword_score": keyword_score,
                    "context_score": context_score,
                    "relevant_keywords": list(relevant_words),
                },
            )

        except Exception as e:
            return MetricResult(
                metric_type=self.metric_type,
                score=0.0,
                threshold=self.threshold,
                passed=False,
                error=str(e),
            )

    def _check_context_relevance(self, output: str, context: str) -> float:
        """Check if output is relevant to context."""
        output_lower = output.lower()
        context_lower = context.lower()

        # Extract numbers (amounts, dates, etc.)
        import re
        output_numbers = set(re.findall(r'\d+[\d,\.]*', output_lower))
        context_numbers = set(re.findall(r'\d+[\d,\.]*', context_lower))

        number_overlap = len(output_numbers & context_numbers) / len(context_numbers) if context_numbers else 1.0

        return number_overlap


class EvaluationPipeline:
    """
    Full evaluation pipeline for invoice extraction.
    """

    def __init__(self, thresholds: Optional[Dict[MetricType, float]] = None):
        self.thresholds = thresholds or {
            MetricType.HALLUCINATION: 0.7,
            MetricType.FAITHFULNESS: 0.8,
            MetricType.ANSWER_CORRECTNESS: 0.9,
            MetricType.CONTEXTUAL_RELEVANCE: 0.7,
        }

        self.metrics = {
            MetricType.HALLUCINATION: HallucinationMetric(self.thresholds[MetricType.HALLUCINATION]),
            MetricType.FAITHFULNESS: FaithfulnessMetric(self.thresholds[MetricType.FAITHFULNESS]),
            MetricType.ANSWER_CORRECTNESS: AnswerCorrectnessMetric(self.thresholds[MetricType.ANSWER_CORRECTNESS]),
            MetricType.CONTEXTUAL_RELEVANCE: ContextualRelevanceMetric(self.thresholds[MetricType.CONTEXTUAL_RELEVANCE]),
        }

    def evaluate_extraction(
        self,
        actual_output: str,
        expected_output: Optional[str] = None,
        context: Optional[str] = None,
        query: Optional[str] = None,
    ) -> EvaluationResult:
        """
        Run full evaluation of extraction.

        Args:
            actual_output: The extracted data (JSON string or text)
            expected_output: Ground truth expected output (optional)
            context: Source document text (optional)
            query: The query that was asked (optional)

        Returns:
            EvaluationResult with all metrics
        """
        results: List[MetricResult] = []

        # Hallucination check (requires context)
        if context:
            result = self.metrics[MetricType.HALLUCINATION].measure(actual_output, context)
            results.append(result)

        # Faithfulness check (requires context)
        if context:
            result = self.metrics[MetricType.FAITHFULNESS].measure(actual_output, context)
            results.append(result)

        # Correctness check (requires expected output)
        if expected_output:
            result = self.metrics[MetricType.ANSWER_CORRECTNESS].measure(actual_output, expected_output)
            results.append(result)

        # Contextual relevance check (requires context and query)
        if context and query:
            result = self.metrics[MetricType.CONTEXTUAL_RELEVANCE].measure(actual_output, query, context)
            results.append(result)

        # Calculate overall score
        if results:
            overall_score = sum(r.score for r in results) / len(results)
            passed = all(r.passed for r in results)
        else:
            overall_score = 0.0
            passed = False

        return EvaluationResult(
            overall_score=overall_score,
            passed=passed,
            metric_results=results,
            overall_details={
                "total_metrics": len(results),
                "passed_metrics": sum(1 for r in results if r.passed),
                "thresholds": {k.value: v for k, v in self.thresholds.items()},
            },
        )


class ExtractionTestCase(BaseModel):
    """Test case for extraction evaluation."""
    name: str
    input: str
    actual_output: str
    expected_output: Optional[Dict[str, Any]] = None
    context: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def evaluate_test_case(
    test_case: ExtractionTestCase,
    thresholds: Optional[Dict[MetricType, float]] = None,
) -> EvaluationResult:
    """
    Evaluate a single test case.

    Args:
        test_case: The test case to evaluate
        thresholds: Custom thresholds for metrics

    Returns:
        EvaluationResult
    """
    pipeline = EvaluationPipeline(thresholds)

    return pipeline.evaluate_extraction(
        actual_output=test_case.actual_output,
        expected_output=json.dumps(test_case.expected_output) if test_case.expected_output else None,
        context=test_case.context,
        query=test_case.input,
    )
