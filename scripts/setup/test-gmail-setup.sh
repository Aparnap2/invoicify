#!/bin/bash

# Gmail OAuth Testing Script for AP Intake System
# This script helps test Gmail OAuth setup and email processing

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if test environment file exists
check_test_env() {
    if [ ! -f ".env.test" ]; then
        print_error ".env.test file not found. Please create it first."
        exit 1
    fi
    print_success "Test environment file found"
}

# Setup test environment
setup_test_env() {
    print_status "Setting up test environment..."
    
    # Copy test environment to local
    cp .env.test .env.local
    
    # Load test environment (handle special characters properly)
        set -a
        source .env.local
        set +a
    
    print_success "Test environment loaded"
}

# Start core services
start_core_services() {
    print_status "Starting core services..."
    
    # Start only core services (postgres, redis, minio)
    docker-compose -f docker-compose.simple.yml up -d
    
    # Wait for services to be ready
    print_status "Waiting for services to be ready..."
    sleep 10
    
    print_success "Core services started"
}

# Test Gmail OAuth endpoints
test_gmail_endpoints() {
    print_status "Testing Gmail OAuth endpoints..."
    
    # Test health endpoint
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        print_success "API health endpoint accessible"
    else
        print_warning "API health endpoint not accessible - starting API..."
        
        # Stop existing services first
        docker-compose -f docker-compose.simple.yml down
        
        # Start full test environment
        docker-compose -f docker-compose.test.yml up -d
        sleep 20
        
        if curl -s http://localhost:8001/health > /dev/null; then
            print_success "API started and health endpoint accessible"
        else
            print_error "API failed to start - check logs"
            docker-compose -f docker-compose.test.yml logs api
            return 1
        fi
    fi
}

# Test Gmail OAuth setup
test_gmail_oauth() {
    print_status "Testing Gmail OAuth configuration..."
    
    # Check if Gmail credentials are configured
    if grep -q "your-gmail-client-id-here" .env.local; then
        print_warning "Gmail credentials not configured in .env.local"
        print_status "Please update GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env.local"
        print_status "See GMAIL_OAUTH_TESTING_GUIDE.md for instructions"
        return 1
    fi
    
    print_success "Gmail credentials found in environment"
    
    # Test Gmail watch status endpoint
    if curl -s http://localhost:8001/api/v1/gmail/watch/status > /dev/null 2>&1; then
        print_success "Gmail watch status endpoint accessible"
    else
        print_warning "Gmail watch status endpoint not accessible"
    fi
}

# Generate test invoice
generate_test_invoice() {
    print_status "Generating test invoice..."
    
    # Create test invoice directory if it doesn't exist
    mkdir -p test_invoices
    
    # Generate a simple test invoice
    python scripts/create_test_invoice.py --scenario standard --count 1 --output-dir test_invoices
    
    if [ -f test_invoices/test_invoice_standard_*.pdf ]; then
        print_success "Test invoice generated successfully"
        ls -la test_invoices/
    else
        print_error "Failed to generate test invoice"
        return 1
    fi
}

# Display testing URLs
display_test_urls() {
    print_status "Testing URLs:"
    echo ""
    echo "🌐 API:              http://localhost:8001"
    echo "📚 API Docs:         http://localhost:8001/docs"
    echo "🏥 Health Check:     http://localhost:8001/health"
    echo "🔗 Gmail OAuth:      http://localhost:8001/api/v1/gmail/auth"
    echo "📧 Gmail Watch:      http://localhost:8001/api/v1/gmail/watch"
    echo "🖥️  MinIO Console:   http://localhost:9005 (minioadmin/minioadmin123)"
    echo ""
}

# Show next steps
show_next_steps() {
    print_status "🎯 Next Steps for Gmail Testing:"
    echo ""
    echo "1. 📋 Configure Gmail OAuth:"
    echo "   - Update GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env.local"
    echo "   - See GMAIL_OAUTH_TESTING_GUIDE.md for detailed instructions"
    echo ""
    echo "2. 🔗 Initialize Gmail Watch:"
    echo "   - Open: http://localhost:8001/api/v1/gmail/auth"
    echo "   - Authorize with your Gmail account"
    echo "   - Start watch: curl -X POST http://localhost:8001/api/v1/gmail/watch"
    echo ""
    echo "3. 📧 Send Test Email:"
    echo "   - Send email with PDF invoice to your Gmail address"
    echo "   - Use generated test invoice from test_invoices/ directory"
    echo ""
    echo "4. 📊 Monitor Processing:"
    echo "   - Check: http://localhost:8001/api/v1/gmail/watch/status"
    echo "   - Monitor: docker-compose -f docker-compose.test.yml logs api"
    echo "   - View: http://localhost:3001 (when frontend is running)"
    echo ""
}

# Show usage information
show_usage() {
    echo "Gmail OAuth Testing Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -s, --setup            Setup test environment only"
    echo "  -t, --test             Test Gmail OAuth endpoints"
    echo "  -g, --generate          Generate test invoice"
    echo "  -a, --all              Run complete setup and test"
    echo ""
    echo "Examples:"
    echo "  $0                      Setup and test everything"
    echo "  $0 --setup              Setup test environment only"
    echo "  $0 --test               Test Gmail OAuth only"
    echo "  $0 --generate           Generate test invoice only"
    echo ""
}

# Main execution
main() {
    case "${1:-}" in
        -h|--help)
            show_usage
            exit 0
            ;;
        -s|--setup)
            check_test_env
            setup_test_env
            start_core_services
            display_test_urls
            ;;
        -t|--test)
            check_test_env
            setup_test_env
            test_gmail_endpoints
            test_gmail_oauth
            ;;
        -g|--generate)
            generate_test_invoice
            ;;
        -a|--all|"")
            check_test_env
            setup_test_env
            start_core_services
            test_gmail_endpoints
            test_gmail_oauth
            generate_test_invoice
            display_test_urls
            show_next_steps
            print_success "Gmail OAuth testing setup completed!"
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"