"""
Email processors for AP Intake & Validation system.

This module provides specialized processors for different aspects of email handling:
- SecurityProcessor: Validates email security and detects threats
- ExtractionProcessor: Extracts invoice data from email content
- TemplateProcessor: Renders email templates and manages email formatting
"""

from .security import SecurityProcessor
from .extraction import ExtractionProcessor
from .templates import TemplateProcessor

__all__ = [
    'SecurityProcessor',
    'ExtractionProcessor', 
    'TemplateProcessor'
]