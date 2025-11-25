"""
String manipulation and formatting utilities for consistent text handling.
"""

import re
import html
import uuid
from typing import Optional, List, Dict, Any
from urllib.parse import quote, unquote


class StringUtils:
    """Utility class for string operations and formatting."""
    
    @staticmethod
    def sanitize(text: Optional[str], max_length: int = 1000) -> str:
        """Sanitize string input for security and consistency."""
        if text is None:
            return ""
        
        if not isinstance(text, str):
            text = str(text)
        
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
        
        # HTML entity encoding for XSS prevention
        text = html.escape(text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Truncate to max length
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + '...'
        
        return text.strip()
    
    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to URL-friendly slug."""
        # Convert to lowercase and replace spaces with hyphens
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)  # Remove special characters
        text = re.sub(r'[-\s]+', '-', text)   # Replace spaces and multiple hyphens
        return text.strip('-')
    
    @staticmethod
    def extract_numbers(text: str) -> List[float]:
        """Extract all numbers from text."""
        pattern = r'-?\d+\.?\d*'
        matches = re.findall(pattern, text)
        return [float(match) for match in matches]
    
    @staticmethod
    def extract_emails(text: str) -> List[str]:
        """Extract email addresses from text."""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.findall(pattern, text)
    
    @staticmethod
    def extract_phone_numbers(text: str) -> List[str]:
        """Extract phone numbers from text."""
        pattern = r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'
        matches = re.findall(pattern, text)
        return [''.join(match) for match in matches]
    
    @staticmethod
    def mask_sensitive_data(text: str, mask_char: str = '*') -> str:
        """Mask sensitive data like emails, phone numbers, credit cards."""
        # Mask emails
        email_pattern = r'\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b'
        text = re.sub(email_pattern, lambda m: f"{m.group(1)[0]}{mask_char * (len(m.group(1))-1)}@{m.group(2)}", text)
        
        # Mask phone numbers
        phone_pattern = r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'
        text = re.sub(phone_pattern, lambda m: f"{m.group(1)}({mask_char*3}) {mask_char*3}-{mask_char*4}", text)
        
        # Mask credit card numbers
        card_pattern = r'\b(\d{4}[-\s]?){3}\d{4}\b'
        text = re.sub(card_pattern, lambda m: mask_char * (len(m.group(0)) - 4) + m.group(0)[-4:], text)
        
        return text
    
    @staticmethod
    def generate_random_id(length: int = 8) -> str:
        """Generate random alphanumeric ID."""
        return uuid.uuid4().hex[:length]
    
    @staticmethod
    def format_currency(amount: float, currency: str = 'USD') -> str:
        """Format amount as currency string."""
        if currency == 'USD':
            return f"${amount:,.2f}"
        elif currency == 'EUR':
            return f"€{amount:,.2f}"
        elif currency == 'GBP':
            return f"£{amount:,.2f}"
        else:
            return f"{amount:,.2f} {currency}"
    
    @staticmethod
    def format_percentage(value: float, decimal_places: int = 2) -> str:
        """Format value as percentage."""
        return f"{value:.{decimal_places}f}%"
    
    @staticmethod
    def truncate_words(text: str, max_words: int, suffix: str = "...") -> str:
        """Truncate text to specified number of words."""
        words = text.split()
        if len(words) <= max_words:
            return text
        return ' '.join(words[:max_words]) + suffix
    
    @staticmethod
    def highlight_keywords(text: str, keywords: List[str], highlight_tag: str = "mark") -> str:
        """Highlight keywords in text with HTML tags."""
        for keyword in keywords:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            text = pattern.sub(f"<{highlight_tag}>{keyword}</{highlight_tag}>", text)
        return text
    
    @staticmethod
    def clean_html(text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)
    
    @staticmethod
    def is_empty_or_whitespace(text: Optional[str]) -> bool:
        """Check if string is empty or contains only whitespace."""
        return not text or text.strip() == ""
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        return ' '.join(text.split())
    
    @staticmethod
    def escape_sql_like(text: str) -> str:
        """Escape special characters for SQL LIKE queries."""
        return text.replace('%', '\\%').replace('_', '\\_')
    
    @staticmethod
    def url_encode(text: str) -> str:
        """URL encode text."""
        return quote(text)
    
    @staticmethod
    def url_decode(text: str) -> str:
        """URL decode text."""
        return unquote(text)
    
    @staticmethod
    def format_list(items: List[str], conjunction: str = "and") -> str:
        """Format list of strings as readable sentence."""
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f" {conjunction} ".join(items)
        return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"
    
    @staticmethod
    def extract_json_objects(text: str) -> List[Dict[str, Any]]:
        """Extract JSON objects from text."""
        import json
        json_objects = []
        
        # Find JSON-like structures
        pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                json_objects.append(json.loads(match))
            except json.JSONDecodeError:
                continue
        
        return json_objects