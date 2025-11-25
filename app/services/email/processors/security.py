"""
Security processor for email validation and threat detection.

Implements security validation following Single Responsibility Principle.
"""

import logging
import re
from typing import List, Dict, Any, Set
from urllib.parse import urlparse

from ..base import EmailProcessor, EmailMessage, ProcessingResult, SecurityResult, SecurityFlag


logger = logging.getLogger(__name__)


class SecurityProcessor(EmailProcessor):
    """
    Email security validation processor.
    
    Validates emails for security threats using configurable rules.
    """
    
    def __init__(
        self,
        trusted_domains: List[str] = None,
        blocked_domains: List[str] = None,
        max_urls: int = 10,
        max_attachments: int = 10,
        max_attachment_size_mb: int = 25
    ):
        """
        Initialize security processor.
        
        Args:
            trusted_domains: List of trusted sender domains
            blocked_domains: List of blocked sender domains
            max_urls: Maximum allowed URLs in email
            max_attachments: Maximum allowed attachments
            max_attachment_size_mb: Maximum attachment size in MB
        """
        self.trusted_domains = set(trusted_domains or [])
        self.blocked_domains = set(blocked_domains or [])
        self.max_urls = max_urls
        self.max_attachments = max_attachments
        self.max_attachment_size_mb = max_attachment_size_mb
        
        # Security patterns for detection
        self.malicious_patterns = [
            r'click\s+here\s+immediately',
            r'urgent\s+action\s+required',
            r'account\s+suspended',
            r'verify\s+your\s+account',
            r'winner\s+notification',
            r'congratulations\s+you\s+won',
            r'limited\s+time\s+offer',
            r'act\s+now\s+or\s+lose',
        ]
        
        # Suspicious file extensions
        self.suspicious_extensions = {
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr',
            '.vbs', '.js', '.jar', '.app', '.deb', '.pkg',
            '.dmg', '.iso', '.img', '.msi', '.msp', '.msm'
        }
        
        logger.info(f"SecurityProcessor initialized with {len(self.trusted_domains)} trusted domains")
    
    async def process(self, email: EmailMessage) -> ProcessingResult:
        """
        Process email for security validation.
        
        Args:
            email: Email message to validate
            
        Returns:
            ProcessingResult with security validation
        """
        try:
            logger.info(f"Performing security validation on email {email.id}")
            
            security_result = await self._validate_email(email)
            
            return ProcessingResult(
                success=True,
                status="processed",
                message="Security validation completed",
                security_result=security_result
            )
            
        except Exception as e:
            logger.error(f"Error in security validation: {str(e)}")
            return ProcessingResult(
                success=False,
                status="failed",
                message=f"Security validation failed: {str(e)}",
                error_details={"error": str(e), "type": type(e).__name__}
            )
    
    def can_handle(self, email: EmailMessage) -> bool:
        """
        Check if processor can handle the email.
        
        Args:
            email: Email message to check
            
        Returns:
            True if processor can handle the email
        """
        # Security processor can handle all emails
        return True
    
    async def _validate_email(self, email: EmailMessage) -> SecurityResult:
        """
        Perform comprehensive security validation.
        
        Args:
            email: Email message to validate
            
        Returns:
            SecurityResult with validation details
        """
        flags = []
        security_score = 100
        details = {}
        
        # 1. Sender domain validation
        domain_score, domain_flags, domain_details = self._validate_sender(email.from_email)
        security_score += domain_score
        flags.extend(domain_flags)
        details.update(domain_details)
        
        # 2. Content validation
        content_score, content_flags, content_details = self._validate_content(email)
        security_score += content_score
        flags.extend(content_flags)
        details.update(content_details)
        
        # 3. Attachment validation
        attachment_score, attachment_flags, attachment_details = self._validate_attachments(email)
        security_score += attachment_score
        flags.extend(attachment_flags)
        details.update(attachment_details)
        
        # 4. URL validation
        url_score, url_flags, url_details = self._validate_urls(email)
        security_score += url_score
        flags.extend(url_flags)
        details.update(url_details)
        
        # Determine if email is safe
        is_safe = (
            security_score >= 70 and  # Minimum score threshold
            SecurityFlag.MALICIOUS_PATTERN not in flags and
            SecurityFlag.UNTRUSTED_SENDER not in flags
        )
        
        blocked_reason = None
        if not is_safe:
            if SecurityFlag.UNTRUSTED_SENDER in flags:
                blocked_reason = "Sender domain not trusted"
            elif SecurityFlag.MALICIOUS_PATTERN in flags:
                blocked_reason = "Malicious content detected"
            elif SecurityFlag.EXCESSIVE_ATTACHMENTS in flags:
                blocked_reason = "Too many attachments"
            elif SecurityFlag.EXCESSIVE_URLS in flags:
                blocked_reason = "Too many URLs"
        
        logger.info(f"Security validation completed. Score: {security_score}, Safe: {is_safe}")
        
        return SecurityResult(
            is_safe=is_safe,
            security_score=max(0, min(100, security_score)),
            flags=flags,
            details=details,
            blocked_reason=blocked_reason
        )
    
    def _validate_sender(self, email: str) -> tuple[int, List[SecurityFlag], Dict[str, Any]]:
        """
        Validate sender email address.
        
        Args:
            email: Sender email address
            
        Returns:
            Tuple of (score, flags, details)
        """
        flags = []
        score = 0
        details = {}
        
        try:
            # Extract domain
            domain = email.split('@')[-1].lower() if '@' in email else ''
            
            details['sender_domain'] = domain
            details['sender_email'] = email
            
            # Check blocked domains
            if domain in self.blocked_domains:
                flags.append(SecurityFlag.UNTRUSTED_SENDER)
                score -= 50
                details['domain_status'] = 'blocked'
            
            # Check trusted domains
            elif domain in self.trusted_domains:
                score += 10
                details['domain_status'] = 'trusted'
            
            # Check for suspicious patterns in email
            elif self._is_suspicious_email(email):
                flags.append(SecurityFlag.SUSPICIOUS_CONTENT)
                score -= 15
                details['domain_status'] = 'suspicious'
            
            else:
                details['domain_status'] = 'unknown'
        
        except Exception as e:
            logger.warning(f"Error validating sender: {str(e)}")
            score -= 5
        
        return score, flags, details
    
    def _validate_content(self, email: EmailMessage) -> tuple[int, List[SecurityFlag], Dict[str, Any]]:
        """
        Validate email content for malicious patterns.
        
        Args:
            email: Email message to validate
            
        Returns:
            Tuple of (score, flags, details)
        """
        flags = []
        score = 0
        details = {}
        
        content_to_check = []
        
        # Collect all text content
        if email.subject:
            content_to_check.append(email.subject.lower())
        if email.body_text:
            content_to_check.append(email.body_text.lower())
        if email.body_html:
            # Remove HTML tags for content checking
            import re
            clean_html = re.sub(r'<[^>]+>', '', email.body_html.lower())
            content_to_check.append(clean_html)
        
        details['content_length'] = sum(len(content) for content in content_to_check)
        
        # Check for malicious patterns
        for content in content_to_check:
            for pattern in self.malicious_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    flags.append(SecurityFlag.MALICIOUS_PATTERN)
                    score -= 25
                    details['malicious_pattern'] = pattern
                    break
        
        # Check for excessive capitalization (common in spam)
        if email.subject:
            caps_ratio = sum(1 for c in email.subject if c.isupper()) / len(email.subject)
            if caps_ratio > 0.5:  # More than 50% caps
                flags.append(SecurityFlag.SUSPICIOUS_CONTENT)
                score -= 10
                details['excessive_caps'] = caps_ratio
        
        return score, flags, details
    
    def _validate_attachments(self, email: EmailMessage) -> tuple[int, List[SecurityFlag], Dict[str, Any]]:
        """
        Validate email attachments.
        
        Args:
            email: Email message to validate
            
        Returns:
            Tuple of (score, flags, details)
        """
        flags = []
        score = 0
        details = {}
        
        if not email.attachments:
            details['attachment_count'] = 0
            return score, flags, details
        
        attachment_count = len(email.attachments)
        details['attachment_count'] = attachment_count
        
        # Check attachment count
        if attachment_count > self.max_attachments:
            flags.append(SecurityFlag.EXCESSIVE_ATTACHMENTS)
            score -= 20
            details['attachment_limit_exceeded'] = True
        
        # Check each attachment
        suspicious_files = []
        large_files = []
        total_size = 0
        
        for attachment in email.attachments:
            # Check file extension
            filename_lower = attachment.filename.lower()
            has_suspicious_ext = any(
                filename_lower.endswith(ext) for ext in self.suspicious_extensions
            )
            
            if has_suspicious_ext:
                suspicious_files.append(attachment.filename)
                score -= 15
            
            # Check file size
            size_mb = attachment.size_bytes / (1024 * 1024)
            total_size += size_mb
            
            if size_mb > self.max_attachment_size_mb:
                large_files.append(attachment.filename)
                score -= 10
        
        if suspicious_files:
            flags.append(SecurityFlag.SUSPICIOUS_CONTENT)
            details['suspicious_files'] = suspicious_files
        
        if large_files:
            flags.append(SecurityFlag.SUSPICIOUS_CONTENT)
            details['large_files'] = large_files
        
        details['total_attachment_size_mb'] = total_size
        
        return score, flags, details
    
    def _validate_urls(self, email: EmailMessage) -> tuple[int, List[SecurityFlag], Dict[str, Any]]:
        """
        Validate URLs in email content.
        
        Args:
            email: Email message to validate
            
        Returns:
            Tuple of (score, flags, details)
        """
        flags = []
        score = 0
        details = {}
        
        # Extract URLs from content
        content_to_check = []
        if email.body_text:
            content_to_check.append(email.body_text)
        if email.body_html:
            content_to_check.append(email.body_html)
        
        url_pattern = r'https?://[^\s<>"\'\)]+'
        urls = []
        
        for content in content_to_check:
            found_urls = re.findall(url_pattern, content, re.IGNORECASE)
            urls.extend(found_urls)
        
        details['url_count'] = len(urls)
        details['urls'] = urls[:10]  # Limit to first 10 URLs
        
        # Check URL count
        if len(urls) > self.max_urls:
            flags.append(SecurityFlag.EXCESSIVE_URLS)
            score -= 15
            details['url_limit_exceeded'] = True
        
        # Check for suspicious URLs
        suspicious_urls = []
        for url in urls:
            if self._is_suspicious_url(url):
                suspicious_urls.append(url)
                score -= 5
        
        if suspicious_urls:
            flags.append(SecurityFlag.SUSPICIOUS_CONTENT)
            details['suspicious_urls'] = suspicious_urls
        
        return score, flags, details
    
    def _is_suspicious_email(self, email: str) -> bool:
        """
        Check if email address looks suspicious.
        
        Args:
            email: Email address to check
            
        Returns:
            True if email looks suspicious
        """
        # Check for common suspicious patterns
        suspicious_patterns = [
            r'[0-9]{4,}@',  # Numbers before @
            r'[a-z]{1,2}[0-9]{3,}@',  # Letter + numbers
            r'no-reply',  # Generic no-reply
            r'admin\d*@",  # Admin with numbers
            r'support\d*@",  # Support with numbers
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, email, re.IGNORECASE):
                return True
        
        return False
    
    def _is_suspicious_url(self, url: str) -> bool:
        """
        Check if URL looks suspicious.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL looks suspicious
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Check for URL shorteners (often used in phishing)
            shorteners = {
                'bit.ly', 'tinyurl.com', 't.co', 'goo.gl',
                'ow.ly', 'is.gd', 'buff.ly', 'adf.ly'
            }
            
            if domain in shorteners:
                return True
            
            # Check for IP addresses instead of domains
            import re
            ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'
            if re.match(ip_pattern, domain):
                return True
            
            # Check for suspicious TLDs
            suspicious_tlds = ['.tk', '.ml', '.ga', '.cf']
            if any(domain.endswith(tld) for tld in suspicious_tlds):
                return True
        
        except Exception:
            pass
        
        return False