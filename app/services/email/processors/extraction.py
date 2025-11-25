"""
Invoice extraction processor for email attachments.

Implements invoice data extraction using document processing services.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..base import EmailProcessor, EmailMessage, ProcessingResult, ExtractionResult


logger = logging.getLogger(__name__)


class ExtractionProcessor(EmailProcessor):
    """
    Invoice extraction processor.
    
    Extracts invoice data from PDF attachments using document processing.
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.85,
        supported_formats: List[str] = None,
        max_file_size_mb: int = 25
    ):
        """
        Initialize extraction processor.
        
        Args:
            confidence_threshold: Minimum confidence for successful extraction
            supported_formats: List of supported file formats
            max_file_size_mb: Maximum file size for processing
        """
        self.confidence_threshold = confidence_threshold
        self.supported_formats = supported_formats or ['pdf']
        self.max_file_size_mb = max_file_size_mb
        
        logger.info(f"ExtractionProcessor initialized with threshold {confidence_threshold}")
    
    async def process(self, email: EmailMessage) -> ProcessingResult:
        """
        Process email attachments for invoice extraction.
        
        Args:
            email: Email message with attachments
            
        Returns:
            ProcessingResult with extraction results
        """
        try:
            logger.info(f"Processing invoice extraction for email {email.id}")
            
            if not email.attachments:
                return ProcessingResult(
                    success=True,
                    status="processed",
                    message="No attachments to process",
                    extraction_result=ExtractionResult(
                        success=False,
                        confidence=0.0,
                        error_message="No attachments found"
                    )
                )
            
            # Process each attachment
            extraction_results = []
            for attachment in email.attachments:
                if self._can_process_attachment(attachment):
                    result = await self._extract_from_attachment(attachment)
                    extraction_results.append(result)
                else:
                    logger.info(f"Skipping attachment {attachment.filename} - unsupported format")
                    extraction_results.append(ExtractionResult(
                        success=False,
                        confidence=0.0,
                        error_message=f"Unsupported format: {attachment.content_type}"
                    ))
            
            # Find best extraction result
            best_result = self._find_best_extraction(extraction_results)
            
            return ProcessingResult(
                success=True,
                status="processed",
                message=f"Processed {len(extraction_results)} attachments",
                extraction_result=best_result
            )
            
        except Exception as e:
            logger.error(f"Error in invoice extraction: {str(e)}")
            return ProcessingResult(
                success=False,
                status="failed",
                message=f"Extraction failed: {str(e)}",
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
        # Can handle emails with attachments
        return bool(email.attachments)
    
    def _can_process_attachment(self, attachment) -> bool:
        """
        Check if attachment can be processed.
        
        Args:
            attachment: Email attachment to check
            
        Returns:
            True if attachment can be processed
        """
        # Check file format
        if not self._is_supported_format(attachment):
            return False
        
        # Check file size
        size_mb = attachment.size_bytes / (1024 * 1024)
        if size_mb > self.max_file_size_mb:
            logger.warning(f"Attachment {attachment.filename} too large: {size_mb}MB")
            return False
        
        # Check if it's likely an invoice (PDF with invoice-like filename)
        if not self._is_likely_invoice(attachment):
            return False
        
        return True
    
    def _is_supported_format(self, attachment) -> bool:
        """
        Check if attachment format is supported.
        
        Args:
            attachment: Email attachment to check
            
        Returns:
            True if format is supported
        """
        content_type = attachment.content_type.lower()
        filename = attachment.filename.lower()
        
        # Check content type
        for format_type in self.supported_formats:
            if format_type in content_type or format_type in filename:
                return True
        
        # Common PDF content types
        pdf_types = [
            'application/pdf',
            'application/x-pdf',
            'application/x-bzpdf',
            'application/x-gzpdf'
        ]
        
        return content_type in pdf_types
    
    def _is_likely_invoice(self, attachment) -> bool:
        """
        Check if attachment is likely an invoice based on filename.
        
        Args:
            attachment: Email attachment to check
            
        Returns:
            True if attachment is likely an invoice
        """
        filename = attachment.filename.lower()
        
        # Common invoice keywords in filename
        invoice_keywords = [
            'invoice', 'inv', 'bill', 'receipt', 'statement',
            'purchase', 'order', 'po', 'payment', 'due'
        ]
        
        # Check if filename contains invoice keywords
        for keyword in invoice_keywords:
            if keyword in filename:
                return True
        
        # Check for common invoice patterns
        import re
        invoice_patterns = [
            r'\d{4,}-\d{2,}-\d{2,}',  # Date pattern
            r'inv\d+',  # INV followed by numbers
            r'bill\d+',  # BILL followed by numbers
            r'po\d+',   # PO followed by numbers
        ]
        
        for pattern in invoice_patterns:
            if re.search(pattern, filename):
                return True
        
        # Default to True for PDFs (most business PDFs are invoices)
        return attachment.is_pdf
    
    async def _extract_from_attachment(self, attachment) -> ExtractionResult:
        """
        Extract invoice data from attachment.
        
        Args:
            attachment: Email attachment to process
            
        Returns:
            ExtractionResult with extracted data
        """
        try:
            logger.info(f"Extracting invoice data from {attachment.filename}")
            
            # Use document processing service (placeholder for now)
            # TODO: Integrate with actual document processing service
            extracted_data = await self._process_document(attachment)
            
            if extracted_data:
                return ExtractionResult(
                    success=True,
                    confidence=extracted_data.get('confidence', 0.0),
                    vendor_name=extracted_data.get('vendor_name'),
                    invoice_date=extracted_data.get('invoice_date'),
                    invoice_amount=extracted_data.get('invoice_amount'),
                    extracted_data=extracted_data
                )
            else:
                return ExtractionResult(
                    success=False,
                    confidence=0.0,
                    error_message="No invoice data extracted"
                )
        
        except Exception as e:
            logger.error(f"Error extracting from {attachment.filename}: {str(e)}")
            return ExtractionResult(
                success=False,
                confidence=0.0,
                error_message=f"Extraction error: {str(e)}"
            )
    
    async def _process_document(self, attachment) -> Optional[Dict[str, Any]]:
        """
        Process document using document processing service.
        
        Args:
            attachment: Email attachment to process
            
        Returns:
            Extracted data dictionary or None
        """
        # Placeholder implementation
        # TODO: Replace with actual document processing service integration
        
        # Simulate extraction based on filename patterns
        filename = attachment.filename.lower()
        
        # Extract potential vendor name from filename
        vendor_name = self._extract_vendor_from_filename(filename)
        
        # Extract potential date from filename
        invoice_date = self._extract_date_from_filename(filename)
        
        # Extract potential amount from filename
        invoice_amount = self._extract_amount_from_filename(filename)
        
        # Simulate confidence based on filename quality
        confidence = 0.7  # Base confidence
        if vendor_name:
            confidence += 0.1
        if invoice_date:
            confidence += 0.1
        if invoice_amount:
            confidence += 0.1
        
        extracted_data = {
            'vendor_name': vendor_name,
            'invoice_date': invoice_date,
            'invoice_amount': invoice_amount,
            'confidence': min(confidence, 1.0),
            'extraction_method': 'filename_pattern',
            'filename': attachment.filename,
            'file_size': attachment.size_bytes,
            'content_type': attachment.content_type
        }
        
        # Only return data if confidence meets threshold
        if confidence >= self.confidence_threshold:
            return extracted_data
        
        return None
    
    def _extract_vendor_from_filename(self, filename: str) -> Optional[str]:
        """
        Extract vendor name from filename.
        
        Args:
            filename: Filename to analyze
            
        Returns:
            Vendor name or None
        """
        # Remove common prefixes and suffixes
        import re
        
        # Remove file extension
        name_without_ext = re.sub(r'\.[^.]+$', '', filename)
        
        # Remove common invoice prefixes
        prefixes_to_remove = [
            r'^invoice[_\s-]*',
            r'^inv[_\s-]*',
            r'^bill[_\s-]*',
            r'^receipt[_\s-]*',
            r'^po[_\s-]*',
            r'^purchase[_\s-]*',
            r'\d{4,}[_\s-]*',  # Remove dates at start
            r'\d+[_\s-]*',      # Remove numbers at start
        ]
        
        for prefix in prefixes_to_remove:
            name_without_ext = re.sub(prefix, '', name_without_ext, flags=re.IGNORECASE)
        
        # Remove common suffixes
        suffixes_to_remove = [
            r'[_\s-]*invoice?$',
            r'[_\s-]*bill?$',
            r'[_\s-]*receipt?$',
            r'[_\s-]*po?$',
            r'[_\s-]*\d{4,}$',  # Remove dates at end
            r'[_\s-]*v\d+$',     # Remove version numbers
        ]
        
        for suffix in suffixes_to_remove:
            name_without_ext = re.sub(suffix, '', name_without_ext, flags=re.IGNORECASE)
        
        # Clean up remaining name
        vendor_name = name_without_ext.strip(' _-')
        
        # Return if we have a reasonable vendor name
        if len(vendor_name) >= 3 and len(vendor_name) <= 50:
            return vendor_name.title()
        
        return None
    
    def _extract_date_from_filename(self, filename: str) -> Optional[datetime]:
        """
        Extract invoice date from filename.
        
        Args:
            filename: Filename to analyze
            
        Returns:
            Datetime object or None
        """
        import re
        from datetime import datetime
        
        # Look for date patterns
        date_patterns = [
            r'(\d{4,})[-_](\d{1,2})[-_](\d{1,2})',  # YYYY-MM-DD
            r'(\d{1,2})[-_](\d{1,2})[-_](\d{4,})',  # MM-DD-YYYY
            r'(\d{4,})(\d{2,})(\d{2,)',           # YYYYMMDD
            r'(\d{2,})(\d{2,})(\d{4,})',           # MMDDYYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    groups = match.groups()
                    
                    # Try different date format interpretations
                    if len(groups) == 3:
                        # Check if first group is year (4 digits)
                        if len(groups[0]) == 4:
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        else:
                            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        
                        # Validate date
                        if 1 <= month <= 12 and 1 <= day <= 31:
                            return datetime(year, month, day)
                
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _extract_amount_from_filename(self, filename: str) -> Optional[float]:
        """
        Extract invoice amount from filename.
        
        Args:
            filename: Filename to analyze
            
        Returns:
            Amount as float or None
        """
        import re
        
        # Look for amount patterns
        amount_patterns = [
            r'[$€£¥]\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Currency symbol
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*[$€£¥]',  # Currency symbol after
            r'amount[_\s-]*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # "amount" prefix
            r'total[_\s-]*(\d+(?:,\d{3})*(?:\.\d{2})?)',   # "total" prefix
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1)
                    # Remove commas and convert to float
                    amount = float(amount_str.replace(',', ''))
                    
                    # Validate amount range
                    if 0 < amount < 1000000:  # Reasonable invoice amount range
                        return amount
                
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _find_best_extraction(self, results: List[ExtractionResult]) -> ExtractionResult:
        """
        Find the best extraction result from multiple results.
        
        Args:
            results: List of extraction results
            
        Returns:
            Best extraction result
        """
        if not results:
            return ExtractionResult(
                success=False,
                confidence=0.0,
                error_message="No extraction results"
            )
        
        # Filter successful results
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            return ExtractionResult(
                success=False,
                confidence=0.0,
                error_message="No successful extractions"
            )
        
        # Return result with highest confidence
        best_result = max(successful_results, key=lambda r: r.confidence)
        
        logger.info(f"Best extraction: confidence={best_result.confidence}, vendor={best_result.vendor_name}")
        
        return best_result