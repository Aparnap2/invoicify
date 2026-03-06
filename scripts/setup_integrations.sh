#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════
# Invoicify Integration Setup Script
# Purpose: Interactive setup for QuickBooks + Salesforce integrations
# ═══════════════════════════════════════════════════════════════

ENV_FILE="apps/agent-core/.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     Invoicify Integration Setup                           ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${YELLOW}═══ $1 ═══${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Ensure .env file exists
ensure_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        print_info "Creating $ENV_FILE..."
        touch "$ENV_FILE"
    fi
}

# Remove existing credentials from .env (to avoid duplicates)
remove_existing_credentials() {
    print_info "Cleaning up existing integration credentials..."
    
    # QuickBooks credentials
    sed -i '/^QB_CLIENT_ID=/d' "$ENV_FILE"
    sed -i '/^QB_CLIENT_SECRET=/d' "$ENV_FILE"
    sed -i '/^QB_REALM_ID=/d' "$ENV_FILE"
    sed -i '/^QB_REFRESH_TOKEN=/d' "$ENV_FILE"
    sed -i '/^QB_SANDBOX=/d' "$ENV_FILE"
    
    # Salesforce credentials
    sed -i '/^SF_CONSUMER_KEY=/d' "$ENV_FILE"
    sed -i '/^SF_USERNAME=/d' "$ENV_FILE"
    sed -i '/^SF_PRIVATE_KEY_PEM=/d' "$ENV_FILE"
    sed -i '/^SF_INSTANCE_URL=/d' "$ENV_FILE"
    sed -i '/^SF_SANDBOX=/d' "$ENV_FILE"
}

# QuickBooks setup
setup_quickbooks() {
    print_section "QuickBooks Online Setup"
    
    echo "Step 1: Get your QuickBooks credentials"
    echo ""
    echo "  1. Go to https://developer.intuit.com/app/developer/playground"
    echo "  2. Select your sandbox app → click 'Get Authorization Code'"
    echo "  3. Authorize the app → copy the authorization_code from the redirect URL"
    echo "  4. Exchange authorization code for tokens using this curl command:"
    echo ""
    echo "     curl -X POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer \\"
    echo "       -H 'Authorization: Basic $(echo -n \"<client_id>:<client_secret>\" | base64)' \\"
    echo "       -H 'Content-Type: application/x-www-form-urlencoded' \\"
    echo "       -d 'grant_type=authorization_code&code=<authorization_code>&redirect_uri=<your_redirect_uri>'"
    echo ""
    echo "  5. Copy the refresh_token from the response"
    echo ""
    echo "  More info: https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0-playground"
    echo ""
    
    read -p "Enter QB_CLIENT_ID: " QB_CLIENT_ID
    read -p "Enter QB_CLIENT_SECRET: " QB_CLIENT_SECRET
    read -p "Enter QB_REALM_ID (sandbox company ID): " QB_REALM_ID
    read -p "Enter QB_REFRESH_TOKEN: " QB_REFRESH_TOKEN
    
    # Validate required fields
    if [ -z "$QB_CLIENT_ID" ] || [ -z "$QB_CLIENT_SECRET" ] || [ -z "$QB_REALM_ID" ] || [ -z "$QB_REFRESH_TOKEN" ]; then
        print_warning "Some QuickBooks credentials are empty. Skipping QuickBooks setup."
        return 1
    fi
    
    # Append to .env
    cat >> "$ENV_FILE" << EOF

# ═══════════════════════════════════════════════════════════════
# QuickBooks Online (Sandbox)
# ═══════════════════════════════════════════════════════════════
QB_CLIENT_ID=$QB_CLIENT_ID
QB_CLIENT_SECRET=$QB_CLIENT_SECRET
QB_REALM_ID=$QB_REALM_ID
QB_REFRESH_TOKEN=$QB_REFRESH_TOKEN
QB_SANDBOX=true

EOF
    
    print_success "QuickBooks credentials saved to $ENV_FILE"
    return 0
}

# Salesforce setup
setup_salesforce() {
    print_section "Salesforce Setup"
    
    echo "Step 1: Create a Connected App in Salesforce"
    echo ""
    echo "  1. Go to Setup → App Manager → New Connected App"
    echo "  2. Fill in basic info (name, contact email)"
    echo "  3. Enable 'Use digital signatures' → upload your certificate"
    echo "  4. Enable 'Enable OAuth Settings' → add callback URL"
    echo "  5. Save → copy the Consumer Key"
    echo ""
    echo "Step 2: Generate RSA key pair (if you haven't already)"
    echo ""
    echo "  Run this command to generate a 2048-bit RSA private key:"
    echo "    openssl genrsa -out salesforce_key.pem 2048"
    echo ""
    echo "  Extract the public key for upload to Salesforce:"
    echo "    openssl rsa -in salesforce_key.pem -pubout -out salesforce_key.pub"
    echo ""
    echo "Step 3: Pre-authorize the user"
    echo ""
    echo "  1. Go to Setup → Manage Connected Apps"
    echo "  2. Find your app → Manage → Permitted Users"
    echo "  3. Add the username you'll use for JWT auth"
    echo ""
    echo "More info: https://help.salesforce.com/s/article/000325026"
    echo ""
    
    read -p "Enter SF_CONSUMER_KEY: " SF_CONSUMER_KEY
    read -p "Enter SF_USERNAME (pre-authorized user): " SF_USERNAME
    read -p "Enter SF_PRIVATE_KEY_PEM (path to PEM file): " SF_PRIVATE_KEY_PEM
    read -p "Enter SF_INSTANCE_URL (e.g., https://yourorg.my.salesforce.com): " SF_INSTANCE_URL
    
    # Validate required fields
    if [ -z "$SF_CONSUMER_KEY" ] || [ -z "$SF_USERNAME" ] || [ -z "$SF_PRIVATE_KEY_PEM" ] || [ -z "$SF_INSTANCE_URL" ]; then
        print_warning "Some Salesforce credentials are empty. Skipping Salesforce setup."
        return 1
    fi
    
    # Validate PEM file exists (if it's a path)
    if [ -f "$SF_PRIVATE_KEY_PEM" ]; then
        print_success "PEM file found: $SF_PRIVATE_KEY_PEM"
    else
        print_warning "PEM file not found at: $SF_PRIVATE_KEY_PEM"
        print_info "Make sure the path is correct or paste the PEM content directly."
    fi
    
    # Append to .env
    cat >> "$ENV_FILE" << EOF

# ═══════════════════════════════════════════════════════════════
# Salesforce (Developer Org)
# ═══════════════════════════════════════════════════════════════
SF_CONSUMER_KEY=$SF_CONSUMER_KEY
SF_USERNAME=$SF_USERNAME
SF_PRIVATE_KEY_PEM=$SF_PRIVATE_KEY_PEM
SF_INSTANCE_URL=$SF_INSTANCE_URL
SF_SANDBOX=true

EOF
    
    print_success "Salesforce credentials saved to $ENV_FILE"
    return 0
}

# Run smoke tests
run_smoke_tests() {
    print_section "Running Smoke Tests"
    
    cd "$ROOT_DIR"
    
    # QuickBooks smoke test
    echo "Testing QuickBooks..."
    if python -m src.mcp_servers.quickbooks_mcp --smoke-test 2>&1 | tee /tmp/qb_test.log; then
        print_success "QuickBooks: OK"
    else
        print_error "QuickBooks: FAILED"
        print_info "Check logs: /tmp/qb_test.log"
        print_info "Troubleshooting hints:"
        echo "  - Verify QB_REFRESH_TOKEN is valid (tokens expire after 90 days of inactivity)"
        echo "  - Ensure QB_SANDBOX=true for sandbox environment"
        echo "  - Check network connectivity to oauth.platform.intuit.com"
    fi
    
    echo ""
    
    # Salesforce smoke test
    echo "Testing Salesforce..."
    if python -m src.mcp_servers.salesforce_mcp --smoke-test 2>&1 | tee /tmp/sf_test.log; then
        print_success "Salesforce: OK"
    else
        print_error "Salesforce: FAILED"
        print_info "Check logs: /tmp/sf_test.log"
        print_info "Troubleshooting hints:"
        echo "  - Verify SF_PRIVATE_KEY_PEM path is correct"
        echo "  - Ensure SF_USERNAME is pre-authorized in Connected App"
        echo "  - Check SF_INSTANCE_URL matches your org (test.salesforce.com for sandbox)"
        echo "  - Verify certificate uploaded to Salesforce matches the private key"
    fi
    
    echo ""
    print_warning "Smoke tests completed. Even if tests failed, setup script exits with code 0."
    print_info "Fix any issues and re-run this script or test manually."
}

# Main execution
main() {
    print_header
    
    echo "This script will help you set up QuickBooks and Salesforce integrations."
    echo "Credentials will be saved to: $ENV_FILE"
    echo ""
    read -p "Continue? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Setup cancelled."
        exit 0
    fi
    
    ensure_env_file
    remove_existing_credentials
    
    # QuickBooks setup
    setup_quickbooks || true
    
    # Salesforce setup
    setup_salesforce || true
    
    # Smoke tests
    read -p "Run smoke tests now? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [ -z "$REPLY" ]; then
        run_smoke_tests
    fi
    
    echo ""
    print_section "Setup Complete"
    echo "Credentials saved to: $ENV_FILE"
    echo ""
    print_info "Restart your agent to load the new credentials:"
    echo "  cd apps/agent-core && uv run python -m src.main"
    echo ""
    print_info "To re-run setup later:"
    echo "  bash scripts/setup_integrations.sh"
    echo ""
}

# Run main function
main "$@"
