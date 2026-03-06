# QuickBooks MCP Server

Production-grade Model Context Protocol (MCP) server for QuickBooks Online API integration.

## Features

- **OAuth 2.0 Token Management**: Automatic token refresh with rotation
- **6 MCP Tools**: Complete invoice processing workflow
- **Resilience**: Exponential backoff for rate limiting (429), auto-retry on 401
- **Observability**: Structured logging with trace_id correlation
- **Type Safety**: Pydantic v2 models for all I/O
- **Security**: Token persistence to `.secrets/` (gitignored)

## Quick Start

### 1. Set Environment Variables

```bash
export QB_CLIENT_ID="your_client_id"
export QB_CLIENT_SECRET="your_client_secret"
export QB_REALM_ID="your_realm_id"
export QB_REFRESH_TOKEN="your_refresh_token"
export QB_SANDBOX="true"  # Set to "false" for production
```

Alternatively, use a file for the refresh token:
```bash
export QB_REFRESH_TOKEN_FILE="/path/to/refresh_token.txt"
```

### 2. Run as MCP Server

```bash
cd apps/agent-core
uv run python -m src.mcp_servers.quickbooks_mcp
```

### 3. Run Smoke Test

```bash
uv run python -m src.mcp_servers.quickbooks_mcp --smoke-test
```

Expected output:
- Success: `QB: ✓`
- Failure: `QB: ✗ <error message>`

## MCP Tools

### 1. `qb_create_bill`

Create a bill in QuickBooks.

**Parameters:**
- `vendor_id` (str): QuickBooks Vendor ID
- `line_items` (list[dict]): Bill line items
  - `description` (str): Item description
  - `amount` (float): Line item amount
  - `quantity` (float, optional): Quantity (default: 1)
  - `unit_price` (float, optional): Unit price (default: 0)
  - `account_ref` (str, optional): Account reference ID
- `due_date` (str): Due date (YYYY-MM-DD)
- `currency` (str, optional): Currency code (default: "USD")
- `doc_number` (str, optional): Document number
- `txn_date` (str, optional): Transaction date (YYYY-MM-DD)
- `private_note` (str, optional): Private note

**Returns:**
```json
{
  "bill_id": "123",
  "sync_token": "0",
  "total_amount": 100.0,
  "status": "Due",
  "vendor_ref": "vendor-123",
  "doc_number": "INV-001",
  "due_date": "2026-03-15",
  "created_at": "2026-03-06T05:00:00Z"
}
```

### 2. `qb_get_vendor`

Query vendor information.

**Parameters:**
- `vendor_name` (str): Vendor name to search for

**Returns:**
```json
{
  "vendor_id": "vendor-123",
  "display_name": "Acme Corp",
  "email": "billing@acme.com",
  "phone": "555-1234",
  "balance": 0.0,
  "active": true
}
```

### 3. `qb_create_vendor`

Create a new vendor.

**Parameters:**
- `display_name` (str): Vendor display name (required)
- `email` (str, optional): Email address
- `phone` (str, optional): Phone number
- `given_name` (str, optional): Contact first name
- `family_name` (str, optional): Contact last name
- `company_name` (str, optional): Company name

**Returns:**
```json
{
  "vendor_id": "vendor-123",
  "display_name": "Acme Corp",
  "sync_token": "0",
  "created_at": "2026-03-06T05:00:00Z",
  "active": true
}
```

### 4. `qb_get_bill`

Retrieve bill details.

**Parameters:**
- `bill_id` (str): QuickBooks Bill ID

**Returns:**
```json
{
  "bill_id": "123",
  "sync_token": "0",
  "vendor_ref": "vendor-123",
  "total_amount": 100.0,
  "balance": 100.0,
  "status": "Due",
  "due_date": "2026-03-15",
  "txn_date": "2026-03-01",
  "line_items": [...]
}
```

### 5. `qb_void_bill`

Void a bill.

**Parameters:**
- `bill_id` (str): QuickBooks Bill ID

**Returns:**
```json
{
  "bill_id": "123",
  "sync_token": "1",
  "status": "Void",
  "voided_at": "2026-03-06T05:00:00Z"
}
```

### 6. `qb_list_accounts`

List chart of accounts.

**Returns:**
```json
{
  "accounts": [...],
  "count": 50
}
```

## Token Management

### OAuth 2.0 Flow

The `TokenManager` class handles OAuth 2.0 token refresh:

1. **Initial Load**: Attempts to load cached tokens from `.secrets/qb_tokens.json`
2. **Auto-Refresh**: When access_token expires (with 5-minute buffer), automatically refreshes
3. **Token Rotation**: Each refresh returns a new refresh_token (single-use)
4. **Persistence**: Saves both tokens to `.secrets/qb_tokens.json`

### Token Lifecycle

- **Access Token**: Valid for 1 hour (3600 seconds)
- **Refresh Token**: Valid for 100 days of inactivity
- **Rotation**: Refresh token changes on each use

### Token File Format

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
  "refresh_token": "AB1234567890...",
  "expires_at": 1741234567,
  "realm_id": "123456789"
}
```

### File Permissions

Token file is created with `0600` permissions (owner read/write only).

## Error Handling

### 401 Unauthorized

1. Detects 401 response
2. Refreshes access token
3. Retries request once
4. Raises error if still 401 after refresh

### 429 Rate Limit

1. Detects 429 response
2. Reads `Retry-After` header
3. Retries with exponential backoff (2s, 4s, 8s, 16s, 32s max)
4. Raises error after 5 failed attempts

### Network Errors

- Retries with exponential backoff
- 30-second timeout per request
- Logs all errors with trace_id

## Logging

All logs are structured JSON with trace_id for correlation:

```json
{
  "trace_id": "f8e54013-e699-479c-bfc0-7f39aac70ec7",
  "event": "token_refresh_successful",
  "level": "info",
  "timestamp": "2026-03-06T05:00:00Z",
  "access_token_expires_in": 3600,
  "refresh_token_expires_in": 8726400
}
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `QB_CLIENT_ID` | Yes | - | OAuth client ID |
| `QB_CLIENT_SECRET` | Yes | - | OAuth client secret |
| `QB_REALM_ID` | Yes | - | Company/realm ID |
| `QB_REFRESH_TOKEN` | Yes* | - | OAuth refresh token |
| `QB_REFRESH_TOKEN_FILE` | Yes* | - | Path to refresh token file |
| `QB_SANDBOX` | No | `true` | Use sandbox environment |

*Either `QB_REFRESH_TOKEN` or `QB_REFRESH_TOKEN_FILE` is required.

### Sandbox vs Production

- **Sandbox**: `https://sandbox-quickbooks.api.intuit.com/v3`
- **Production**: `https://quickbooks.api.intuit.com/v3`

Set `QB_SANDBOX=false` for production.

## Directory Structure

```
apps/agent-core/
├── src/
│   └── mcp_servers/
│       ├── __init__.py
│       └── quickbooks_mcp.py
├── .secrets/              # Created automatically
│   └── qb_tokens.json     # Token cache (gitignored)
└── pyproject.toml
```

## Testing

### Unit Tests

```bash
cd apps/agent-core
uv run pytest tests/mcp_servers/test_quickbooks_mcp.py -v
```

### Integration Tests

Requires valid QuickBooks credentials:

```bash
export QB_CLIENT_ID="..."
export QB_CLIENT_SECRET="..."
export QB_REALM_ID="..."
export QB_REFRESH_TOKEN="..."

uv run python -m src.mcp_servers.quickbooks_mcp --smoke-test
```

## Security Considerations

1. **Token Storage**: Tokens stored in `.secrets/` directory (gitignored)
2. **File Permissions**: Token file created with `0600` permissions
3. **No Hardcoded Credentials**: All credentials from environment variables
4. **Input Validation**: Pydantic models validate all inputs
5. **SQL Injection Prevention**: No SQL queries (REST API only)

## Integration with Existing Code

The MCP server wraps the existing `quickbooks_sync.py` logic:

```python
from src.execution.quickbooks_sync import QuickBooksSync
from src.mcp_servers.quickbooks_mcp import QuickBooksMCPServer

# Use existing sync logic for batch operations
qb_sync = QuickBooksSync(redis_client)
result = await qb_sync.sync_invoice(invoice_data, invoice_id)

# Use MCP server for interactive tool calls
qb_mcp = QuickBooksMCPServer()
await qb_mcp.server.run_stdio_async()
```

## Troubleshooting

### "Missing required QuickBooks configuration"

Set all required environment variables:
```bash
export QB_CLIENT_ID="..."
export QB_CLIENT_SECRET="..."
export QB_REALM_ID="..."
export QB_REFRESH_TOKEN="..."
```

### "Token refresh failed"

1. Verify credentials are correct
2. Check if refresh token has expired (100 days of inactivity)
3. Re-authorize application in QuickBooks Developer Portal

### "Rate limited"

- QuickBooks Sandbox: 1,000 calls/day
- QuickBooks Production: Varies by plan
- Implement caching or reduce call frequency

### "401 after token refresh"

1. Refresh token may have expired
2. Re-authorize application
3. Get new refresh token from OAuth flow

## References

- [QuickBooks OAuth 2.0](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0)
- [QuickBooks Accounting API](https://developer.intuit.com/app/developer/qbo/docs/develop/accounting-api/concepts)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
