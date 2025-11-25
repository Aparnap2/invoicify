"""
Enhanced LLM service for structured invoice extraction using instructor.

This service provides intelligent data extraction and validation capabilities
with structured Pydantic outputs for improved reliability and type safety.
"""

import logging
import time
from typing import Any, Dict, Optional, List, Type, TypeVar
import json
import asyncio
from dataclasses import dataclass
from decimal import Decimal

import instructor
from openai import OpenAI, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import ExtractionException, LLMException
from app.schemas.invoice_extraction import (
    InvoiceExtraction, Vendor, Address, InvoiceHeader, LineItem,
    ConfidenceScores, ExtractionPatchResponse, FieldPatch,
    InvoiceContext, ExtractionQuality, create_extraction_from_dict
)

logger = logging.getLogger(__name__)

# Generic type for instructor responses
T = TypeVar('T')


@dataclass
class LLMUsage:
    """Track LLM usage for cost monitoring."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    cost_estimate: float
    timestamp: float
    response_type: str  # Type of response requested


class LLMService:
    """
    Enhanced LLM service using instructor for structured outputs.

    This service leverages instructor to ensure type-safe, validated responses
    from the LLM for invoice extraction and field patching operations.
    """

    def __init__(self):
        """Initialize the LLM service with instructor integration."""
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.LLM_MODEL
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.temperature = settings.LLM_TEMPERATURE
        self.base_url = settings.OPENROUTER_BASE_URL
        self.provider = settings.LLM_PROVIDER
        self.app_name = settings.OPENROUTER_APP_NAME
        self.app_url = settings.OPENROUTER_APP_URL

        # Usage tracking
        self.usage_history: List[LLMUsage] = []
        self.total_cost: float = 0.0

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0
        self.backoff_factor = 2.0

        # Initialize instructor clients
        self.client = None
        self.async_client = None

        if self.api_key and self.provider == 'openrouter':
            try:
                # OpenAI client for instructor
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    default_headers={
                        "HTTP-Referer": self.app_url,
                        "X-Title": self.app_name,
                    }
                )

                # Async OpenAI client
                self.async_client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    default_headers={
                        "HTTP-Referer": self.app_url,
                        "X-Title": self.app_name,
                    }
                )

                # Patch the clients with instructor
                instructor.patch(client=self.client)
                instructor.patch(client=self.async_client)

                logger.info(f"Enhanced LLM service initialized with instructor using model: {self.model}")
                logger.info(f"OpenRouter configuration - Base URL: {self.base_url}, App: {self.app_name}")

            except ImportError as e:
                logger.error(f"Missing dependencies for instructor integration: {e}")
                logger.error("Please install with: pip install instructor openai>=1.0.0")
            except Exception as e:
                logger.error(f"Failed to initialize instructor client: {e}")
        else:
            logger.warning(f"OpenRouter API key not configured or provider not set to 'openrouter'. Enhanced LLM service will be disabled")

    async def extract_invoice_from_text(
        self,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> InvoiceExtraction:
        """
        Extract complete invoice information from raw text using structured outputs.

        Args:
            text_content: Raw text extracted from invoice PDF
            metadata: Additional metadata about the extraction

        Returns:
            InvoiceExtraction: Structured invoice data with confidence scores

        Raises:
            LLMException: If extraction fails or returns invalid data
        """
        if not self.async_client:
            raise LLMException("LLM client not available for extraction")

        try:
            logger.info(f"Starting structured invoice extraction from {len(text_content)} characters")

            # Truncate text if too long for LLM context
            max_text_length = 8000  # Leave room for prompt and response
            if len(text_content) > max_text_length:
                text_content = text_content[:max_text_length] + "\n[TRUNCATED]"
                logger.warning(f"Text truncated to {max_text_length} characters for LLM processing")

            # Create extraction prompt
            system_prompt = self._get_extraction_system_prompt()
            user_prompt = self._get_extraction_user_prompt(text_content, metadata)

            # Call LLM with structured response
            extraction = await self._call_structured_llm(
                response_model=InvoiceExtraction,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            logger.info(f"Successfully extracted invoice with {len(extraction.line_items)} line items")
            logger.info(f"Extraction confidence: {extraction.confidence.overall}")

            return extraction

        except ValidationError as e:
            logger.error(f"LLM response validation failed: {e}")
            raise LLMException(f"Invalid structured response from LLM: {str(e)}") from e
        except Exception as e:
            logger.error(f"Failed to extract invoice from text: {e}")
            raise LLMException(f"Extraction failed: {str(e)}") from e

    async def patch_low_confidence_fields(
        self,
        extraction_result: Dict[str, Any],
        confidence_threshold: Optional[float] = None
    ) -> ExtractionPatchResponse:
        """
        Patch low-confidence fields using structured LLM responses.

        Args:
            extraction_result: Current extraction result with confidence scores
            confidence_threshold: Override default confidence threshold

        Returns:
            ExtractionPatchResponse: Structured patch recommendations

        Raises:
            LLMException: If patching fails or returns invalid data
        """
        if not self.async_client:
            raise LLMException("LLM client not available for field patching")

        try:
            threshold = confidence_threshold or settings.DOCLING_CONFIDENCE_THRESHOLD
            logger.info(f"Patching low-confidence fields (threshold: {threshold})")

            # Identify low-confidence fields
            low_confidence_fields = self._identify_low_confidence_fields(
                extraction_result, threshold
            )

            if not low_confidence_fields:
                logger.info("No low-confidence fields to patch")
                return ExtractionPatchResponse(
                    patches=[],
                    patch_summary="No fields required patching",
                    overall_confidence_improvement=Decimal("0.0"),
                    requires_manual_review=False
                )

            # Create patching prompt
            system_prompt = self._get_patching_system_prompt()
            user_prompt = self._get_patching_user_prompt(
                extraction_result, low_confidence_fields
            )

            # Call LLM with structured patch response
            patch_response = await self._call_structured_llm(
                response_model=ExtractionPatchResponse,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            logger.info(f"Generated {len(patch_response.patches)} field patches")
            logger.info(f"Confidence improvement: {patch_response.overall_confidence_improvement}")

            return patch_response

        except ValidationError as e:
            logger.error(f"Patch response validation failed: {e}")
            raise LLMException(f"Invalid patch response from LLM: {str(e)}") from e
        except Exception as e:
            logger.error(f"Failed to patch low-confidence fields: {e}")
            raise LLMException(f"Field patching failed: {str(e)}") from e

    async def extract_invoice_context(
        self,
        full_text: str,
        max_length: int = 3000
    ) -> InvoiceContext:
        """
        Extract contextual information about the invoice document.

        Args:
            full_text: Full text content from the document
            max_length: Maximum characters to analyze

        Returns:
            InvoiceContext: Contextual information about the document
        """
        if not self.async_client:
            raise LLMException("LLM client not available for context extraction")

        try:
            # Limit text length for context analysis
            analysis_text = full_text[:max_length]

            system_prompt = """
            You are an expert document analyst. Analyze the provided invoice text
            and provide contextual information about the document type, business domain,
            and key entities present.
            """

            user_prompt = f"""
            Analyze this invoice/document text and provide context:

            {analysis_text}

            Focus on:
            1. Document type (invoice, receipt, quote, etc.)
            2. Business domain or industry
            3. Key entities (companies, dates, amounts)
            4. Document structure and sections
            5. Overall confidence in context extraction
            """

            context = await self._call_structured_llm(
                response_model=InvoiceContext,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            logger.info(f"Extracted document context: {context.document_type}")
            return context

        except ValidationError as e:
            logger.error(f"Context extraction validation failed: {e}")
            raise LLMException(f"Invalid context response: {str(e)}") from e
        except Exception as e:
            logger.error(f"Failed to extract invoice context: {e}")
            raise LLMException(f"Context extraction failed: {str(e)}") from e

    async def improve_extraction_quality(
        self,
        extraction: InvoiceExtraction,
        additional_context: Optional[str] = None
    ) -> ExtractionQuality:
        """
        Analyze and provide quality assessment for extraction results.

        Args:
            extraction: The invoice extraction to analyze
            additional_context: Additional context about the extraction

        Returns:
            ExtractionQuality: Quality assessment and recommendations
        """
        if not self.async_client:
            raise LLMException("LLM client not available for quality assessment")

        try:
            system_prompt = """
            You are an expert in invoice data quality assessment. Analyze the provided
            extraction and provide detailed quality metrics, identify issues, and suggest
            improvements for better accuracy.
            """

            user_prompt = f"""
            Analyze this invoice extraction for quality:

            Vendor: {extraction.vendor.vendor_name}
            Invoice Number: {extraction.header.invoice_number}
            Total Amount: {extraction.header.total_amount} {extraction.header.currency}
            Line Items: {len(extraction.line_items)}
            Overall Confidence: {extraction.confidence.overall}

            {additional_context or ""}

            Provide:
            1. Completeness score (0-1)
            2. Accuracy score (0-1)
            3. Confidence score (0-1)
            4. Quality issues identified
            5. Recommendations for improvement
            """

            quality = await self._call_structured_llm(
                response_model=ExtractionQuality,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            logger.info(f"Quality assessment - Completeness: {quality.completeness_score}, "
                       f"Accuracy: {quality.accuracy_score}")

            return quality

        except ValidationError as e:
            logger.error(f"Quality assessment validation failed: {e}")
            raise LLMException(f"Invalid quality response: {str(e)}") from e
        except Exception as e:
            logger.error(f"Failed to assess extraction quality: {e}")
            raise LLMException(f"Quality assessment failed: {str(e)}") from e

    async def _call_structured_llm(
        self,
        response_model: Type[T],
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None
    ) -> T:
        """
        Call LLM with structured response using instructor.

        Args:
            response_model: Pydantic model for structured response
            system_prompt: System prompt for the LLM
            user_prompt: User prompt for the LLM
            temperature: Override default temperature

        Returns:
            T: Structured response of type response_model
        """
        start_time = time.time()
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Structured LLM call attempt {attempt + 1}/{self.max_retries}")

                # Create messages
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                # Call LLM with instructor
                response = await self.async_client.chat.completions.create(
                    model=self.model,
                    response_model=response_model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=temperature or self.temperature,
                )

                # Track usage
                if hasattr(response, 'usage') and response.usage:
                    await self._track_usage(
                        response.usage,
                        start_time,
                        response_model.__name__
                    )

                response_time = time.time() - start_time
                logger.debug(f"Structured LLM response received in {response_time:.2f}s")

                return response

            except ValidationError as e:
                # Don't retry validation errors - they indicate structural issues
                logger.error(f"Response validation failed: {e}")
                raise LLMException(f"LLM response validation failed: {str(e)}") from e

            except Exception as e:
                last_exception = e
                logger.warning(f"Structured LLM call attempt {attempt + 1} failed: {e}")

                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    delay = self.retry_delay * (self.backoff_factor ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)

        # All attempts failed
        raise LLMException(
            f"Structured LLM service failed after {self.max_retries} attempts: {str(last_exception)}"
        ) from last_exception

    def _get_extraction_system_prompt(self) -> str:
        """Get system prompt for invoice extraction."""
        return """
        You are an expert invoice data extraction specialist. Extract structured information
        from the provided invoice text and return it as a complete InvoiceExtraction object.

        CRITICAL REQUIREMENTS:
        1. Extract ALL line items with accurate quantities and amounts
        2. Ensure mathematical consistency between line items and totals
        3. Use proper data types and formats as specified in the schema
        4. Include confidence scores that reflect extraction certainty
        5. Handle partial information gracefully - set fields to None if not found
        6. Normalize and standardize all extracted values

        MATHEMATICAL VALIDATION:
        - Line item totals must equal quantity × unit_price
        - Sum of line items should match header subtotal
        - Total amount should include tax if present

        CONFIDENCE GUIDELINES:
        - Use 0.9-1.0 for clearly printed, standard format data
        - Use 0.7-0.9 for legible but slightly ambiguous data
        - Use 0.5-0.7 for handwritten or poor quality data
        - Use 0.3-0.5 for very uncertain extractions
        - Use 0.1-0.3 for guesses with little evidence

        Return ONLY the InvoiceExtraction object - no additional text or explanation.
        """

    def _get_extraction_user_prompt(
        self,
        text_content: str,
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Get user prompt for invoice extraction."""
        prompt = f"""
        Extract structured invoice data from this text:

        INVOICE TEXT:
        {text_content}

        """

        if metadata:
            prompt += f"""
        ADDITIONAL METADATA:
        {json.dumps(metadata, indent=2, default=str)}

        """

        prompt += """
        Extract ALL available information including:
        - Vendor details (name, address, tax info)
        - Invoice header (number, dates, amounts, currency)
        - Line items (description, quantity, unit price, total)
        - Any other relevant fields

        Ensure mathematical consistency and provide realistic confidence scores.
        """

        return prompt

    def _get_patching_system_prompt(self) -> str:
        """Get system prompt for field patching."""
        return """
        You are an expert invoice data correction specialist. Review the provided
        extraction data and identify corrections for low-confidence fields.

        CORRECTION PRINCIPLES:
        1. Correct obvious typos, formatting errors, and OCR mistakes
        2. Standardize dates, currencies, and number formats
        3. Infer missing values only when highly confident
        4. Ensure mathematical consistency across all fields
        5. Maintain the original data structure and field names

        CONFIDENCE BOOSTING:
        - Provide realistic confidence improvements (0.05 to 0.25)
        - Higher boosts for clear corrections
        - Lower boosts for uncertain inferences
        - Consider context and business logic

        Return ONLY the ExtractionPatchResponse object with all required corrections.
        """

    def _get_patching_user_prompt(
        self,
        extraction_result: Dict[str, Any],
        low_confidence_fields: Dict[str, float]
    ) -> str:
        """Get user prompt for field patching."""
        prompt = f"""
        Review and correct low-confidence fields in this invoice extraction:

        CURRENT EXTRACTION:
        {json.dumps(extraction_result, indent=2, default=str)}

        LOW CONFIDENCE FIELDS (< {settings.DOCLING_CONFIDENCE_THRESHOLD}):
        {json.dumps(low_confidence_fields, indent=2)}

        Focus on:
        1. Correcting typos in vendor names and addresses
        2. Fixing number formatting and currency symbols
        3. Standardizing date formats (YYYY-MM-DD)
        4. Ensuring mathematical consistency
        5. Improving data quality while preserving accuracy

        Provide specific corrections with confidence improvements and reasoning.
        """

        return prompt

    def _identify_low_confidence_fields(
        self,
        extraction_result: Dict[str, Any],
        threshold: float
    ) -> Dict[str, float]:
        """Identify fields with confidence below threshold."""
        low_confidence = {}

        confidence_data = extraction_result.get("confidence", {})

        # Check header confidence if available
        if isinstance(confidence_data, dict):
            header_confidence = confidence_data.get("header_fields", {})
            for field, confidence in header_confidence.items():
                try:
                    conf_val = float(confidence)
                    if conf_val < threshold:
                        low_confidence[f"header.{field}"] = conf_val
                except (ValueError, TypeError):
                    continue

            # Check line item confidence
            line_confidence = confidence_data.get("line_items", [])
            for i, confidence in enumerate(line_confidence):
                try:
                    conf_val = float(confidence)
                    if conf_val < threshold:
                        low_confidence[f"line_items.{i}"] = conf_val
                except (ValueError, TypeError):
                    continue

        # Check overall confidence
        overall_confidence = confidence_data.get("overall", 0.0)
        try:
            if float(overall_confidence) < threshold:
                low_confidence["overall"] = float(overall_confidence)
        except (ValueError, TypeError):
            pass

        return low_confidence

    async def _track_usage(
        self,
        usage,
        start_time: float,
        response_type: str
    ):
        """Track LLM usage and estimate costs."""
        try:
            # Cost estimation (update with actual model pricing)
            # These are rough estimates - update based on actual OpenRouter pricing
            cost_per_1k_input = 0.001  # $0.001 per 1k input tokens
            cost_per_1k_output = 0.002  # $0.002 per 1k output tokens

            input_cost = (usage.prompt_tokens / 1000) * cost_per_1k_input
            output_cost = (usage.completion_tokens / 1000) * cost_per_1k_output
            total_cost = input_cost + output_cost

            usage_record = LLMUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                model=self.model,
                cost_estimate=total_cost,
                timestamp=start_time,
                response_type=response_type
            )

            self.usage_history.append(usage_record)
            self.total_cost += total_cost

            logger.info(
                f"LLM usage tracked - Type: {response_type}, "
                f"Tokens: {usage.total_tokens}, "
                f"Estimated cost: ${total_cost:.4f}"
            )

            # Keep only last 100 usage records
            if len(self.usage_history) > 100:
                self.usage_history = self.usage_history[-100:]

        except Exception as e:
            logger.warning(f"Failed to track usage: {e}")

    async def test_connection(self) -> Dict[str, Any]:
        """Test enhanced LLM connection and return status information."""
        if not self.async_client:
            return {
                "status": "error",
                "message": "Enhanced LLM client not initialized",
                "provider": self.provider,
                "model": self.model,
                "instructor_enabled": False
            }

        try:
            start_time = time.time()

            # Simple structured test call
            from pydantic import BaseModel
            class TestResponse(BaseModel):
                status: str
                message: str

            response = await self.async_client.chat.completions.create(
                model=self.model,
                response_model=TestResponse,
                messages=[
                    {"role": "user", "content": "Respond with a test message confirming the connection works."}
                ],
                max_tokens=50,
                temperature=0.0,
            )

            response_time = time.time() - start_time

            return {
                "status": "success",
                "message": "Enhanced LLM connection successful",
                "provider": self.provider,
                "model": self.model,
                "base_url": self.base_url,
                "response_time": f"{response_time:.2f}s",
                "test_response": response.status,
                "instructor_enabled": True,
                "total_usage_records": len(self.usage_history),
                "total_cost": f"${self.total_cost:.4f}"
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Enhanced LLM connection failed: {str(e)}",
                "provider": self.provider,
                "model": self.model,
                "base_url": self.base_url,
                "instructor_enabled": False
            }

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get detailed usage statistics."""
        if not self.usage_history:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "average_cost_per_request": 0.0,
                "response_type_stats": {}
            }

        total_tokens = sum(u.total_tokens for u in self.usage_history)
        response_type_stats = {}

        for usage in self.usage_history:
            rtype = usage.response_type
            if rtype not in response_type_stats:
                response_type_stats[rtype] = {
                    "count": 0,
                    "tokens": 0,
                    "cost": 0.0
                }
            response_type_stats[rtype]["count"] += 1
            response_type_stats[rtype]["tokens"] += usage.total_tokens
            response_type_stats[rtype]["cost"] += usage.cost_estimate

        return {
            "total_requests": len(self.usage_history),
            "total_tokens": total_tokens,
            "total_cost": self.total_cost,
            "average_cost_per_request": self.total_cost / len(self.usage_history),
            "average_tokens_per_request": total_tokens / len(self.usage_history),
            "model": self.model,
            "provider": self.provider,
            "instructor_enabled": True,
            "response_type_stats": response_type_stats
        }

    # Legacy compatibility methods
    async def patch_low_confidence_fields_legacy(
        self,
        extraction_result: Dict[str, Any],
        confidence_score: float
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.

        This method maintains the old interface while using the new structured approach.
        """
        try:
            # Use new structured approach
            patch_response = await self.patch_low_confidence_fields(
                extraction_result, confidence_score
            )

            # Convert back to legacy format
            patched_result = extraction_result.copy()

            # Apply patches to original result
            for patch in patch_response.patches:
                # Simple field path resolution for backward compatibility
                if patch.field_path.startswith("header."):
                    field_name = patch.field_path.replace("header.", "")
                    if "header" not in patched_result:
                        patched_result["header"] = {}
                    patched_result["header"][field_name] = patch.corrected_value
                elif patch.field_path.startswith("line_items."):
                    # Handle line item patches (simplified)
                    parts = patch.field_path.split(".")
                    if len(parts) >= 3:
                        line_idx = int(parts[1])
                        field_name = ".".join(parts[2:])
                        if "lines" not in patched_result:
                            patched_result["lines"] = []
                        while len(patched_result["lines"]) <= line_idx:
                            patched_result["lines"].append({})
                        patched_result["lines"][line_idx][field_name] = patch.corrected_value

            # Update confidence scores if available
            if "confidence" in patched_result:
                overall_confidence = float(patched_result["confidence"].get("overall", 0.8))
                improvement = float(patch_response.overall_confidence_improvement)
                patched_result["confidence"]["overall"] = min(1.0, overall_confidence + improvement)
                patched_result["overall_confidence"] = patched_result["confidence"]["overall"]

            return patched_result

        except Exception as e:
            logger.error(f"Legacy patching failed, returning original: {e}")
            return extraction_result

    def __bool__(self) -> bool:
        """Boolean check for service availability."""
        return self.async_client is not None