"""
Instructor-based extraction service for structured LLM outputs.

This service provides intelligent invoice data extraction using instructor
for type-safe, validated responses from the LLM.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime

from app.services.llm_service import LLMService
from app.schemas.invoice_extraction import (
    InvoiceExtraction, Vendor, Address, InvoiceHeader, LineItem,
    ConfidenceScores, ExtractionQuality, calculate_extraction_quality
)
from app.core.config import settings
from app.core.exceptions import ExtractionException, LLMException

logger = logging.getLogger(__name__)


class InstructorExtractionService:
    """
    Extraction service using instructor for structured LLM outputs.

    This service leverages instructor to ensure type-safe, validated responses
    from the LLM for invoice extraction operations.
    """

    def __init__(self):
        """Initialize the instructor extraction service."""
        self.llm_service = LLMService()
        self.confidence_threshold = settings.DOCLING_CONFIDENCE_THRESHOLD

    async def extract_invoice_structured(
        self,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> InvoiceExtraction:
        """
        Extract complete invoice using structured LLM outputs.

        Args:
            text_content: Raw text extracted from PDF
            metadata: Additional metadata about the document

        Returns:
            Complete structured InvoiceExtraction

        Raises:
            LLMException: If LLM extraction fails
            ExtractionException: If extraction validation fails
        """
        if not self.llm_service:
            raise ExtractionException("LLM service not available for instructor extraction")

        try:
            logger.info(f"Starting instructor-based extraction from {len(text_content)} characters")

            # Extract using structured LLM response
            extraction = await self.llm_service.extract_invoice_from_text(
                text_content, metadata
            )

            # Validate and enhance the extraction
            quality = await self.llm_service.improve_extraction_quality(extraction)
            logger.info(f"Extraction quality - completeness: {quality.completeness_score}")

            # Add processing notes based on quality
            if quality.quality_issues:
                extraction.extraction_notes.extend([
                    f"Quality issue: {issue}" for issue in quality.quality_issues
                ])

            if quality.recommendations:
                extraction.extraction_notes.extend([
                    f"Recommendation: {rec}" for rec in quality.recommendations
                ])

            # Final validation
            is_valid, issues = await self.validate_extraction(extraction)
            if not is_valid:
                extraction.extraction_notes.extend([
                    f"Validation issue: {issue}" for issue in issues
                ])

            return extraction

        except LLMException as e:
            logger.error(f"Instructor extraction failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Structured extraction failed: {e}")
            raise ExtractionException(f"Failed to extract invoice: {str(e)}") from e

    async def enhance_extraction_with_patching(
        self,
        extraction: InvoiceExtraction,
        original_text: Optional[str] = None
    ) -> InvoiceExtraction:
        """
        Enhance existing extraction with LLM-based field patching.

        Args:
            extraction: Existing extraction to enhance
            original_text: Original text for context (optional)

        Returns:
            Enhanced extraction with improved fields
        """
        if not self.llm_service:
            logger.warning("LLM service not available for patching")
            return extraction

        try:
            logger.info("Applying LLM-based field patching")

            # Convert extraction to dict for patching
            extraction_dict = extraction.model_dump()

            # Apply patching
            patch_response = await self.llm_service.patch_low_confidence_fields(
                extraction_dict, self.confidence_threshold
            )

            if not patch_response.patches:
                logger.info("No patches required")
                return extraction

            # Apply patches
            enhanced_extraction = self._apply_patches(extraction, patch_response)

            # Update confidence scores
            enhanced_extraction = self._update_confidence(
                enhanced_extraction, patch_response
            )

            # Add processing notes
            enhanced_extraction.extraction_notes.append(
                f"Applied {len(patch_response.patches)} patches: {patch_response.patch_summary}"
            )

            if patch_response.requires_manual_review:
                enhanced_extraction.extraction_notes.append(
                    "Patched extraction requires manual review"
                )

            logger.info(f"Applied {len(patch_response.patches)} field patches")
            return enhanced_extraction

        except Exception as e:
            logger.error(f"Field patching failed: {e}")
            extraction.extraction_notes.append(f"Patching failed: {str(e)}")
            return extraction

    async def extract_with_validation(
        self,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        auto_patch: bool = True
    ) -> Tuple[InvoiceExtraction, Dict[str, Any]]:
        """
        Extract invoice with comprehensive validation and optional auto-patching.

        Args:
            text_content: Raw text extracted from PDF
            metadata: Additional metadata about the document
            auto_patch: Whether to automatically apply field patching

        Returns:
            Tuple of (extraction, validation_metadata)
        """
        try:
            # Initial extraction
            extraction = await self.extract_invoice_structured(text_content, metadata)

            # Auto-patch if enabled and confidence is low
            if auto_patch and extraction.confidence.overall < self.confidence_threshold:
                logger.info(f"Auto-patching enabled for confidence {extraction.confidence.overall}")
                extraction = await self.enhance_extraction_with_patching(
                    extraction, text_content
                )

            # Comprehensive validation
            validation_result = await self.comprehensive_validation(extraction)

            # Get quality assessment
            quality = calculate_extraction_quality(extraction)

            validation_metadata = {
                "validation": validation_result,
                "quality": quality.model_dump(),
                "confidence_breakdown": extraction.confidence.model_dump(),
                "processing_notes": extraction.extraction_notes,
                "extraction_timestamp": extraction.extraction_timestamp.isoformat(),
                "auto_patched": auto_patch and extraction.confidence.overall < self.confidence_threshold
            }

            return extraction, validation_metadata

        except Exception as e:
            logger.error(f"Extraction with validation failed: {e}")
            raise ExtractionException(f"Failed to extract with validation: {str(e)}") from e

    async def comprehensive_validation(
        self,
        extraction: InvoiceExtraction
    ) -> Dict[str, Any]:
        """
        Perform comprehensive validation of extraction results.

        Args:
            extraction: The extraction to validate

        Returns:
            Detailed validation results
        """
        validation_issues = []
        validation_warnings = []

        try:
            # Business logic validation
            business_issues = await self._validate_business_logic(extraction)
            validation_issues.extend(business_issues)

            # Mathematical validation
            math_issues = self._validate_mathematics(extraction)
            validation_issues.extend(math_issues)

            # Format validation
            format_warnings = self._validate_formats(extraction)
            validation_warnings.extend(format_warnings)

            # Confidence validation
            confidence_warnings = self._validate_confidence(extraction)
            validation_warnings.extend(confidence_warnings)

            is_valid = len(validation_issues) == 0
            requires_review = len(validation_issues) > 0 or len(validation_warnings) > 0

            return {
                "is_valid": is_valid,
                "requires_review": requires_review,
                "issues": validation_issues,
                "warnings": validation_warnings,
                "issue_count": len(validation_issues),
                "warning_count": len(validation_warnings)
            }

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "is_valid": False,
                "requires_review": True,
                "issues": [f"Validation error: {str(e)}"],
                "warnings": [],
                "issue_count": 1,
                "warning_count": 0
            }

    async def _validate_business_logic(
        self,
        extraction: InvoiceExtraction
    ) -> List[str]:
        """Validate business logic rules."""
        issues = []

        # Vendor validation
        if not extraction.vendor.vendor_name:
            issues.append("Vendor name is required")
        elif len(extraction.vendor.vendor_name.strip()) < 2:
            issues.append("Vendor name appears invalid (too short)")

        # Header validation
        if not extraction.header.invoice_date:
            issues.append("Invoice date is required")
        else:
            # Check if date is reasonable (not too far in past/future)
            invoice_date = extraction.header.invoice_date
            today = datetime.now().date()
            if invoice_date > today:
                issues.append("Invoice date is in the future")
            elif (today - invoice_date).days > 365:
                issues.append("Invoice date is more than 1 year old")

        if not extraction.header.total_amount or extraction.header.total_amount <= 0:
            issues.append("Total amount must be positive")

        # Line items validation
        if not extraction.line_items:
            issues.append("At least one line item is required")
        else:
            # Check for duplicate descriptions
            descriptions = [line.description.lower().strip() for line in extraction.line_items]
            if len(descriptions) != len(set(descriptions)):
                issues.append("Duplicate line item descriptions detected")

            # Check for suspicious amounts
            for i, line in enumerate(extraction.line_items):
                if line.total_amount > Decimal("100000"):
                    issues.append(f"Line {i+1} has unusually large amount: {line.total_amount}")

        return issues

    def _validate_mathematics(
        self,
        extraction: InvoiceExtraction
    ) -> List[str]:
        """Validate mathematical consistency."""
        issues = []

        try:
            # Check line item calculations
            for i, line in enumerate(extraction.line_items):
                expected_total = line.quantity * line.unit_price

                # Apply discount if present
                if line.discount_rate:
                    expected_total *= (1 - line.discount_rate)
                elif line.discount_amount:
                    expected_total -= line.discount_amount

                expected_total = expected_total.quantize(Decimal('0.01'))

                if abs(expected_total - line.total_amount) > Decimal("0.05"):
                    issues.append(
                        f"Line {i+1}: Mathematical inconsistency - "
                        f"expected {expected_total}, got {line.total_amount}"
                    )

            # Check totals consistency
            lines_total = sum(line.total_amount for line in extraction.line_items)

            if extraction.header.subtotal_amount:
                if abs(lines_total - extraction.header.subtotal_amount) > Decimal("1.00"):
                    issues.append(
                        f"Line items total ({lines_total}) doesn't match "
                        f"header subtotal ({extraction.header.subtotal_amount})"
                    )

            # Check tax calculations
            if (extraction.header.subtotal_amount and
                extraction.header.tax_amount and
                extraction.header.total_amount):

                expected_total = extraction.header.subtotal_amount + extraction.header.tax_amount
                expected_total = expected_total.quantize(Decimal('0.01'))

                if abs(expected_total - extraction.header.total_amount) > Decimal("0.05"):
                    issues.append(
                        f"Total calculation inconsistency - "
                        f"expected {expected_total}, got {extraction.header.total_amount}"
                    )

        except Exception as e:
            issues.append(f"Mathematical validation error: {str(e)}")

        return issues

    def _validate_formats(
        self,
        extraction: InvoiceExtraction
    ) -> List[str]:
        """Validate data formats."""
        warnings = []

        # Check currency format
        if extraction.header.currency and len(extraction.header.currency) != 3:
            warnings.append("Currency should be 3-letter ISO code")

        # Check phone number format if present
        if extraction.vendor.vendor_phone:
            phone = extraction.vendor.vendor_phone
            if not any(c.isdigit() for c in phone):
                warnings.append("Vendor phone number may be invalid")

        # Check email format if present
        if extraction.vendor.vendor_email:
            email = extraction.vendor.vendor_email
            if "@" not in email or "." not in email:
                warnings.append("Vendor email format may be invalid")

        return warnings

    def _validate_confidence(
        self,
        extraction: InvoiceExtraction
    ) -> List[str]:
        """Validate confidence scores."""
        warnings = []

        overall_conf = extraction.confidence.overall
        if overall_conf < 0.3:
            warnings.append("Very low overall confidence - manual review recommended")
        elif overall_conf < 0.7:
            warnings.append("Low overall confidence - consider manual review")

        # Check line item confidence distribution
        if hasattr(extraction.confidence, 'line_items'):
            line_confidences = extraction.confidence.line_items
            if line_confidences:
                avg_line_conf = sum(line_confidences) / len(line_confidences)
                if avg_line_conf < overall_conf - 0.2:
                    warnings.append("Line item confidence significantly lower than overall")

        return warnings

    def _apply_patches(
        self,
        extraction: InvoiceExtraction,
        patch_response
    ) -> InvoiceExtraction:
        """Apply patches to extraction."""
        try:
            for patch in patch_response.patches:
                # Apply patch based on field path
                if patch.field_path.startswith("vendor."):
                    field_name = patch.field_path.replace("vendor.", "")
                    if hasattr(extraction.vendor, field_name):
                        setattr(extraction.vendor, field_name, patch.corrected_value)

                elif patch.field_path.startswith("header."):
                    field_name = patch.field_path.replace("header.", "")
                    if hasattr(extraction.header, field_name):
                        setattr(extraction.header, field_name, patch.corrected_value)

                elif patch.field_path.startswith("line_items."):
                    parts = patch.field_path.split(".")
                    if len(parts) >= 3:
                        line_idx = int(parts[1])
                        field_name = parts[2]
                        if 0 <= line_idx < len(extraction.line_items):
                            line_item = extraction.line_items[line_idx]
                            if hasattr(line_item, field_name):
                                setattr(line_item, field_name, patch.corrected_value)

            return extraction

        except Exception as e:
            logger.error(f"Patch application failed: {e}")
            return extraction

    def _update_confidence(
        self,
        extraction: InvoiceExtraction,
        patch_response
    ) -> InvoiceExtraction:
        """Update confidence scores after patching."""
        try:
            improvement = float(patch_response.overall_confidence_improvement)
            current_confidence = float(extraction.confidence.overall)
            new_confidence = min(1.0, current_confidence + improvement)

            extraction.confidence.overall = Decimal(str(new_confidence))

            return extraction

        except Exception as e:
            logger.error(f"Confidence update failed: {e}")
            return extraction

    async def validate_extraction(self, extraction: InvoiceExtraction) -> Tuple[bool, List[str]]:
        """
        Validate extraction results.

        Args:
            extraction: The extraction to validate

        Returns:
            Tuple of (is_valid, issues)
        """
        validation_result = await self.comprehensive_validation(extraction)
        return validation_result["is_valid"], validation_result["issues"]

    async def get_extraction_context(
        self,
        text_content: str
    ) -> Dict[str, Any]:
        """Get contextual information about the document."""
        if not self.llm_service:
            return {"document_type": "unknown", "confidence": "low"}

        try:
            context = await self.llm_service.extract_invoice_context(text_content)
            return {
                "document_type": context.document_type,
                "business_domain": context.business_domain,
                "key_entities": context.key_entities,
                "document_structure": context.document_structure,
                "confidence_context": context.confidence_context
            }
        except Exception as e:
            logger.warning(f"Context extraction failed: {e}")
            return {"document_type": "unknown", "error": str(e)}

    def get_service_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service": "instructor_extraction",
            "llm_service_available": bool(self.llm_service),
            "confidence_threshold": self.confidence_threshold,
            "supported_features": [
                "structured_extraction",
                "field_patching",
                "comprehensive_validation",
                "quality_assessment",
                "context_extraction"
            ] if self.llm_service else ["llm_service_unavailable"]
        }

    async def test_extraction(
        self,
        sample_text: str,
        test_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Test extraction capabilities with sample data."""
        try:
            logger.info("Testing instructor extraction capabilities")

            # Test basic extraction
            extraction = await self.extract_invoice_structured(
                sample_text, test_metadata
            )

            # Test validation
            is_valid, issues = await self.validate_extraction(extraction)

            # Test context extraction
            context = await self.get_extraction_context(sample_text)

            # Test quality assessment
            quality = calculate_extraction_quality(extraction)

            return {
                "status": "success",
                "extraction": extraction.model_dump(),
                "validation": {
                    "is_valid": is_valid,
                    "issues": issues
                },
                "context": context,
                "quality": quality.model_dump(),
                "service_status": self.get_service_status()
            }

        except Exception as e:
            logger.error(f"Instructor extraction test failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "service_status": self.get_service_status()
            }