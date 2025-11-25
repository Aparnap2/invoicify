"""
Security utilities for consistent security operations across the application.
"""

import hashlib
import secrets
import jwt
import bcrypt
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import re
import ipaddress
from urllib.parse import urlparse


class SecurityUtils:
    """Utility class for security operations."""
    
    # Password hashing
    @staticmethod
    def hash_password(password: str, rounds: int = 12) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against bcrypt hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def generate_secure_password(length: int = 16, include_symbols: bool = True) -> str:
        """Generate secure random password."""
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        if include_symbols:
            alphabet += "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # Ensure password meets complexity requirements
        if length >= 8:
            # At least one uppercase, one lowercase, one digit, one symbol
            if not re.search(r'[A-Z]', password):
                password = password[:-1] + secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            if not re.search(r'[a-z]', password):
                password = password[:-1] + secrets.choice('abcdefghijklmnopqrstuvwxyz')
            if not re.search(r'\d', password):
                password = password[:-1] + secrets.choice('0123456789')
            if include_symbols and not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
                password = password[:-1] + secrets.choice('!@#$%^&*()_+-=[]{}|;:,.<>?')
        
        return password
    
    # Token operations
    @staticmethod
    def generate_jwt_token(payload: Dict[str, Any], secret_key: str, 
                         algorithm: str = 'HS256', expires_in: Optional[int] = None) -> str:
        """Generate JWT token."""
        if expires_in:
            payload['exp'] = datetime.utcnow() + timedelta(seconds=expires_in)
        
        payload['iat'] = datetime.utcnow()
        payload['jti'] = secrets.token_urlsafe(32)
        
        return jwt.encode(payload, secret_key, algorithm=algorithm)
    
    @staticmethod
    def verify_jwt_token(token: str, secret_key: str, algorithms: List[str] = ['HS256']) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload."""
        try:
            payload = jwt.decode(token, secret_key, algorithms=algorithms)
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    @staticmethod
    def generate_api_key(length: int = 32) -> str:
        """Generate secure API key."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def generate_session_token(length: int = 64) -> str:
        """Generate secure session token."""
        return secrets.token_hex(length)
    
    # Encryption/Decryption
    @staticmethod
    def derive_key(password: str, salt: bytes, iterations: int = 100000) -> bytes:
        """Derive encryption key from password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
        )
        return kdf.derive(password.encode())
    
    @staticmethod
    def encrypt_data(data: str, key: bytes) -> str:
        """Encrypt data using Fernet symmetric encryption."""
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(data.encode())
        return base64.b64encode(encrypted_data).decode()
    
    @staticmethod
    def decrypt_data(encrypted_data: str, key: bytes) -> str:
        """Decrypt data using Fernet symmetric encryption."""
        fernet = Fernet(key)
        decoded_data = base64.b64decode(encrypted_data.encode())
        decrypted_data = fernet.decrypt(decoded_data)
        return decrypted_data.decode()
    
    @staticmethod
    def generate_encryption_key() -> bytes:
        """Generate new encryption key."""
        return Fernet.generate_key()
    
    # Hashing utilities
    @staticmethod
    def hash_data(data: str, algorithm: str = 'sha256') -> str:
        """Hash data using specified algorithm."""
        if algorithm.lower() == 'sha256':
            return hashlib.sha256(data.encode()).hexdigest()
        elif algorithm.lower() == 'sha512':
            return hashlib.sha512(data.encode()).hexdigest()
        elif algorithm.lower() == 'md5':
            return hashlib.md5(data.encode()).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    @staticmethod
    def hash_file(file_path: str, algorithm: str = 'sha256', chunk_size: int = 8192) -> str:
        """Hash file contents using specified algorithm."""
        if algorithm.lower() == 'sha256':
            hash_func = hashlib.sha256()
        elif algorithm.lower() == 'sha512':
            hash_func = hashlib.sha512()
        elif algorithm.lower() == 'md5':
            hash_func = hashlib.md5()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    # Input validation and sanitization
    @staticmethod
    def sanitize_html(input_string: str) -> str:
        """Sanitize HTML input to prevent XSS."""
        import html
        return html.escape(input_string)
    
    @staticmethod
    def validate_sql_input(input_string: str) -> bool:
        """Check if input contains SQL injection patterns."""
        sql_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(--|#|/\*|\*/)",
            r"(\bOR\b.*=.*\bOR\b)",
            r"(\bAND\b.*=.*\bAND\b)",
            r"(['\"];?\s*(OR|AND)\s+.+=.+)",
            r"(\.\./|\.\.\\)",
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, input_string, re.IGNORECASE):
                return False
        
        return True
    
    @staticmethod
    def validate_email_format(email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone_number(phone: str, country_code: str = 'US') -> bool:
        """Validate phone number format."""
        if country_code.upper() == 'US':
            pattern = r'^\+?1[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})$'
            return bool(re.match(pattern, phone))
        else:
            # Basic international validation
            pattern = r'^\+[1-9]\d{1,14}$'
            return bool(re.match(pattern, phone))
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False
    
    @staticmethod
    def validate_ip_address(ip: str, version: str = 'both') -> bool:
        """Validate IP address format."""
        try:
            if version in ('ipv4', 'both'):
                ipaddress.IPv4Address(ip)
                return True
            if version in ('ipv6', 'both'):
                ipaddress.IPv6Address(ip)
                return True
            return False
        except ValueError:
            return False
    
    @staticmethod
    def validate_credit_card(card_number: str) -> bool:
        """Validate credit card number using Luhn algorithm."""
        # Remove spaces and dashes
        card_number = re.sub(r'[\s-]', '', card_number)
        
        # Check if it's numeric and has valid length
        if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
            return False
        
        # Luhn algorithm
        total = 0
        reverse_digits = map(int, reversed(card_number))
        
        for i, digit in enumerate(reverse_digits):
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        
        return total % 10 == 0
    
    # Rate limiting
    @staticmethod
    def generate_rate_limit_key(identifier: str, action: str, window: str) -> str:
        """Generate rate limit key."""
        return f"rate_limit:{identifier}:{action}:{window}"
    
    @staticmethod
    def is_rate_limited(current_count: int, limit: int) -> bool:
        """Check if rate limit is exceeded."""
        return current_count >= limit
    
    # Security headers
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get recommended security headers."""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
        }
    
    # CSRF protection
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate CSRF token."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_csrf_token(token: str, expected_token: str) -> bool:
        """Validate CSRF token."""
        return secrets.compare_digest(token, expected_token)
    
    # Secure random generation
    @staticmethod
    def generate_secure_id(length: int = 16) -> str:
        """Generate secure random ID."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def generate_uuid() -> str:
        """Generate UUID."""
        import uuid
        return str(uuid.uuid4())
    
    # Data masking
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email address for privacy."""
        if '@' not in email:
            return email
        
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        
        return f"{masked_local}@{domain}"
    
    @staticmethod
    def mask_phone_number(phone: str) -> str:
        """Mask phone number for privacy."""
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) <= 4:
            return '*' * len(phone)
        
        # Show last 4 digits
        masked_digits = '*' * (len(digits) - 4) + digits[-4:]
        
        # Reformat with original non-digit characters
        result = ''
        digit_index = 0
        for char in phone:
            if char.isdigit():
                if digit_index < len(masked_digits):
                    result += masked_digits[digit_index]
                    digit_index += 1
                else:
                    result += '*'
            else:
                result += char
        
        return result
    
    @staticmethod
    def mask_credit_card(card_number: str) -> str:
        """Mask credit card number showing only last 4 digits."""
        # Remove spaces and dashes
        clean_number = re.sub(r'[\s-]', '', card_number)
        
        if len(clean_number) <= 4:
            return '*' * len(card_number)
        
        # Show last 4 digits
        masked_number = '*' * (len(clean_number) - 4) + clean_number[-4:]
        
        # Reformat with original spacing
        if ' ' in card_number:
            # Insert spaces every 4 digits
            formatted = ''
            for i, char in enumerate(masked_number):
                if i > 0 and i % 4 == 0:
                    formatted += ' '
                formatted += char
            return formatted
        elif '-' in card_number:
            # Insert dashes at original positions
            formatted = ''
            dash_positions = [i for i, char in enumerate(card_number) if char == '-']
            masked_index = 0
            for i in range(len(card_number)):
                if i in dash_positions:
                    formatted += '-'
                else:
                    if masked_index < len(masked_number):
                        formatted += masked_number[masked_index]
                        masked_index += 1
            return formatted
        else:
            return masked_number
    
    # Security audit utilities
    @staticmethod
    def check_password_strength(password: str) -> Dict[str, Any]:
        """Check password strength and provide feedback."""
        feedback = {
            'score': 0,
            'issues': [],
            'suggestions': []
        }
        
        # Length check
        if len(password) < 8:
            feedback['issues'].append('Password is too short (minimum 8 characters)')
            feedback['suggestions'].append('Use a longer password')
        else:
            feedback['score'] += 1
        
        # Complexity checks
        if not re.search(r'[a-z]', password):
            feedback['issues'].append('Missing lowercase letters')
            feedback['suggestions'].append('Include lowercase letters')
        else:
            feedback['score'] += 1
        
        if not re.search(r'[A-Z]', password):
            feedback['issues'].append('Missing uppercase letters')
            feedback['suggestions'].append('Include uppercase letters')
        else:
            feedback['score'] += 1
        
        if not re.search(r'\d', password):
            feedback['issues'].append('Missing numbers')
            feedback['suggestions'].append('Include numbers')
        else:
            feedback['score'] += 1
        
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
            feedback['issues'].append('Missing special characters')
            feedback['suggestions'].append('Include special characters')
        else:
            feedback['score'] += 1
        
        # Common patterns
        if re.search(r'(.)\1{2,}', password):
            feedback['issues'].append('Contains repeated characters')
            feedback['suggestions'].append('Avoid repeated characters')
        
        if re.search(r'(012|123|234|345|456|567|678|789|890|987|876|765|654|543|432|321|210)', password):
            feedback['issues'].append('Contains sequential numbers')
            feedback['suggestions'].append('Avoid sequential numbers')
        
        # Overall strength
        if feedback['score'] >= 4:
            feedback['strength'] = 'strong'
        elif feedback['score'] >= 3:
            feedback['strength'] = 'medium'
        else:
            feedback['strength'] = 'weak'
        
        return feedback