"""
Enhanced validation utilities building on core validation for better developer experience.
"""

import re
import uuid
from datetime import datetime, date
from typing import Any, Optional, List, Dict, Union, Type
from decimal import Decimal, InvalidOperation

from app.core.validation import ValidationError


class ValidationUtils:
    """Enhanced utility class for comprehensive input validation."""
    
    # Common regex patterns
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'phone_us': r'^\+?1[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})$',
        'phone_intl': r'^\+[1-9]\d{1,14}$',
        'url': r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$',
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        'ipv4': r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        'ipv6': r'^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$',
        'credit_card': r'^(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})$',
        'ssn': r'^(?!666|000|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}$',
        'postal_code_us': r'^\d{5}(-\d{4})?$',
        'postal_code_ca': r'^[A-Z]\d[A-Z] \d[A-Z]\d$',
    }
    
    @classmethod
    def validate_pattern(cls, value: str, pattern_name: str, field_name: str = "Value") -> str:
        """Validate string against predefined pattern."""
        if pattern_name not in cls.PATTERNS:
            raise ValidationError(f"Unknown pattern: {pattern_name}")
        
        pattern = cls.PATTERNS[pattern_name]
        if not re.match(pattern, value):
            raise ValidationError(f"Invalid {field_name} format")
        
        return value
    
    @classmethod
    def validate_email(cls, email: str) -> str:
        """Validate email format with enhanced checks."""
        if not isinstance(email, str):
            raise ValidationError("Email must be a string")
        
        email = email.strip().lower()
        
        # Basic format validation
        cls.validate_pattern(email, 'email', 'email')
        
        # Additional checks
        if email.startswith('.') or email.endswith('.'):
            raise ValidationError("Email cannot start or end with a dot")
        
        if '..' in email:
            raise ValidationError("Email cannot contain consecutive dots")
        
        return email
    
    @classmethod
    def validate_phone(cls, phone: str, country: str = 'US') -> str:
        """Validate phone number format for specific country."""
        if not isinstance(phone, str):
            raise ValidationError("Phone number must be a string")
        
        # Remove all non-digit characters except + for international
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        if country.upper() == 'US':
            cls.validate_pattern(phone, 'phone_us', 'phone number')
        else:
            cls.validate_pattern(cleaned, 'phone_intl', 'international phone number')
        
        return cleaned
    
    @classmethod
    def validate_url(cls, url: str) -> str:
        """Validate URL format."""
        if not isinstance(url, str):
            raise ValidationError("URL must be a string")
        
        url = url.strip()
        cls.validate_pattern(url, 'url', 'URL')
        
        return url
    
    @classmethod
    def validate_uuid(cls, uuid_string: str, field_name: str = "ID") -> uuid.UUID:
        """Validate UUID string and return UUID object."""
        if not isinstance(uuid_string, str):
            raise ValidationError(f"{field_name} must be a string")
        
        try:
            return uuid.UUID(uuid_string)
        except ValueError:
            raise ValidationError(f"Invalid {field_name} format")
    
    @classmethod
    def validate_ip_address(cls, ip: str, version: str = 'both') -> str:
        """Validate IP address format."""
        if not isinstance(ip, str):
            raise ValidationError("IP address must be a string")
        
        if version in ('ipv4', 'both'):
            if re.match(cls.PATTERNS['ipv4'], ip):
                return ip
        
        if version in ('ipv6', 'both'):
            if re.match(cls.PATTERNS['ipv6'], ip):
                return ip
        
        raise ValidationError(f"Invalid IP address format")
    
    @classmethod
    def validate_credit_card(cls, card_number: str) -> str:
        """Validate credit card number with Luhn algorithm."""
        if not isinstance(card_number, str):
            raise ValidationError("Credit card number must be a string")
        
        # Remove spaces and dashes
        cleaned = re.sub(r'[\s-]', '', card_number)
        
        # Pattern validation
        cls.validate_pattern(cleaned, 'credit_card', 'credit card number')
        
        # Luhn algorithm validation
        total = 0
        reverse_digits = map(int, reversed(cleaned))
        
        for i, digit in enumerate(reverse_digits):
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        
        if total % 10 != 0:
            raise ValidationError("Invalid credit card number")
        
        return cleaned
    
    @classmethod
    def validate_ssn(cls, ssn: str) -> str:
        """Validate Social Security Number format."""
        if not isinstance(ssn, str):
            raise ValidationError("SSN must be a string")
        
        cls.validate_pattern(ssn, 'ssn', 'SSN')
        return ssn
    
    @classmethod
    def validate_postal_code(cls, postal_code: str, country: str = 'US') -> str:
        """Validate postal code format for specific country."""
        if not isinstance(postal_code, str):
            raise ValidationError("Postal code must be a string")
        
        postal_code = postal_code.strip().upper()
        
        if country.upper() == 'US':
            cls.validate_pattern(postal_code, 'postal_code_us', 'US postal code')
        elif country.upper() == 'CA':
            cls.validate_pattern(postal_code, 'postal_code_ca', 'Canadian postal code')
        else:
            raise ValidationError(f"Unsupported country for postal code validation: {country}")
        
        return postal_code
    
    @classmethod
    def validate_date_range(cls, start_date: Union[str, date, datetime], 
                           end_date: Union[str, date, datetime], 
                           field_name: str = "Date range") -> tuple[date, date]:
        """Validate date range with proper ordering."""
        # Convert to date objects
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date).date()
        elif isinstance(start_date, datetime):
            start_date = start_date.date()
        
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date).date()
        elif isinstance(end_date, datetime):
            end_date = end_date.date()
        
        if start_date > end_date:
            raise ValidationError(f"{field_name}: Start date must be before end date")
        
        return start_date, end_date
    
    @classmethod
    def validate_decimal(cls, value: Any, min_value: Optional[Decimal] = None, 
                       max_value: Optional[Decimal] = None, 
                       decimal_places: Optional[int] = None,
                       field_name: str = "Value") -> Decimal:
        """Validate decimal value with range and precision constraints."""
        try:
            decimal_value = Decimal(str(value))
        except (ValueError, InvalidOperation, TypeError):
            raise ValidationError(f"{field_name} must be a valid decimal number")
        
        if min_value is not None and decimal_value < min_value:
            raise ValidationError(f"{field_name} must be at least {min_value}")
        
        if max_value is not None and decimal_value > max_value:
            raise ValidationError(f"{field_name} must be at most {max_value}")
        
        if decimal_places is not None:
            if decimal_value.as_tuple().exponent < -decimal_places:
                raise ValidationError(f"{field_name} cannot have more than {decimal_places} decimal places")
        
        return decimal_value
    
    @classmethod
    def validate_list_items(cls, items: List[Any], item_validator: callable, 
                           min_items: Optional[int] = None, max_items: Optional[int] = None,
                           field_name: str = "List") -> List[Any]:
        """Validate list of items with custom validator."""
        if not isinstance(items, list):
            raise ValidationError(f"{field_name} must be a list")
        
        if min_items is not None and len(items) < min_items:
            raise ValidationError(f"{field_name} must have at least {min_items} items")
        
        if max_items is not None and len(items) > max_items:
            raise ValidationError(f"{field_name} must have at most {max_items} items")
        
        validated_items = []
        for i, item in enumerate(items):
            try:
                validated_item = item_validator(item)
                validated_items.append(validated_item)
            except ValidationError as e:
                raise ValidationError(f"{field_name}[{i}]: {str(e)}")
        
        return validated_items
    
    @classmethod
    def validate_dict_keys(cls, data: Dict[str, Any], required_keys: List[str], 
                          optional_keys: Optional[List[str]] = None,
                          field_name: str = "Dictionary") -> Dict[str, Any]:
        """Validate dictionary keys and structure."""
        if not isinstance(data, dict):
            raise ValidationError(f"{field_name} must be a dictionary")
        
        # Check required keys
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise ValidationError(f"{field_name} missing required keys: {', '.join(missing_keys)}")
        
        # Check for unexpected keys
        allowed_keys = set(required_keys + (optional_keys or []))
        unexpected_keys = [key for key in data.keys() if key not in allowed_keys]
        if unexpected_keys:
            raise ValidationError(f"{field_name} contains unexpected keys: {', '.join(unexpected_keys)}")
        
        return data
    
    @classmethod
    def validate_json_schema(cls, data: Any, schema: Dict[str, Any], 
                           field_name: str = "Data") -> Any:
        """Validate data against JSON schema."""
        try:
            import jsonschema
            jsonschema.validate(data, schema)
            return data
        except ImportError:
            raise ValidationError("jsonschema library not available for validation")
        except jsonschema.ValidationError as e:
            raise ValidationError(f"{field_name}: {e.message}")
    
    @classmethod
    def validate_business_rules(cls, data: Dict[str, Any], rules: Dict[str, callable],
                              field_name: str = "Data") -> Dict[str, Any]:
        """Validate data against custom business rules."""
        errors = []
        
        for rule_name, rule_func in rules.items():
            try:
                rule_func(data)
            except ValidationError as e:
                errors.append(f"{rule_name}: {str(e)}")
        
        if errors:
            raise ValidationError(f"{field_name} business rule violations: {'; '.join(errors)}")
        
        return data
    
    @classmethod
    def create_validator_chain(cls, *validators) -> callable:
        """Create a chain of validators that run in sequence."""
        def chained_validator(value):
            result = value
            for validator in validators:
                result = validator(result)
            return result
        return chained_validator