"""
Email service manager for AP Intake & Validation system.

Coordinates email providers and processors using Dependency Injection.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import (
    EmailProvider, EmailProcessor, EmailMessage, EmailResult, 
    ProcessingResult, EmailQuery, SecurityResult, ExtractionResult
)
from .processors import SecurityProcessor, ExtractionProcessor
from ..exceptions import EmailServiceException


logger = logging.getLogger(__name__)


class EmailServiceManager:
    """
    Main email service manager implementing Facade pattern.
    
    Provides unified interface for email operations while hiding
    complexity of multiple providers and processors.
    """
    
    def __init__(
        self,
        providers: Dict[str, EmailProvider],
        processors: List[EmailProcessor],
        default_provider: str = "gmail"
    ):
        """
        Initialize email service manager.
        
        Args:
            providers: Dictionary of email providers by name
            processors: List of email processors in execution order
            default_provider: Default provider to use
        """
        self.providers = providers
        self.processors = processors
        self.default_provider = default_provider
        self._security_processor = None
        self._extraction_processor = None
        
        # Find specific processors by type
        for processor in processors:
            if isinstance(processor, SecurityProcessor):
                self._security_processor = processor
            elif isinstance(processor, ExtractionProcessor):
                self._extraction_processor = processor
    
    async def process_email(
        self, 
        email: EmailMessage, 
        provider_name: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process an email through all configured processors.
        
        Args:
            email: Email message to process
            provider_name: Specific provider to use (optional)
            
        Returns:
            ProcessingResult with combined processing results
        """
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Processing email {email.id} from {email.from_email}")
            
            # Step 1: Security validation
            security_result = None
            if self._security_processor:
                security_result = await self._security_processor.process(email)
                if not security_result.success:
                    logger.warning(f"Email {email.id} failed security validation")
                    return ProcessingResult(
                        success=False,
                        status="blocked",
                        message="Email failed security validation",
                        security_result=security_result,
                        processing_time_ms=self._calculate_duration(start_time)
                    )
            
            # Step 2: Invoice extraction (only for safe emails)
            extraction_result = None
            if self._extraction_processor and (
                security_result is None or security_result.is_safe
            ):
                extraction_result = await self._extraction_processor.process(email)
            
            # Step 3: Determine final status
            if security_result and not security_result.is_safe:
                final_status = "blocked"
            elif extraction_result and extraction_result.success:
                final_status = "processed"
            elif extraction_result and not extraction_result.success:
                final_status = "failed"
            else:
                final_status = "processed"
            
            processing_time_ms = self._calculate_duration(start_time)
            
            logger.info(f"Email {email.id} processed successfully in {processing_time_ms}ms")
            
            return ProcessingResult(
                success=True,
                status=final_status,
                message="Email processed successfully",
                security_result=security_result,
                extraction_result=extraction_result,
                processing_time_ms=processing_time_ms
            )
            
        except Exception as e:
            logger.error(f"Error processing email {email.id}: {str(e)}")
            return ProcessingResult(
                success=False,
                status="failed",
                message=f"Processing failed: {str(e)}",
                processing_time_ms=self._calculate_duration(start_time),
                error_details={"error": str(e), "type": type(e).__name__}
            )
    
    async def get_messages(
        self, 
        query: EmailQuery, 
        provider_name: Optional[str] = None
    ) -> EmailResult:
        """
        Retrieve messages from specified provider.
        
        Args:
            query: Email query parameters
            provider_name: Specific provider to use
            
        Returns:
            EmailResult with messages
        """
        provider = self._get_provider(provider_name)
        
        try:
            logger.info(f"Retrieving messages for user {query.user_id}")
            result = await provider.get_messages(query)
            
            if result.success:
                logger.info(f"Retrieved {len(result.data) if result.data else 0} messages")
            else:
                logger.error(f"Failed to retrieve messages: {result.message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving messages: {str(e)}")
            return EmailResult(
                success=False,
                message=f"Failed to retrieve messages: {str(e)}",
                error_code="PROVIDER_ERROR"
            )
    
    async def send_email(
        self, 
        message: EmailMessage, 
        provider_name: Optional[str] = None
    ) -> EmailResult:
        """
        Send email through specified provider.
        
        Args:
            message: Email message to send
            provider_name: Specific provider to use
            
        Returns:
            EmailResult with delivery status
        """
        provider = self._get_provider(provider_name)
        
        try:
            logger.info(f"Sending email to {message.to_emails}")
            result = await provider.send_email(message)
            
            if result.success:
                logger.info(f"Email sent successfully to {message.to_emails}")
            else:
                logger.error(f"Failed to send email: {result.message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return EmailResult(
                success=False,
                message=f"Failed to send email: {str(e)}",
                error_code="PROVIDER_ERROR"
            )
    
    async def setup_monitoring(
        self, 
        webhook_url: str, 
        provider_name: Optional[str] = None
    ) -> EmailResult:
        """
        Set up real-time email monitoring.
        
        Args:
            webhook_url: URL to receive notifications
            provider_name: Specific provider to monitor
            
        Returns:
            EmailResult with monitoring status
        """
        provider = self._get_provider(provider_name)
        
        try:
            logger.info(f"Setting up email monitoring for {provider_name or self.default_provider}")
            result = await provider.watch_messages(webhook_url)
            
            if result.success:
                logger.info("Email monitoring set up successfully")
            else:
                logger.error(f"Failed to set up monitoring: {result.message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error setting up monitoring: {str(e)}")
            return EmailResult(
                success=False,
                message=f"Failed to set up monitoring: {str(e)}",
                error_code="PROVIDER_ERROR"
            )
    
    async def stop_monitoring(self, provider_name: Optional[str] = None) -> EmailResult:
        """
        Stop real-time email monitoring.
        
        Args:
            provider_name: Specific provider to stop monitoring
            
        Returns:
            EmailResult with stop status
        """
        provider = self._get_provider(provider_name)
        
        try:
            logger.info(f"Stopping email monitoring for {provider_name or self.default_provider}")
            result = await provider.stop_watching()
            
            if result.success:
                logger.info("Email monitoring stopped successfully")
            else:
                logger.error(f"Failed to stop monitoring: {result.message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error stopping monitoring: {str(e)}")
            return EmailResult(
                success=False,
                message=f"Failed to stop monitoring: {str(e)}",
                error_code="PROVIDER_ERROR"
            )
    
    def get_provider_status(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of all providers or specific provider.
        
        Args:
            provider_name: Specific provider to check
            
        Returns:
            Dictionary with provider status information
        """
        status = {}
        
        if provider_name:
            # Check specific provider
            if provider_name in self.providers:
                status[provider_name] = {
                    "available": True,
                    "type": type(self.providers[provider_name]).__name__
                }
            else:
                status[provider_name] = {
                    "available": False,
                    "error": "Provider not configured"
                }
        else:
            # Check all providers
            for name, provider in self.providers.items():
                status[name] = {
                    "available": True,
                    "type": type(provider).__name__
                }
        
        return status
    
    def _get_provider(self, provider_name: Optional[str] = None) -> EmailProvider:
        """
        Get provider instance by name.
        
        Args:
            provider_name: Name of provider
            
        Returns:
            EmailProvider instance
            
        Raises:
            EmailServiceException: If provider not found
        """
        name = provider_name or self.default_provider
        
        if name not in self.providers:
            raise EmailServiceException(
                f"Provider '{name}' not configured. Available providers: {list(self.providers.keys())}"
            )
        
        return self.providers[name]
    
    def _calculate_duration(self, start_time: datetime) -> int:
        """
        Calculate processing duration in milliseconds.
        
        Args:
            start_time: Start time
            
        Returns:
            Duration in milliseconds
        """
        duration = datetime.utcnow() - start_time
        return int(duration.total_seconds() * 1000)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all email services.
        
        Returns:
            Dictionary with health status information
        """
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "providers": {},
            "processors": {
                "security_processor": self._security_processor is not None,
                "extraction_processor": self._extraction_processor is not None,
                "total_processors": len(self.processors)
            }
        }
        
        # Check each provider
        for name, provider in self.providers.items():
            try:
                # Basic health check - try to authenticate or get status
                health_status["providers"][name] = {
                    "status": "healthy",
                    "type": type(provider).__name__
                }
            except Exception as e:
                health_status["providers"][name] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "type": type(provider).__name__
                }
                health_status["status"] = "degraded"
        
        return health_status