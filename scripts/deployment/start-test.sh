#!/bin/bash

# AP Intake & Validation System - Test Setup Script
# This script starts the system with non-conflicting ports for testing

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
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

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    print_success "Docker is running"
}

# Check if required files exist
check_requirements() {
    if [ ! -f "docker-compose.test.yml" ]; then
        print_error "docker-compose.test.yml not found. Please run from project root."
        exit 1
    fi

    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from example..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warning "Please edit .env with your configuration"
        else
            print_error "No .env.example found. Please create .env file manually."
        fi
    fi
}

# Start services
start_services() {
    print_status "Starting AP Intake & Validation System (Test Environment)..."
    
    # Use the test compose file with different ports
    docker-compose -f docker-compose.test.yml up -d

    # Wait for services to be ready
    print_status "Waiting for services to be ready..."
    sleep 15

    # Check service health
    if docker-compose -f docker-compose.test.yml ps | grep -q "Up.*healthy\|Up"; then
        print_success "Services started successfully"
    else
        print_error "Some services failed to start. Check docker-compose -f docker-compose.test.yml ps"
        docker-compose -f docker-compose.test.yml ps
        exit 1
    fi
}

# Initialize database
initialize_database() {
    print_status "Initializing database..."
    
    # Wait a bit more for database to be fully ready
    sleep 10
    
    # Run database migrations
    if docker-compose -f docker-compose.test.yml exec -T api alembic upgrade head; then
        print_success "Database migrations completed"
    else
        print_warning "Database migrations failed, will continue..."
    fi
}

# Display service URLs
display_urls() {
    print_status "Service URLs (Test Environment):"
    echo ""
    echo "🌐 API:              http://localhost:8001"
    echo "📚 API Docs:         http://localhost:8001/docs"
    echo "🏥 Health Check:     http://localhost:8001/health"
    echo "📊 Metrics:          http://localhost:8001/metrics"
    echo ""
    echo "🖥️  MinIO Console:   http://localhost:9005 (minioadmin/minioadmin123)"
    echo "🐰 RabbitMQ:        Not configured in test setup"
    echo "🌸 Flower:          Not configured in test setup"
    echo ""
    echo "🎨 Frontend:         http://localhost:3001"
    echo ""
    echo "📧 Email Testing:     Send emails to configured Gmail address"
    echo "🔔 Slack Testing:     Configure Slack webhook in .env"
    echo ""
}

# Show usage information
show_usage() {
    echo "AP Intake & Validation System - Test Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -s, --stop              Stop all services"
    echo "  -r, --restart           Restart all services"
    echo "  -l, --logs              Show service logs"
    echo "  -t, --test              Run health tests after startup"
    echo ""
    echo "Examples:"
    echo "  $0                      Start all services"
    echo "  $0 --stop               Stop all services"
    echo "  $0 --logs               Show logs"
    echo ""
}

# Stop all services
stop_services() {
    print_status "Stopping all services..."
    docker-compose -f docker-compose.test.yml down
    print_success "All services stopped"
}

# Restart all services
restart_services() {
    print_status "Restarting all services..."
    stop_services
    sleep 5
    start_services
    initialize_database
    display_urls
    print_success "System restart completed!"
}

# Show logs
show_logs() {
    print_status "Showing service logs..."
    docker-compose -f docker-compose.test.yml logs -f
}

# Run health tests
run_health_tests() {
    print_status "Running health tests..."
    
    # Test API health
    if curl -s http://localhost:8001/health | grep -q "healthy"; then
        print_success "API health check passed"
    else
        print_warning "API health check failed"
    fi
    
    # Test frontend
    if curl -s http://localhost:3001 > /dev/null; then
        print_success "Frontend is accessible"
    else
        print_warning "Frontend not accessible"
    fi
    
    print_success "Health tests completed"
}

# Main execution
main_startup() {
    print_status "Starting AP Intake & Validation System (Test Environment)..."
    echo ""
    
    check_docker
    check_requirements
    start_services
    initialize_database
    display_urls
    print_success "System startup completed!"
    
    echo ""
    print_status "🧪 Ready for Manual Testing:"
    echo "   1. Send email with invoice PDF to configured address"
    echo "   2. Check processing at http://localhost:3001"
    echo "   3. Monitor Slack notifications"
    echo "   4. Verify API at http://localhost:8001/docs"
    echo ""
}

# Parse command line arguments
case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
    -s|--stop)
        stop_services
        exit 0
        ;;
    -r|--restart)
        restart_services
        exit 0
        ;;
    -l|--logs)
        show_logs
        exit 0
        ;;
    -t|--test)
        run_health_tests
        exit 0
        ;;
    "")
        main_startup
        ;;
    *)
        print_error "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac