"""
Structured extraction schemas for LLM-based invoice processing using instructor.

This module defines strict Pydantic models for invoice extraction with proper field
validators and constraints to ensure high-quality structured outputs from LLMs.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from pydantic_core import ValidationError


# Base Models

class BaseExtractionModel(BaseModel):
    """Base model for all extraction models with common configuration."""

    model_config = ConfigDict(
        extra="forbid",  # Strict validation - no extra fields allowed
        validate_assignment=True,
        use_enum_values=True
    )


# Address Models

class Address(BaseExtractionModel):
    """Structured address information."""

    street: Optional[str] = Field(
        None,
        max_length=200,
        description="Street address (house number, street name)"
    )
    city: Optional[str] = Field(
        None,
        max_length=100,
        description="City name"
    )
    state: Optional[str] = Field(
        None,
        max_length=50,
        description="State or province"
    )
    postal_code: Optional[str] = Field(
        None,
        max_length=20,
        description="Postal/ZIP code"
    )
    country: Optional[str] = Field(
        None,
        max_length=2,
        min_length=2,
        description="Two-letter ISO country code"
    )

    @field_validator('country')
    @classmethod
    def validate_country_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO country code."""
        if v is None:
            return v
        return v.upper()

    @field_validator('postal_code')
    @classmethod
    def validate_postal_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate postal code format."""
        if v is None:
            return v
        # Basic postal code validation - can be enhanced based on country
        import re
        if not re.match(r'^[A-Z0-9\-\s]+$', v.upper()):
            raise ValueError("Invalid postal code format")
        return v.upper().strip()


# Vendor Models

class Vendor(BaseExtractionModel):
    """Vendor information extracted from invoice."""

    vendor_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Legal business name of vendor"
    )
    vendor_address: Optional[Address] = Field(
        None,
        description="Vendor's business address"
    )
    vendor_tax_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Tax identification number (EIN, ABN, VAT ID, etc.)"
    )
    vendor_email: Optional[str] = Field(
        None,
        max_length=255,
        description="Vendor's email address"
    )
    vendor_phone: Optional[str] = Field(
        None,
        max_length=50,
        description="Vendor's phone number"
    )
    vendor_website: Optional[str] = Field(
        None,
        max_length=255,
        description="Vendor's website URL"
    )

    @field_validator('vendor_email')
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format."""
        if v is None:
            return v
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator('vendor_tax_id')
    @classmethod
    def validate_tax_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate tax ID format."""
        if v is None:
            return v
        # Remove common separators and spaces
        cleaned = ''.join(c for c in v if c.isalnum())
        if len(cleaned) < 5 or len(cleaned) > 20:
            raise ValueError("Tax ID length should be between 5 and 20 characters")
        return cleaned

    @field_validator('vendor_phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v
        # Extract digits only
        digits = ''.join(c for c in v if c.isdigit())
        if len(digits) < 7:
            raise ValueError("Phone number too short")
        return v


# Line Item Models

class LineItem(BaseExtractionModel):
    """Individual line item from an invoice."""

    line_number: Optional[int] = Field(
        None,
        ge=1,
        le=999,
        description="Sequential line number (1-999)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Detailed description of goods or services"
    )
    quantity: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        max_digits=12,
        description="Quantity purchased (positive number)"
    )
    unit_price: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        max_digits=12,
        description="Price per unit"
    )
    total_amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        max_digits=15,
        description="Total amount for this line (quantity × unit_price)"
    )
    item_code: Optional[str] = Field(
        None,
        max_length=50,
        description="Product SKU, item number, or service code"
    )
    gl_account: Optional[str] = Field(
        None,
        max_length=50,
        description="General ledger account code"
    )
    tax_rate: Optional[Decimal] = Field(
        None,
        ge=0,
        le=1,
        decimal_places=4,
        max_digits=5,
        description="Tax rate as decimal (e.g., 0.08 for 8%)"
    )
    tax_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
        max_digits=12,
        description="Tax amount for this line"
    )
    discount_rate: Optional[Decimal] = Field(
        None,
        ge=0,
        le=1,
        decimal_places=4,
        max_digits=5,
        description="Discount rate as decimal"
    )
    discount_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
        max_digits=12,
        description="Discount amount for this line"
    )

    @model_validator(mode='after')
    def validate_amount_consistency(self) -> 'LineItem':
        """Validate that amounts are mathematically consistent."""
        # Calculate expected total
        expected_total = self.quantity * self.unit_price

        # Apply discount if present
        if self.discount_rate is not None:
            expected_total *= (1 - self.discount_rate)
        elif self.discount_amount is not None:
            expected_total -= self.discount_amount

        # Round to 2 decimal places for comparison
        expected_total = expected_total.quantize(Decimal('0.01'))
        actual_total = self.total_amount.quantize(Decimal('0.01'))

        # Allow small rounding differences
        if abs(expected_total - actual_total) > Decimal('0.05'):
            raise ValueError(
                f"Line item total inconsistency: expected {expected_total}, "
                f"got {actual_total}"
            )

        return self


# Invoice Header Models

class InvoiceHeader(BaseExtractionModel):
    """Header information extracted from invoice."""

    invoice_number: Optional[str] = Field(
        None,
        max_length=50,
        description="Unique invoice identifier from vendor"
    )
    invoice_date: Optional[date] = Field(
        None,
        description="Date when invoice was issued"
    )
    due_date: Optional[date] = Field(
        None,
        description="Payment due date"
    )
    subtotal_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
        max_digits=15,
        description="Subtotal before tax and discounts"
    )
    tax_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
        max_digits=15,
        description="Total tax amount"
    )
    total_amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        max_digits=15,
        description="Grand total amount to be paid"
    )
    currency: str = Field(
        "USD",
        min_length=3,
        max_length=3,
        description="3-letter ISO currency code"
    )
    purchase_order: Optional[str] = Field(
        None,
        max_length=50,
        description="Purchase order number if applicable"
    )
    order_date: Optional[date] = Field(
        None,
        description="Date when order was placed"
    )
    shipping_date: Optional[date] = Field(
        None,
        description="Date when goods were shipped"
    )
    payment_terms: Optional[str] = Field(
        None,
        max_length=100,
        description="Payment terms (e.g., 'NET 30', 'Due on Receipt')"
    )
    invoice_type: Optional[Literal["standard", "credit", "debit", "proforma"]] = Field(
        "standard",
        description="Type of invoice document"
    )

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate ISO currency code."""
        v = v.upper()
        # List of common currency codes
        common_currencies = {
            "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CNY", "INR",
            "CHF", "SEK", "NOK", "DKK", "NZD", "SGD", "HKD", "MXN"
        }
        if v not in common_currencies:
            raise ValueError(f"Unsupported currency code: {v}")
        return v

    @model_validator(mode='after')
    def validate_date_consistency(self) -> 'InvoiceHeader':
        """Validate that dates are logically consistent."""
        if self.invoice_date and self.due_date:
            if self.due_date < self.invoice_date:
                raise ValueError("Due date cannot be before invoice date")

        if self.order_date and self.invoice_date:
            if self.invoice_date < self.order_date:
                raise ValueError("Invoice date cannot be before order date")

        if self.shipping_date and self.invoice_date:
            # Shipping can be before or after invoice, but warn if far apart
            date_diff = abs((self.shipping_date - self.invoice_date).days)
            if date_diff > 365:
                raise ValueError("Shipping date and invoice date too far apart")

        return self


# Confidence Score Models

class ConfidenceScores(BaseExtractionModel):
    """Confidence scores for different extraction aspects."""

    overall: Decimal = Field(
        ...,
        ge=0,
        le=1,
        decimal_places=3,
        max_digits=4,
        description="Overall confidence score (0-1)"
    )
    header_fields: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Confidence scores for header fields"
    )
    line_items: List[Decimal] = Field(
        default_factory=list,
        description="Confidence scores for each line item"
    )

    @field_validator('header_fields', mode='before')
    @classmethod
    def validate_header_scores(cls, v: Any) -> Dict[str, Decimal]:
        """Validate header confidence scores."""
        if isinstance(v, dict):
            validated = {}
            for field, score in v.items():
                try:
                    validated[field] = Decimal(str(score))
                except (ValueError, TypeError):
                    continue
            return validated
        return {}

    @field_validator('line_items', mode='before')
    @classmethod
    def validate_line_scores(cls, v: Any) -> List[Decimal]:
        """Validate line item confidence scores."""
        if isinstance(v, list):
            validated = []
            for score in v:
                try:
                    validated.append(Decimal(str(score)))
                except (ValueError, TypeError):
                    validated.append(Decimal('0.0'))
            return validated
        return []


# Main Invoice Extraction Model

class InvoiceExtraction(BaseExtractionModel):
    """Complete structured extraction of invoice data."""

    extraction_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this extraction"
    )
    vendor: Vendor = Field(
        ...,
        description="Vendor information"
    )
    header: InvoiceHeader = Field(
        ...,
        description="Invoice header information"
    )
    line_items: List[LineItem] = Field(
        ...,
        min_length=1,
        description="List of line items"
    )
    confidence: ConfidenceScores = Field(
        ...,
        description="Confidence scores for extraction"
    )
    extraction_notes: List[str] = Field(
        default_factory=list,
        description="Notes about extraction quality or issues"
    )
    extraction_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When extraction was performed"
    )

    @model_validator(mode='after')
    def validate_line_item_consistency(self) -> 'InvoiceExtraction':
        """Validate line items against header totals."""
        if not self.line_items:
            raise ValueError("At least one line item is required")

        # Calculate line items total
        lines_total = sum(line.total_amount for line in self.line_items)

        # Compare with header total if subtotal is present
        if self.header.subtotal_amount is not None:
            lines_total = lines_total.quantize(Decimal('0.01'))
            subtotal = self.header.subtotal_amount.quantize(Decimal('0.01'))

            if abs(lines_total - subtotal) > Decimal('1.00'):  # Allow $1 tolerance
                raise ValueError(
                    f"Line items total ({lines_total}) doesn't match "
                    f"header subtotal ({subtotal})"
                )

        return self

    @model_validator(mode='after')
    def validate_line_number_sequence(self) -> 'InvoiceExtraction':
        """Validate that line numbers form a proper sequence."""
        numbered_lines = [
            line for line in self.line_items
            if line.line_number is not None
        ]

        if numbered_lines:
            # Check for duplicates
            numbers = [line.line_number for line in numbered_lines]
            if len(numbers) != len(set(numbers)):
                raise ValueError("Duplicate line numbers found")

            # Check sequence (should be 1, 2, 3, ...)
            sorted_numbers = sorted(numbers)
            expected = list(range(1, len(sorted_numbers) + 1))
            if sorted_numbers != expected:
                # Not a fatal error, just add a note
                self.extraction_notes.append(
                    "Line numbers are not in sequential order"
                )

        return self


# Patch Response Models for LLM Field Correction

class FieldPatch(BaseExtractionModel):
    """Patch for correcting individual fields."""

    field_path: str = Field(
        ...,
        description="Dot notation path to field (e.g., 'header.vendor_name')"
    )
    original_value: Any = Field(
        ...,
        description="Original value that was corrected"
    )
    corrected_value: Any = Field(
        ...,
        description="Corrected value"
    )
    confidence_boost: Decimal = Field(
        Decimal('0.1'),
        ge=0,
        le=1,
        decimal_places=3,
        description="Amount to boost confidence score"
    )
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Reason for the correction"
    )


class ExtractionPatchResponse(BaseExtractionModel):
    """Structured response for field patching requests."""

    patches: List[FieldPatch] = Field(
        ...,
        description="List of field corrections"
    )
    patch_summary: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Summary of what was corrected"
    )
    overall_confidence_improvement: Decimal = Field(
        ...,
        ge=0,
        le=1,
        decimal_places=3,
        description="Estimated improvement in overall confidence"
    )
    requires_manual_review: bool = Field(
        ...,
        description="Whether the patched result still requires manual review"
    )


# Context Extraction Models

class InvoiceContext(BaseExtractionModel):
    """Contextual information extracted from invoice text."""

    document_type: Literal["invoice", "receipt", "quote", "purchase_order", "credit_note"] = Field(
        ...,
        description="Type of document"
    )
    business_domain: Optional[str] = Field(
        None,
        max_length=100,
        description="Business domain (e.g., 'retail', 'services', 'manufacturing')"
    )
    key_entities: Dict[str, str] = Field(
        default_factory=dict,
        description="Key entities and their values"
    )
    document_structure: List[str] = Field(
        default_factory=list,
        description="Description of document structure"
    )
    confidence_context: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Context about extraction confidence"
    )


# Validation and Quality Models

class ExtractionQuality(BaseExtractionModel):
    """Quality assessment of extraction results."""

    completeness_score: Decimal = Field(
        ...,
        ge=0,
        le=1,
        decimal_places=3,
        description="How complete the extraction is"
    )
    accuracy_score: Decimal = Field(
        ...,
        ge=0,
        le=1,
        decimal_places=3,
        description="Estimated accuracy of extraction"
    )
    confidence_score: Decimal = Field(
        ...,
        ge=0,
        le=1,
        decimal_places=3,
        description="Overall confidence in extraction"
    )
    quality_issues: List[str] = Field(
        default_factory=list,
        description="List of quality issues detected"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations for improving extraction"
    )


# Utility Functions

def create_extraction_from_dict(data: Dict[str, Any]) -> InvoiceExtraction:
    """
    Create InvoiceExtraction from raw dictionary data.

    This helper function attempts to create a structured extraction
    from potentially incomplete or messy dictionary data.
    """
    try:
        return InvoiceExtraction.model_validate(data)
    except ValidationError as e:
        # Log validation errors and attempt to fix common issues
        error_details = e.errors()

        # Common fixes can be attempted here
        # For now, re-raise with more helpful message
        raise ValueError(
            f"Failed to create extraction from data: {error_details}"
        ) from e


def calculate_extraction_quality(extraction: InvoiceExtraction) -> ExtractionQuality:
    """
    Calculate quality metrics for an extraction.
    """
    # Completeness: how many required fields are filled
    completeness = 0.0
    total_fields = 0

    # Check vendor fields
    vendor_fields = [
        extraction.vendor.vendor_name,
        extraction.vendor.vendor_address,
        extraction.vendor.vendor_tax_id
    ]
    completeness += sum(1 for f in vendor_fields if f is not None)
    total_fields += len(vendor_fields)

    # Check header fields
    header_fields = [
        extraction.header.invoice_number,
        extraction.header.invoice_date,
        extraction.header.due_date
    ]
    completeness += sum(1 for f in header_fields if f is not None)
    total_fields += len(header_fields)

    if total_fields > 0:
        completeness_score = Decimal(str(completeness / total_fields))
    else:
        completeness_score = Decimal('0.0')

    # Use confidence as accuracy proxy
    accuracy_score = extraction.confidence.overall

    # Overall quality is weighted average
    overall_quality = (completeness_score + accuracy_score) / Decimal('2')

    # Identify issues
    issues = []
    if completeness_score < Decimal('0.5'):
        issues.append("Many required fields are missing")
    if accuracy_score < Decimal('0.8'):
        issues.append("Low confidence in extracted data")

    if len(extraction.line_items) == 0:
        issues.append("No line items extracted")

    return ExtractionQuality(
        completeness_score=completeness_score,
        accuracy_score=accuracy_score,
        confidence_score=overall_quality,
        quality_issues=issues,
        recommendations=[]
    )


# Export the main models
__all__ = [
    'InvoiceExtraction',
    'Vendor',
    'Address',
    'InvoiceHeader',
    'LineItem',
    'ConfidenceScores',
    'ExtractionPatchResponse',
    'FieldPatch',
    'InvoiceContext',
    'ExtractionQuality',
    'create_extraction_from_dict',
    'calculate_extraction_quality'
]