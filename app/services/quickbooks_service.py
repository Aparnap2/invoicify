"""
QuickBooks Online API integration service using python-quickbooks library with OAuth 2.0.

This service handles:
- OAuth 2.0 authentication with QuickBooks Online using intuitlib
- Invoice data mapping and export using python-quickbooks
- Vendor and account management
- Webhook handling for status updates
- Error handling and retry logic
- Batch operations support
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import httpx
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects import Bill, Vendor, Account, PurchaseOrder
from quickbooks.exceptions import QuickbooksException, AuthorizationException

from app.core.config import settings
from app.core.exceptions import ExportException, ValidationException

logger = logging.getLogger(__name__)


class QuickBooksServiceException(Exception):
    """Base exception for QuickBooks service errors."""
    pass


class QuickBooksAuthException(QuickBooksServiceException):
    """Exception for QuickBooks authentication errors."""
    pass


class QuickBooksAPIException(QuickBooksServiceException):
    """Exception for QuickBooks API errors."""
    pass


class QuickBooksService:
    """Service for integrating with QuickBooks Online API using python-quickbooks."""

    def __init__(self):
        """Initialize the QuickBooks service."""
        self.client_id = settings.QUICKBOOKS_SANDBOX_CLIENT_ID
        self.client_secret = settings.QUICKBOOKS_SANDBOX_CLIENT_SECRET
        self.redirect_uri = settings.QUICKBOOKS_REDIRECT_URI
        self.environment = settings.QUICKBOOKS_ENVIRONMENT

        if not self.client_id or not self.client_secret:
            raise QuickBooksServiceException("QuickBooks credentials not configured")

        # Initialize AuthClient for OAuth 2.0
        self.auth_client = AuthClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment=self.environment,
        )

        # HTTP client for additional requests
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )

        # OAuth state cache (in production, use Redis)
        self._oauth_state_cache = {}

        # Rate limiting - QuickBooks allows 500 requests per minute per app
        self.rate_limit_calls = 500
        self.rate_limit_window = 60
        self._rate_limit_tracker = []

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.http_client.aclose()

    def _generate_state(self) -> str:
        """Generate a secure state parameter for OAuth flow."""
        return secrets.token_urlsafe(32)

    async def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate QuickBooks OAuth 2.0 authorization URL using python-quickbooks library.

        Returns:
            Tuple of (authorization_url, state)
        """
        logger.info("Generating QuickBooks authorization URL")

        # Generate state for CSRF protection
        state = self._generate_state()

        # Store state temporarily (in production, use Redis with expiration)
        self._oauth_state_cache[state] = {
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=10)
        }

        # Get authorization URL from intuitlib
        scopes = [
            Scopes.ACCOUNTING,
            Scopes.ADDRESS,
            Scopes.EMAIL,
            Scopes.OPENID,
            Scopes.PHONE,
            Scopes.PROFILE
        ]

        auth_url = self.auth_client.get_authorization_url(scopes, state=state)

        logger.info(f"Generated authorization URL with state: {state}")
        return auth_url, state

    async def exchange_code_for_tokens(self, code: str, state: str, realm_id: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from QuickBooks
            state: State parameter from authorization request
            realm_id: QuickBooks company ID

        Returns:
            Token response with access_token, refresh_token, etc.
        """
        logger.info(f"Exchanging authorization code for tokens with state: {state}")

        # Validate state
        if state not in self._oauth_state_cache:
            raise QuickBooksAuthException("Invalid or expired state parameter")

        state_data = self._oauth_state_cache[state]
        if datetime.utcnow() > state_data["expires_at"]:
            del self._oauth_state_cache[state]
            raise QuickBooksAuthException("State parameter expired")

        try:
            # Exchange code for tokens using intuitlib
            response = self.auth_client.get_bearer_access_token(code, realm_id=realm_id)

            # Clean up state
            del self._oauth_state_cache[state]

            # Prepare token response
            token_response = {
                "access_token": self.auth_client.access_token,
                "refresh_token": self.auth_client.refresh_token,
                "expires_in": self.auth_client.expires_in,
                "refresh_token_expires_in": self.auth_client.refresh_token_expires_in,
                "id_token": getattr(self.auth_client, 'id_token', None),
                "realm_id": realm_id,
                "token_type": "Bearer"
            }

            logger.info("Successfully exchanged authorization code for tokens")
            return token_response

        except Exception as e:
            logger.error(f"Token exchange failed: {str(e)}")
            raise QuickBooksAuthException(f"Token exchange failed: {str(e)}")

    async def refresh_access_token(self, refresh_token: str, realm_id: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token from previous token exchange
            realm_id: QuickBooks company ID

        Returns:
            New token response
        """
        logger.info("Refreshing QuickBooks access token")

        try:
            # Set refresh token
            self.auth_client.refresh_token = refresh_token

            # Refresh tokens
            self.auth_client.refresh_access_token(realm_id=realm_id)

            token_response = {
                "access_token": self.auth_client.access_token,
                "refresh_token": self.auth_client.refresh_token,
                "expires_in": self.auth_client.expires_in,
                "refresh_token_expires_in": self.auth_client.refresh_token_expires_in,
                "realm_id": realm_id,
                "token_type": "Bearer"
            }

            logger.info("Successfully refreshed access token")
            return token_response

        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            raise QuickBooksAuthException(f"Token refresh failed: {str(e)}")

    def get_quickbooks_client(self, access_token: str, realm_id: str) -> QuickBooks:
        """
        Create a QuickBooks client instance.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID

        Returns:
            QuickBooks client instance
        """
        try:
            client = QuickBooks(
                client_id=self.client_id,
                client_secret=self.client_secret,
                access_token=access_token,
                refresh_token=None,  # Not needed for single operations
                company_id=realm_id,
                environment=self.environment,
                minorversion=63,  # Latest minor version
            )
            return client
        except Exception as e:
            logger.error(f"Failed to create QuickBooks client: {str(e)}")
            raise QuickBooksAPIException(f"Failed to create QuickBooks client: {str(e)}")

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information using the QuickBooks API.

        Args:
            access_token: Valid access token

        Returns:
            User information
        """
        logger.info("Fetching QuickBooks user info")

        try:
            # Use the auth client to get user info
            user_info = self.auth_client.get_user_info(access_token)
            logger.info("Successfully retrieved user info")
            return user_info

        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise QuickBooksAuthException(f"Failed to get user info: {str(e)}")

    async def get_company_info(self, access_token: str, realm_id: str) -> Dict[str, Any]:
        """
        Get company information for a QuickBooks realm.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID

        Returns:
            Company information
        """
        logger.info(f"Fetching company info for realm: {realm_id}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Query company info
            company_info = client.get_company_info()

            logger.info("Successfully retrieved company info")
            return company_info

        except Exception as e:
            logger.error(f"Failed to get company info: {str(e)}")
            raise QuickBooksAPIException(f"Failed to get company info: {str(e)}")

    async def create_or_update_vendor(
        self,
        access_token: str,
        realm_id: str,
        vendor_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create or update a vendor in QuickBooks using python-quickbooks library.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID
            vendor_data: Vendor information

        Returns:
            Created/updated vendor data
        """
        logger.info(f"Creating/updating vendor: {vendor_data.get('DisplayName', 'Unknown')}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Check if vendor already exists
            existing_vendor = await self._find_vendor_by_name(client, vendor_data.get("DisplayName", ""))

            if existing_vendor:
                return await self._update_vendor(client, existing_vendor, vendor_data)
            else:
                return await self._create_vendor(client, vendor_data)

        except Exception as e:
            logger.error(f"Failed to create/update vendor: {str(e)}")
            raise QuickBooksAPIException(f"Failed to create/update vendor: {str(e)}")

    async def _find_vendor_by_name(
        self,
        client: QuickBooks,
        vendor_name: str
    ) -> Optional[Vendor]:
        """Find a vendor by display name using python-quickbooks."""
        try:
            vendors = Vendor.query(
                "select * from Vendor where DisplayName = '%s'" % vendor_name,
                qb=client
            )
            return vendors[0] if vendors else None
        except Exception as e:
            logger.warning(f"Error searching for vendor {vendor_name}: {str(e)}")
            return None

    async def _create_vendor(
        self,
        client: QuickBooks,
        vendor_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new vendor using python-quickbooks."""
        vendor = Vendor()
        vendor.DisplayName = vendor_data["DisplayName"]
        vendor.GivenName = vendor_data.get("GivenName", "")
        vendor.FamilyName = vendor_data.get("FamilyName", "")
        vendor.CompanyName = vendor_data.get("CompanyName", "")
        vendor.PrintOnCheckName = vendor_data.get("PrintOnCheckName", vendor_data["DisplayName"])
        vendor.Active = True

        # Add optional fields
        if "PrimaryEmailAddr" in vendor_data:
            vendor.PrimaryEmailAddr = vendor_data["PrimaryEmailAddr"]
        if "PrimaryPhone" in vendor_data:
            vendor.PrimaryPhone = vendor_data["PrimaryPhone"]
        if "BillAddr" in vendor_data:
            vendor.BillAddr = vendor_data["BillAddr"]

        try:
            vendor.save(qb=client)
            logger.info(f"Successfully created vendor: {vendor.DisplayName} (ID: {vendor.Id})")
            return vendor.to_dict()
        except Exception as e:
            logger.error(f"Failed to create vendor: {str(e)}")
            raise QuickBooksAPIException(f"Failed to create vendor: {str(e)}")

    async def _update_vendor(
        self,
        client: QuickBooks,
        existing_vendor: Vendor,
        vendor_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing vendor using python-quickbooks."""
        # Update fields
        existing_vendor.DisplayName = vendor_data.get("DisplayName", existing_vendor.DisplayName)
        existing_vendor.GivenName = vendor_data.get("GivenName", existing_vendor.GivenName)
        existing_vendor.FamilyName = vendor_data.get("FamilyName", existing_vendor.FamilyName)
        existing_vendor.CompanyName = vendor_data.get("CompanyName", existing_vendor.CompanyName)
        existing_vendor.PrintOnCheckName = vendor_data.get(
            "PrintOnCheckName", existing_vendor.DisplayName
        )

        # Update optional fields if provided
        if "PrimaryEmailAddr" in vendor_data:
            existing_vendor.PrimaryEmailAddr = vendor_data["PrimaryEmailAddr"]
        if "PrimaryPhone" in vendor_data:
            existing_vendor.PrimaryPhone = vendor_data["PrimaryPhone"]
        if "BillAddr" in vendor_data:
            existing_vendor.BillAddr = vendor_data["BillAddr"]

        try:
            existing_vendor.save(qb=client)
            logger.info(f"Successfully updated vendor: {existing_vendor.DisplayName} (ID: {existing_vendor.Id})")
            return existing_vendor.to_dict()
        except Exception as e:
            logger.error(f"Failed to update vendor: {str(e)}")
            raise QuickBooksAPIException(f"Failed to update vendor: {str(e)}")

    async def create_bill(
        self,
        access_token: str,
        realm_id: str,
        invoice_data: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Create a bill in QuickBooks from invoice data using python-quickbooks.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID
            invoice_data: Invoice data from AP intake system
            dry_run: If True, validate without creating

        Returns:
            Created bill data or validation result
        """
        logger.info(f"Creating bill for invoice: {invoice_data.get('header', {}).get('invoice_no', 'Unknown')}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Map invoice data to QuickBooks bill format
            bill = await self._map_invoice_to_bill(client, invoice_data)

            # Validate the bill
            validation_errors = self._validate_bill(bill)
            if validation_errors:
                raise ValidationException(f"Bill validation failed: {validation_errors}")

            if dry_run:
                logger.info("Dry run: Bill validation passed, not creating")
                return {
                    "status": "validated",
                    "bill": bill.to_dict(),
                    "total_amount": bill.TotalAmt
                }

            # Create the bill
            bill.save(qb=client)

            logger.info(f"Successfully created bill with ID: {bill.Id}")
            return {
                "Bill": bill.to_dict(),
                "Id": bill.Id,
                "TotalAmt": bill.TotalAmt
            }

        except Exception as e:
            logger.error(f"Failed to create bill: {str(e)}")
            raise QuickBooksAPIException(f"Bill creation failed: {str(e)}")

    async def _map_invoice_to_bill(self, client: QuickBooks, invoice_data: Dict[str, Any]) -> Bill:
        """Map AP intake invoice data to QuickBooks Bill object."""
        header = invoice_data.get("header", {})
        lines = invoice_data.get("lines", [])

        # Find or create vendor
        vendor_name = header.get("vendor_name", "Unknown Vendor")
        vendor_data = {
            "DisplayName": vendor_name,
            "CompanyName": vendor_name
        }

        # Ensure vendor exists
        await self.create_or_update_vendor(
            client.access_token,
            client.company_id,
            vendor_data
        )

        # Find vendor reference
        vendor = await self._find_vendor_by_name(client, vendor_name)
        if not vendor:
            raise QuickBooksAPIException(f"Could not find or create vendor: {vendor_name}")

        # Create bill
        bill = Bill()
        bill.VendorRef = vendor.to_ref()
        bill.TxnDate = self._format_date(header.get("invoice_date"))
        bill.DueDate = self._format_date(header.get("due_date"))
        bill.PrivateNote = f"Imported from AP Intake System - PO: {header.get('po_no', 'N/A')}"

        # Map line items
        line_items = []
        total_amount = 0.0

        for i, line in enumerate(lines):
            from quickbooks.objects.account import AccountBasedExpenseLineDetail

            # Create line detail
            detail = AccountBasedExpenseLineDetail()
            detail.AccountRef = self._get_default_expense_account(client)
            detail.BillableStatus = "NotBillable"
            detail.Qty = float(line.get("quantity", 1))
            detail.UnitPrice = float(line.get("unit_price", 0))

            # Create bill line
            from quickbooks.objects.bill import BillLine
            bill_line = BillLine()
            bill_line.Description = line.get("description", "")
            bill_line.Amount = float(line.get("amount", 0))
            bill_line.DetailType = "AccountBasedExpenseLineDetail"
            bill_line.AccountBasedExpenseLineDetail = detail

            line_items.append(bill_line)
            total_amount += float(line.get("amount", 0))

        bill.Line = line_items

        # Set total if provided and differs from calculated total
        header_total = float(header.get("total", 0))
        if header_total > 0 and abs(header_total - total_amount) > 0.01:
            bill.TotalAmt = header_total

        return bill

    def _get_default_expense_account(self, client: QuickBooks):
        """Get default expense account or create one."""
        try:
            # Try to find existing expense account
            accounts = Account.query(
                "select * from Account where AccountType = 'Expense' and Active = true",
                qb=client
            )

            if accounts:
                return accounts[0].to_ref()

            # Create default expense account if none exists
            default_account = Account()
            default_account.Name = "Default Expense Account"
            default_account.AccountType = "Expense"
            default_account.AccountSubType = "OperatingExpenses"
            default_account.Active = True
            default_account.save(qb=client)

            return default_account.to_ref()

        except Exception as e:
            logger.warning(f"Could not create default expense account: {str(e)}")
            # Return a reference to account ID 1 (usually exists)
            from quickbooks.objects.ref import Ref
            return Ref(type="Account", value="1")

    def _validate_bill(self, bill: Bill) -> List[str]:
        """Validate bill object before saving to QuickBooks."""
        errors = []

        # Required fields
        if not bill.VendorRef or not bill.VendorRef.value:
            errors.append("Vendor reference is required")

        if not bill.Line or len(bill.Line) == 0:
            errors.append("At least one line item is required")

        # Validate line items
        for i, line in enumerate(bill.Line or []):
            if not line.Amount or line.Amount <= 0:
                errors.append(f"Line {i+1}: Amount is required and must be greater than 0")

            if not line.Description or not line.Description.strip():
                errors.append(f"Line {i+1}: Description is required")

        return errors

    def _format_date(self, date_str: Optional[str]) -> datetime:
        """Format date string for QuickBooks API."""
        if not date_str:
            return datetime.now()

        try:
            # Try to parse common date formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            # If no format matches, use today's date
            return datetime.now()

        except Exception:
            return datetime.now()

    async def export_multiple_bills(
        self,
        access_token: str,
        realm_id: str,
        invoices: List[Dict[str, Any]],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Export multiple invoices as bills to QuickBooks using batch operations.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID
            invoices: List of invoice data
            dry_run: If True, validate without creating

        Returns:
            Export results with success/failure details
        """
        logger.info(f"Exporting {len(invoices)} invoices to QuickBooks")

        results = {
            "total": len(invoices),
            "success": 0,
            "failed": 0,
            "errors": [],
            "created_bills": []
        }

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            if dry_run:
                # Validate all bills without creating
                for invoice in invoices:
                    try:
                        bill = await self._map_invoice_to_bill(client, invoice)
                        validation_errors = self._validate_bill(bill)
                        if validation_errors:
                            results["failed"] += 1
                            results["errors"].append({
                                "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                                "error": f"Validation failed: {validation_errors}"
                            })
                        else:
                            results["success"] += 1
                    except Exception as e:
                        results["failed"] += 1
                        results["errors"].append({
                            "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                            "error": str(e)
                        })
            else:
                # Use batch operation for better performance
                batch_items = []

                for invoice in invoices:
                    try:
                        bill = await self._map_invoice_to_bill(client, invoice)
                        validation_errors = self._validate_bill(bill)
                        if validation_errors:
                            results["failed"] += 1
                            results["errors"].append({
                                "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                                "error": f"Validation failed: {validation_errors}"
                            })
                            continue

                        # Create batch item
                        batch_item = BatchItemRequest()
                        batch_item.bId = invoice.get("metadata", {}).get("invoice_id")
                        batch_item.operation = "create"
                        batch_item.Bill = bill

                        batch_items.append(batch_item)

                    except Exception as e:
                        results["failed"] += 1
                        results["errors"].append({
                            "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                            "error": str(e)
                        })

                # Execute batch operation if there are items to process
                if batch_items:
                    try:
                        from quickbooks.batch import Batch
                        batch = Batch()
                        batch.BatchItemRequest = batch_items

                        batch_result = batch.execute(qb=client)

                        # Process batch results
                        for item in batch_result.BatchItemResponse:
                            if item.bId:
                                if hasattr(item, 'Fault'):
                                    results["failed"] += 1
                                    results["errors"].append({
                                        "invoice_id": item.bId,
                                        "error": str(item.Fault)
                                    })
                                else:
                                    results["success"] += 1
                                    results["created_bills"].append({
                                        "invoice_id": item.bId,
                                        "bill_id": getattr(item, 'Bill', {}).get('Id')
                                    })

                    except Exception as e:
                        logger.error(f"Batch operation failed: {str(e)}")
                        # Fallback to individual processing
                        for invoice in invoices:
                            try:
                                result = await self.create_bill(access_token, realm_id, invoice, dry_run)
                                if result.get("Bill"):
                                    results["success"] += 1
                                    results["created_bills"].append({
                                        "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                                        "bill_id": result["Bill"]["Id"]
                                    })
                                else:
                                    results["failed"] += 1
                            except Exception as e:
                                results["failed"] += 1
                                results["errors"].append({
                                    "invoice_id": invoice.get("metadata", {}).get("invoice_id"),
                                    "error": str(e)
                                })

        except Exception as e:
            logger.error(f"Batch export failed: {str(e)}")
            results["failed"] += len(invoices)
            results["errors"].append({"error": f"Batch export failed: {str(e)}"})

        logger.info(f"Export completed: {results['success']} success, {results['failed']} failed")
        return results

    async def download_bill_pdf(
        self,
        access_token: str,
        realm_id: str,
        bill_id: str
    ) -> bytes:
        """
        Download a bill as PDF from QuickBooks.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID
            bill_id: Bill ID

        Returns:
            PDF content as bytes
        """
        logger.info(f"Downloading PDF for bill: {bill_id}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Download PDF
            pdf_content = client.download_pdf(bill_id, "Bill")

            logger.info(f"Successfully downloaded PDF for bill: {bill_id}")
            return pdf_content

        except Exception as e:
            logger.error(f"Failed to download PDF for bill {bill_id}: {str(e)}")
            raise QuickBooksAPIException(f"Failed to download PDF: {str(e)}")

    async def send_bill_email(
        self,
        access_token: str,
        realm_id: str,
        bill_id: str,
        email_address: str
    ) -> Dict[str, Any]:
        """
        Send a bill via email through QuickBooks.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID
            bill_id: Bill ID
            email_address: Recipient email address

        Returns:
            Send result
        """
        logger.info(f"Sending email for bill: {bill_id} to {email_address}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Get bill and send email
            bill = Bill.get(bill_id, qb=client)
            result = bill.send_email(email_address, qb=client)

            logger.info(f"Successfully sent email for bill: {bill_id}")
            return {"status": "sent", "bill_id": bill_id, "email": email_address}

        except Exception as e:
            logger.error(f"Failed to send email for bill {bill_id}: {str(e)}")
            raise QuickBooksAPIException(f"Failed to send email: {str(e)}")

    async def handle_webhook(
        self,
        webhook_data: Dict[str, Any],
        signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle incoming webhook from QuickBooks.

        Args:
            webhook_data: Webhook payload
            signature: HMAC signature for verification (if available)

        Returns:
            Processing result
        """
        logger.info("Processing QuickBooks webhook")

        try:
            # Verify webhook signature if provided
            if signature:
                if not self._verify_webhook_signature(webhook_data, signature):
                    logger.error("Webhook signature verification failed")
                    raise QuickBooksServiceException("Invalid webhook signature")
                logger.info("Webhook signature verified successfully")

            # Process webhook events
            event_notifications = webhook_data.get("eventNotifications", [])
            processed_entities = []

            for notification in event_notifications:
                data_change = notification.get("dataChangeEvent", {})
                entities = data_change.get("entities", [])

                for entity in entities:
                    entity_type = entity.get("type")
                    entity_id = entity.get("id")
                    operation = entity.get("operation")

                    logger.info(f"Processing webhook: {operation} {entity_type} {entity_id}")

                    # Handle different entity types
                    if entity_type == "Bill":
                        await self._process_bill_webhook(entity, operation)
                    elif entity_type == "Vendor":
                        await self._process_vendor_webhook(entity, operation)

                    processed_entities.append({
                        "type": entity_type,
                        "id": entity_id,
                        "operation": operation,
                        "status": "processed"
                    })

            return {
                "status": "success",
                "processed_entities": processed_entities
            }

        except Exception as e:
            logger.error(f"Webhook processing failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _process_bill_webhook(self, entity: Dict[str, Any], operation: str):
        """Process bill-specific webhook events."""
        bill_id = entity.get("id")

        if operation == "Create":
            logger.info(f"Bill {bill_id} created in QuickBooks")
            # Trigger any post-creation processing
        elif operation == "Update":
            logger.info(f"Bill {bill_id} updated in QuickBooks")
            # Handle bill updates
        elif operation == "Delete":
            logger.info(f"Bill {bill_id} deleted in QuickBooks")
            # Handle bill deletion

    async def _process_vendor_webhook(self, entity: Dict[str, Any], operation: str):
        """Process vendor-specific webhook events."""
        vendor_id = entity.get("id")

        if operation == "Create":
            logger.info(f"Vendor {vendor_id} created in QuickBooks")
        elif operation == "Update":
            logger.info(f"Vendor {vendor_id} updated in QuickBooks")
        elif operation == "Delete":
            logger.info(f"Vendor {vendor_id} deleted in QuickBooks")

    async def disconnect_app(self, access_token: str, realm_id: str) -> bool:
        """
        Disconnect the app from QuickBooks.

        Args:
            access_token: Valid access token
            realm_id: QuickBooks company ID

        Returns:
            True if disconnection successful
        """
        logger.info(f"Disconnecting app from realm: {realm_id}")

        try:
            client = self.get_quickbooks_client(access_token, realm_id)

            # Disconnect using the python-quickbooks library
            from quickbooks.services.disconnect import DisconnectService
            disconnect_service = DisconnectService()
            result = disconnect_service.disconnect(client)

            logger.info("Successfully disconnected from QuickBooks")
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect: {str(e)}")
            return False
    
    def _verify_webhook_signature(self, webhook_data: Dict[str, Any], signature: str) -> bool:
        """
        Verify QuickBooks webhook signature using HMAC-SHA256.
        
        Args:
            webhook_data: The webhook payload
            signature: The HMAC signature from the request header
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            import hmac
            import hashlib
            import json
            
            # Get webhook verifier token from settings
            verifier_token = settings.QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN
            if not verifier_token:
                logger.warning("QuickBooks webhook verifier token not configured")
                return False
            
            # QuickBooks sends signature as: sha256=<hex_signature>
            if not signature.startswith('sha256='):
                logger.error("Invalid signature format, expected 'sha256=<hex>'")
                return False
            
            received_signature = signature[7:]  # Remove 'sha256=' prefix
            
            # Create the expected signature
            # QuickBooks uses the raw JSON payload as the message
            message = json.dumps(webhook_data, separators=(',', ':'), sort_keys=True)
            expected_signature = hmac.new(
                verifier_token.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures securely
            is_valid = hmac.compare_digest(received_signature, expected_signature)
            
            if not is_valid:
                logger.error(f"Signature mismatch. Expected: {expected_signature}, Received: {received_signature}")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False