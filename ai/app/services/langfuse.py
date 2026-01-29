"""Langfuse observability integration for invoice processing.

Provides tracing for LangGraph workflows, LLM calls, and invoice processing steps.

Usage:
    from app.services.langfuse import get_langfuse_client, trace_invoice_workflow

    # In workflow nodes
    span = get_langfuse_client().start_span(
        name="extract_fields",
        input={"raw_content": "..."}
    )
    # ... do work
    span.end(output={"extracted_data": {...}})
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from langfuse import Langfuse

from app.config import get_settings

logger = logging.getLogger(__name__)


class LangfuseClient:
    """Langfuse client wrapper with async support."""

    def __init__(self):
        """Initialize Langfuse client."""
        self._client: Optional[Langfuse] = None
        self._enabled = False

    def initialize(self) -> bool:
        """Initialize Langfuse with config from settings."""
        settings = get_settings()

        # Check for Langfuse credentials
        public_key = settings.langfuse_public_key
        secret_key = settings.langfuse_secret_key

        if not public_key or not secret_key:
            logger.info("Langfuse credentials not configured, disabling tracing")
            return False

        try:
            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=settings.langfuse_host or "https://cloud.langfuse.com",
            )
            self._enabled = True
            logger.info("Langfuse initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if Langfuse is enabled."""
        return self._enabled and self._client is not None

    def start_span(
        self,
        name: str,
        input_data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> "SpanContext":
        """Start a new span for tracing."""
        if not self.is_enabled():
            return SpanContext.noop(name)

        return SpanContext(
            client=self._client,
            name=name,
            input_data=input_data,
            metadata=metadata,
            trace_id=trace_id,
        )

    def start_trace(
        self,
        name: str,
        input_data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "TraceContext":
        """Start a new trace for a workflow."""
        if not self.is_enabled():
            return TraceContext.noop(name)

        return TraceContext(
            client=self._client,
            name=name,
            input_data=input_data,
            metadata=metadata,
        )

    def log_generation(
        self,
        name: str,
        model: str,
        prompt: str,
        completion: str,
        metadata: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """Log an LLM generation event."""
        if not self.is_enabled():
            return

        try:
            self._client.generation(
                name=name,
                model=model,
                input=prompt,
                output=completion,
                metadata=metadata or {},
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning(f"Failed to log generation to Langfuse: {e}")


class SpanContext:
    """Context manager for span tracing."""

    def __init__(
        self,
        client: Langfuse,
        name: str,
        input_data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ):
        """Initialize span context."""
        self._client = client
        self._name = name
        self._input = input_data
        self._metadata = metadata or {}
        self._trace_id = trace_id
        self._span_id: Optional[str] = None
        self._output: Optional[dict[str, Any]] = None
        self._ended = False

    def set_output(self, output: dict[str, Any]) -> None:
        """Set the span output."""
        self._output = output

    def add_event(self, name: str, data: dict[str, Any]) -> None:
        """Add an event to the span."""
        if self._ended:
            return
        try:
            self._client.event(
                name=name,
                input=data,
                trace_id=self._trace_id,
            )
        except Exception as e:
            logger.warning(f"Failed to add event to Langfuse: {e}")

    def end(self, output: Optional[dict[str, Any]] = None) -> None:
        """End the span."""
        if self._ended:
            return
        self._ended = True

        if output:
            self._output = output

        try:
            self._client.span(
                name=self._name,
                input=self._input,
                output=self._output,
                metadata=self._metadata,
                trace_id=self._trace_id,
            )
        except Exception as e:
            logger.warning(f"Failed to end span in Langfuse: {e}")

    @classmethod
    def noop(cls, name: str) -> "SpanContext":
        """Create a no-op span context."""
        return NoopSpanContext(name)


class NoopSpanContext:
    """No-op span context when Langfuse is disabled."""

    def __init__(self, name: str):
        """Initialize no-op context."""
        self._name = name

    def set_output(self, output: dict[str, Any]) -> None:
        """No-op."""
        pass

    def add_event(self, name: str, data: dict[str, Any]) -> None:
        """No-op."""
        pass

    def end(self, output: Optional[dict[str, Any]] = None) -> None:
        """No-op."""
        pass


class TraceContext:
    """Context manager for trace tracing."""

    def __init__(
        self,
        client: Langfuse,
        name: str,
        input_data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """Initialize trace context."""
        self._client = client
        self._name = name
        self._input = input_data
        self._metadata = metadata or {}
        self._trace_id: Optional[str] = None

    def start_span(
        self,
        name: str,
        input_data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SpanContext:
        """Start a child span."""
        if self._trace_id is None:
            return SpanContext.noop(name)

        return SpanContext(
            client=self._client,
            name=name,
            input_data=input_data,
            metadata=metadata,
            trace_id=self._trace_id,
        )

    def end(self, output: Optional[dict[str, Any]] = None) -> None:
        """End the trace."""
        try:
            self._client.trace(
                name=self._name,
                input=self._input,
                output=output,
                metadata=self._metadata,
            )
        except Exception as e:
            logger.warning(f"Failed to end trace in Langfuse: {e}")

    @classmethod
    def noop(cls, name: str) -> "TraceContext":
        """Create a no-op trace context."""
        return NoopTraceContext(name)


class NoopTraceContext:
    """No-op trace context when Langfuse is disabled."""

    def __init__(self, name: str):
        """Initialize no-op context."""
        self._name = name

    def start_span(self, name: str, input_data=None, metadata=None) -> SpanContext:
        """Return no-op span."""
        return SpanContext.noop(name)

    def end(self, output=None) -> None:
        """No-op."""
        pass


# Global client instance
_langfuse_client: Optional[LangfuseClient] = None


def get_langfuse_client() -> LangfuseClient:
    """Get the singleton Langfuse client."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = LangfuseClient()
        _langfuse_client.initialize()
    return _langfuse_client


def reset_langfuse_client() -> None:
    """Reset the Langfuse client (for testing)."""
    global _langfuse_client
    _langfuse_client = None


async def trace_workflow_step(
    step_name: str,
    workflow_id: str,
    input_data: dict[str, Any],
) -> AsyncGenerator[SpanContext, None]:
    """Context manager for tracing a workflow step.

    Usage:
        async with trace_workflow_step("extract_fields", workflow_id, {"raw_content": "..."}) as span:
            result = await extract_fields(raw_content)
            span.set_output({"extracted": result})
    """
    client = get_langfuse_client()
    trace = client.start_trace(
        name=f"invoice_workflow.{step_name}",
        input_data={"workflow_id": workflow_id, **input_data},
        metadata={"workflow_id": workflow_id, "step": step_name},
    )
    span = trace.start_span(name=step_name, input_data=input_data)

    try:
        yield span
    finally:
        span.end()


class InvoiceWorkflowTracer:
    """Tracer for invoice workflow with built-in LangGraph integration."""

    @staticmethod
    async def trace_extraction(
        invoice_id: str,
        raw_content: str,
        extracted_data: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Trace invoice extraction step."""
        client = get_langfuse_client()
        if not client.is_enabled():
            return

        with client.start_span(
            name="invoice_extraction",
            metadata={
                "invoice_id": invoice_id,
                "duration_ms": duration_ms,
                "vendor": extracted_data.get("vendor_name"),
                "amount": extracted_data.get("total_amount"),
            },
        ) as span:
            span.set_output({"extracted_data": extracted_data})

    @staticmethod
    async def trace_llm_call(
        invoice_id: str,
        agent_name: str,
        model: str,
        prompt: str,
        response: str,
        duration_ms: float,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Trace an LLM call from an agent."""
        client = get_langfuse_client()
        if not client.is_enabled():
            return

        client.log_generation(
            name=f"{agent_name}.generate",
            model=model,
            prompt=prompt,
            completion=response,
            metadata={
                "invoice_id": invoice_id,
                "duration_ms": duration_ms,
                **(metadata or {}),
            },
        )

    @staticmethod
    async def trace_workflow_completion(
        invoice_id: str,
        workflow_id: str,
        final_status: str,
        duration_ms: float,
        total_cost: Optional[float] = None,
    ) -> None:
        """Trace workflow completion."""
        client = get_langfuse_client()
        if not client.is_enabled():
            return

        with client.start_trace(
            name="invoice_workflow.completed",
            input_data={
                "invoice_id": invoice_id,
                "workflow_id": workflow_id,
            },
            metadata={
                "invoice_id": invoice_id,
                "workflow_id": workflow_id,
                "final_status": final_status,
                "duration_ms": duration_ms,
            },
        ) as trace:
            trace.end(output={
                "status": final_status,
                "duration_ms": duration_ms,
                "cost_usd": total_cost,
            })


# Convenience function for tracing
def create_workflow_trace(
    invoice_id: str,
    input_data: dict[str, Any],
) -> TraceContext:
    """Create a trace for a workflow execution."""
    client = get_langfuse_client()
    return client.start_trace(
        name="invoice_workflow",
        input_data={"invoice_id": invoice_id, **input_data},
        metadata={"invoice_id": invoice_id},
    )
