"""
Executor Agent for Invoice Execution.

Executes approved invoices:
- QuickBooks API integration
- ERP system updates
- Payment scheduling
"""

from typing import Any, Dict, Optional
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = structlog.get_logger()


class ExecutorAgent:
    """
    Executes approved invoices.
    
    Integrations:
    - QuickBooks Online (create bills)
    - SAP/Oracle (create POs)
    - Payment systems (schedule payments)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize executor.
        
        Args:
            config: Configuration with QuickBooks credentials
        """
        self.config = config or {}
        self.quickbooks_client_id = config.get("quickbooks_client_id")
        self.quickbooks_client_secret = config.get("quickbooks_client_secret")
        self.quickbooks_base_url = config.get(
            "quickbooks_base_url",
            "https://quickbooks.api.intuit.com/v3",
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def execute(
        self,
        extracted: Any,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Execute approved invoice.
        
        Args:
            extracted: Extracted invoice data
            tenant_id: Tenant identifier
            
        Returns:
            Execution result with bill_id
        """
        try:
            # Create QuickBooks bill
            bill_result = await self._create_quickbooks_bill(extracted, tenant_id)
            
            logger.info(
                "invoice_executed",
                invoice_id=extracted.invoice_id,
                quickbooks_bill_id=bill_result["bill_id"],
            )
            
            return {
                "bill_id": bill_result["bill_id"],
                "status": "success",
                "quickbooks_response": bill_result.get("response"),
            }
            
        except Exception as e:
            logger.error("execution_failed", error=str(e))
            raise
    
    async def _create_quickbooks_bill(
        self,
        extracted: Any,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Create bill in QuickBooks Online.
        
        Args:
            extracted: Extracted invoice data
            tenant_id: Tenant identifier
            
        Returns:
            Bill creation result
        """
        import httpx
        
        # Build QuickBooks bill payload
        bill_payload = self._build_bill_payload(extracted, tenant_id)
        
        # Mock mode for development (uses Mockoon)
        if self.config.get("mock_mode", True):
            return {
                "bill_id": f"mock-bill-{extracted.invoice_id}",
                "response": {"mock": True},
            }
        
        # Production mode
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.quickbooks_base_url}/company/{tenant_id}/bill",
                json=bill_payload,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "bill_id": result["Bill"]["Id"],
                "response": result,
            }
    
    def _build_bill_payload(self, extracted: Any, tenant_id: str) -> Dict[str, Any]:
        """Build QuickBooks bill payload."""
        return {
            "VendorRef": {
                "value": extracted.vendor.name,
            },
            "Line": [
                {
                    "Description": item.description,
                    "Amount": item.total,
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "AccountBasedExpenseLineDetail": {
                        "Qty": item.quantity,
                        "UnitPrice": item.unit_price,
                    },
                }
                for item in extracted.line_items
            ],
            "TotalAmt": extracted.total_amount,
            "BillEmail": {
                "Address": extracted.vendor.email or "billing@vendor.com",
            },
            "DocNumber": extracted.invoice_number,
            "TxnDate": extracted.invoice_date,
            "DueDate": extracted.due_date or extracted.invoice_date,
        }
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get QuickBooks OAuth headers."""
        # Placeholder - needs OAuth token management
        return {
            "Authorization": "Bearer mock_token",
            "Content-Type": "application/json",
        }
