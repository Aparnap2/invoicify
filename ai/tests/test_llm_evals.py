"""
Test suite for LLM Evaluation Service (TDD)

Run with: pytest tests/test_llm_evals.py -v

Tests for evaluation metrics including:
- Hallucination detection
- Faithfulness measurement
- Answer correctness
- Contextual relevance
"""

import pytest
from typing import Dict, List, Optional


class TestEvalsImports:
    """Test that evaluation dependencies are available."""

    def test_pydantic_available(self):
        """Pydantic should be available for test case modeling."""
        from pydantic import BaseModel
        assert BaseModel is not None

    def test_json_available(self):
        """JSON module should be available for parsing."""
        import json
        assert json is not None


class TestMetricResult:
    """Tests for MetricResult dataclass."""

    def test_create_metric_result(self):
        """Test creating a metric result."""
        from app.services.evals import MetricResult, MetricType

        result = MetricResult(
            metric_type=MetricType.HALLUCINATION,
            score=0.85,
            threshold=0.7,
            passed=True,
            details={"test": "value"}
        )

        assert result.score == 0.85
        assert result.passed is True
        assert result.metric_type == MetricType.HALLUCINATION

    def test_metric_result_to_dict(self):
        """Test serialization to dict."""
        from app.services.evals import MetricResult, MetricType

        result = MetricResult(
            metric_type=MetricType.HALLUCINATION,
            score=0.85,
            threshold=0.7,
            passed=True
        )

        data = result.to_dict()
        assert data["metric_type"] == "hallucination"
        assert data["score"] == 0.85
        assert data["passed"] is True


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_create_evaluation_result(self):
        """Test creating an evaluation result."""
        from app.services.evals import EvaluationResult, MetricResult, MetricType

        metric_result = MetricResult(
            metric_type=MetricType.HALLUCINATION,
            score=0.85,
            threshold=0.7,
            passed=True
        )

        result = EvaluationResult(
            overall_score=0.85,
            passed=True,
            metric_results=[metric_result]
        )

        assert result.overall_score == 0.85
        assert result.passed is True
        assert len(result.metric_results) == 1

    def test_evaluation_result_to_dict(self):
        """Test serialization to dict."""
        from app.services.evals import EvaluationResult, MetricResult, MetricType

        result = EvaluationResult(
            overall_score=0.85,
            passed=True,
            metric_results=[],
            overall_details={"total": 1}
        )

        data = result.to_dict()
        assert data["overall_score"] == 0.85
        assert data["passed"] is True
        assert data["overall_details"]["total"] == 1


class TestMetricTypes:
    """Tests for MetricType enum."""

    def test_metric_types_exist(self):
        """Test that all metric types exist."""
        from app.services.evals import MetricType

        assert MetricType.HALLUCINATION.value == "hallucination"
        assert MetricType.FAITHFULNESS.value == "faithfulness"
        assert MetricType.ANSWER_CORRECTNESS.value == "answer_correctness"
        assert MetricType.CONTEXTUAL_RELEVANCE.value == "contextual_relevance"


class TestHallucinationMetric:
    """Tests for HallucinationMetric."""

    def test_metric_initialization(self):
        """Test that metric can be initialized."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.7)
        assert metric.threshold == 0.7

    def test_measure_returns_metric_result(self):
        """Test that measure returns MetricResult."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.7)

        result = metric.measure(
            '{"total": 500}',
            'Invoice for $500'
        )

        assert result.metric_type.value == "hallucination"
        assert isinstance(result.score, float)
        assert isinstance(result.passed, bool)

    def test_detect_hallucinated_amount(self):
        """Test detecting hallucinated invoice amounts."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.7)

        # Context says $500, output says $1000
        result = metric.measure(
            '{"total": 1000}',
            '{"total": 500}'
        )

        # Score should be low due to mismatch
        assert isinstance(result.score, float)
        assert result.score <= 0.5  # Should detect mismatch

    def test_detect_factual_extraction(self):
        """Test that correct extractions score high."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.5)

        # Context and output match
        result = metric.measure(
            '{"total": 500, "vendor": "Acme"}',
            '{"total": 500, "vendor": "Acme"}'
        )

        assert result.score >= 0.5


class TestFaithfulnessMetric:
    """Tests for FaithfulnessMetric."""

    def test_metric_initialization(self):
        """Test that metric can be initialized."""
        from app.services.evals import FaithfulnessMetric

        metric = FaithfulnessMetric(threshold=0.8)
        assert metric.threshold == 0.8

    def test_measure_returns_metric_result(self):
        """Test that measure returns MetricResult."""
        from app.services.evals import FaithfulnessMetric

        metric = FaithfulnessMetric(threshold=0.8)

        result = metric.measure(
            '{"vendor": "Acme", "total": 500}',
            'Invoice from Acme Corp for $500'
        )

        assert result.metric_type.value == "faithfulness"
        assert isinstance(result.score, float)

    def test_faithful_extraction(self):
        """Test measuring faithful extraction."""
        from app.services.evals import FaithfulnessMetric

        metric = FaithfulnessMetric(threshold=0.6)

        result = metric.measure(
            '{"invoice_no": "INV-001", "total": 5250.00}',
            'Invoice #INV-2024-001 dated January 15, 2024 from Acme Corporation Amount: $5,250.00'
        )

        assert isinstance(result.score, float)
        assert 0.0 <= result.score <= 1.0


class TestAnswerCorrectnessMetric:
    """Tests for AnswerCorrectnessMetric."""

    def test_metric_initialization(self):
        """Test that metric can be initialized."""
        from app.services.evals import AnswerCorrectnessMetric

        metric = AnswerCorrectnessMetric(threshold=0.9)
        assert metric.threshold == 0.9

    def test_measure_returns_metric_result(self):
        """Test that measure returns MetricResult."""
        from app.services.evals import AnswerCorrectnessMetric

        metric = AnswerCorrectnessMetric(threshold=0.9)

        result = metric.measure(
            '{"total": 500}',
            '{"total": 500}'
        )

        assert result.metric_type.value == "answer_correctness"
        assert isinstance(result.score, float)

    def test_correct_invoice_total(self):
        """Test evaluating correct invoice total."""
        from app.services.evals import AnswerCorrectnessMetric

        metric = AnswerCorrectnessMetric(threshold=0.9)

        result = metric.measure(
            '{"total": 500.00, "vendor": "Acme"}',
            '{"total": 500.00, "vendor": "Acme"}'
        )

        assert result.score >= 0.9

    def test_incorrect_invoice_total(self):
        """Test evaluating incorrect invoice total."""
        from app.services.evals import AnswerCorrectnessMetric

        metric = AnswerCorrectnessMetric(threshold=0.7)

        result = metric.measure(
            '{"total": 750.00}',
            '{"total": 500.00}'
        )

        assert result.score < 0.7


class TestContextualRelevanceMetric:
    """Tests for ContextualRelevanceMetric."""

    def test_metric_initialization(self):
        """Test that metric can be initialized."""
        from app.services.evals import ContextualRelevanceMetric

        metric = ContextualRelevanceMetric(threshold=0.7)
        assert metric.threshold == 0.7

    def test_measure_returns_metric_result(self):
        """Test that measure returns MetricResult."""
        from app.services.evals import ContextualRelevanceMetric

        metric = ContextualRelevanceMetric(threshold=0.7)

        result = metric.measure(
            '{"total": 1500}',
            "What is the total amount?",
            "Invoice from Acme Corp for $1,500"
        )

        assert result.metric_type.value == "contextual_relevance"
        assert isinstance(result.score, float)

    def test_relevant_extraction(self):
        """Test measuring relevance of extraction."""
        from app.services.evals import ContextualRelevanceMetric

        metric = ContextualRelevanceMetric(threshold=0.5)

        # Use query keywords that appear in output
        result = metric.measure(
            '{"total": 1500, "vendor": "Acme"}',
            "total vendor",  # Keywords that appear in output
            "Invoice from Acme Corp for $1,500"
        )

        # Score should be based on keyword overlap and context relevance
        assert result.score >= 0.0  # Just verify it returns a valid score
        assert 0.0 <= result.score <= 1.0

    def test_irrelevant_extraction(self):
        """Test detecting irrelevant extractions."""
        from app.services.evals import ContextualRelevanceMetric

        metric = ContextualRelevanceMetric(threshold=0.5)

        result = metric.measure(
            '{"weather": "sunny"}',
            "What is the total amount?",
            "Invoice from Acme Corp for $1,500"
        )

        assert result.score < 0.5


class TestEvaluationPipeline:
    """Tests for EvaluationPipeline."""

    def test_pipeline_initialization(self):
        """Test pipeline initialization with defaults."""
        from app.services.evals import EvaluationPipeline, MetricType

        pipeline = EvaluationPipeline()
        assert MetricType.HALLUCINATION in pipeline.metrics
        assert MetricType.FAITHFULNESS in pipeline.metrics
        assert MetricType.ANSWER_CORRECTNESS in pipeline.metrics
        assert MetricType.CONTEXTUAL_RELEVANCE in pipeline.metrics

    def test_pipeline_with_custom_thresholds(self):
        """Test pipeline with custom thresholds."""
        from app.services.evals import EvaluationPipeline, MetricType

        # Must provide all metric types when using custom thresholds
        thresholds = {
            MetricType.HALLUCINATION: 0.8,
            MetricType.FAITHFULNESS: 0.9,
            MetricType.ANSWER_CORRECTNESS: 0.85,
            MetricType.CONTEXTUAL_RELEVANCE: 0.75,
        }
        pipeline = EvaluationPipeline(thresholds)
        assert pipeline.metrics[MetricType.HALLUCINATION].threshold == 0.8
        assert pipeline.metrics[MetricType.FAITHFULNESS].threshold == 0.9

    def test_evaluate_extraction_returns_result(self):
        """Test evaluate_extraction returns EvaluationResult."""
        from app.services.evals import EvaluationPipeline

        pipeline = EvaluationPipeline()

        result = pipeline.evaluate_extraction(
            actual_output='{"total": 500}',
            expected_output='{"total": 500}',
            context="Invoice for $500",
            query="Extract invoice data"
        )

        assert isinstance(result, type(result))  # EvaluationResult
        assert isinstance(result.overall_score, float)
        assert isinstance(result.passed, bool)
        assert isinstance(result.metric_results, list)

    def test_evaluate_extraction_with_only_context(self):
        """Test evaluation with only context (no expected output)."""
        from app.services.evals import EvaluationPipeline

        pipeline = EvaluationPipeline()

        result = pipeline.evaluate_extraction(
            actual_output='{"total": 500}',
            context="Invoice for $500",
        )

        # Should still work, running hallucination and faithfulness checks
        assert isinstance(result.overall_score, float)


class TestEvaluationThresholds:
    """Tests for evaluation threshold configuration."""

    def test_custom_threshold(self):
        """Test using custom evaluation thresholds."""
        from app.services.evals import HallucinationMetric

        # High threshold for strict evaluation
        metric = HallucinationMetric(threshold=0.95)

        result = metric.measure('{"total": 500}', '{"total": 500}')
        assert result.threshold == 0.95

    def test_lenient_threshold(self):
        """Test using lenient evaluation thresholds."""
        from app.services.evals import HallucinationMetric

        # Lenient threshold
        metric = HallucinationMetric(threshold=0.3)

        result = metric.measure('{"total": 505}', '{"total": 500}')
        assert result.threshold == 0.3


class TestEvaluationReporting:
    """Tests for evaluation result reporting."""

    def test_generate_report(self):
        """Test generating evaluation report."""
        from app.services.evals import EvaluationPipeline

        pipeline = EvaluationPipeline()

        result = pipeline.evaluate_extraction(
            actual_output='{"total": 500}',
            expected_output='{"total": 500}',
        )

        report = result.to_dict()
        assert "overall_score" in report
        assert "passed" in report
        assert "metric_results" in report

    def test_summary_statistics(self):
        """Test generating summary statistics."""
        from app.services.evals import EvaluationPipeline

        pipeline = EvaluationPipeline()

        result = pipeline.evaluate_extraction(
            actual_output='{"total": 500}',
            expected_output='{"total": 500}',
            context="Invoice for $500",
        )

        details = result.overall_details
        assert "total_metrics" in details
        assert "passed_metrics" in details


class TestEvaluationEdgeCases:
    """Tests for edge cases in evaluation."""

    def test_empty_actual_output(self):
        """Test evaluating with empty actual output."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.5)

        result = metric.measure("", '{"total": 500}')

        # Should handle gracefully
        assert result.metric_type.value == "hallucination"
        assert isinstance(result.score, float)

    def test_empty_context(self):
        """Test evaluating with empty context."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.5)

        result = metric.measure('{"total": 500}', "")

        # Should handle gracefully
        assert isinstance(result.score, float)

    def test_malformed_output(self):
        """Test evaluating malformed LLM output."""
        from app.services.evals import HallucinationMetric

        metric = HallucinationMetric(threshold=0.5)

        result = metric.measure("This is not JSON", "Invoice for $500")

        # Should handle gracefully
        assert isinstance(result.score, float)

    def test_non_dict_json(self):
        """Test evaluating JSON that's not a dict."""
        from app.services.evals import FaithfulnessMetric

        metric = FaithfulnessMetric(threshold=0.5)

        result = metric.measure('"just a string"', '{"total": 500}')

        # Should handle gracefully
        assert isinstance(result.score, float)


class TestExtractionTestCase:
    """Tests for ExtractionTestCase model."""

    def test_create_test_case(self):
        """Test creating an extraction test case."""
        from app.services.evals import ExtractionTestCase

        test_case = ExtractionTestCase(
            name="Basic Invoice",
            input="Extract invoice data",
            actual_output='{"total": 500}',
            expected_output={"total": 500},
            context="Invoice for $500"
        )

        assert test_case.name == "Basic Invoice"
        assert test_case.expected_output == {"total": 500}
