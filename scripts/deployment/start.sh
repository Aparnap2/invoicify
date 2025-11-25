#!/bin/bash

# AP Intake & Validation System - Unified Start Script
# This script starts all system components with proper initialization

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
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found. Please run from project root."
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

# Start core services
start_core_services() {
    print_status "Starting core services (PostgreSQL, Redis, RabbitMQ, MinIO)..."
    docker-compose up -d postgres redis rabbitmq minio

    # Wait for services to be ready
    print_status "Waiting for services to be ready..."
    sleep 10

    # Check service health
    if docker-compose ps | grep -q "Up.*healthy\|Up"; then
        print_success "Core services started successfully"
    else
        print_error "Some services failed to start. Check docker-compose ps"
        docker-compose ps
        exit 1
    fi
}

# Initialize database
initialize_database() {
    print_status "Initializing database..."

    # Run database migrations
    if docker-compose exec -T api alembic upgrade head; then
        print_success "Database migrations completed"
    else
        print_warning "API container not running, will initialize later"
    fi
}

# Start application services
start_application() {
    print_status "Starting application services..."

    # Start API and worker
    docker-compose up -d api worker

    # Wait for API to be ready
    print_status "Waiting for API to be ready..."
    sleep 15

    # Check API health
    if curl -s http://localhost:8000/health > /dev/null; then
        print_success "API is ready"
    else
        print_warning "API not responding yet, will continue startup"
    fi
}

# Start frontend
start_frontend() {
    print_status "Starting frontend..."

    if [ -d "web" ]; then
        cd web
        if [ -f "package.json" ]; then
            if command -v npm &> /dev/null; then
                npm run dev &
                FRONTEND_PID=$!
                print_success "Frontend started in background (PID: $FRONTEND_PID)"
            else
                print_warning "npm not found. Please install Node.js and npm"
            fi
        else
            print_warning "No package.json found in web directory"
        fi
        cd ..
    else
        print_warning "Web directory not found"
    fi
}

# Display service URLs
display_urls() {
    print_status "Service URLs:"
    echo ""
    echo "🌐 API:              http://localhost:8000"
    echo "📚 API Docs:         http://localhost:8000/docs"
    echo "🏥 Health Check:     http://localhost:8000/health"
    echo "📊 Metrics:          http://localhost:8000/metrics"
    echo ""
    echo "🖥️  MinIO Console:   http://localhost:9001 (minioadmin/minioadmin123)"
    echo "🐰 RabbitMQ Mgmt:    http://localhost:15672 (guest/guest)"
    echo "🌸 Flower (Celery):  http://localhost:5555"
    echo "📈 Grafana:          http://localhost:3001"
    echo "🔍 Prometheus:       http://localhost:9090"
    echo ""
    echo "🎨 Frontend:         http://localhost:3000"
    echo ""
}

# Show usage information
show_usage() {
    echo "AP Intake & Validation System - Start Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -c, --core-only         Start only core services (DB, Redis, RabbitMQ, MinIO)"
    echo "  -a, --app-only          Start application services (API, Worker) - assumes core running"
    echo "  -f, --with-frontend     Include frontend in startup"
    echo "  -s, --stop              Stop all services"
    echo "  -r, --restart           Restart all services"
    echo "  -l, --logs              Show service logs"
    echo "  -t, --test              Run health tests after startup"
    echo "  --init-only             Only initialize database"
    echo ""
    echo "Examples:"
    echo "  $0                      Start all services"
    echo "  $0 --core-only          Start only core services"
    echo "  $0 --with-frontend      Start everything including frontend"
    echo "  $0 --stop               Stop all services"
    echo ""
}

# Stop all services
stop_services() {
    print_status "Stopping all services..."
    docker-compose down

    # Stop frontend if running
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        print_success "Frontend stopped"
    fi

    print_success "All services stopped"
}

# Restart all services
restart_services() {
    print_status "Restarting all services..."
    stop_services
    sleep 5
    main_startup
}

# Show logs
show_logs() {
    print_status "Showing service logs..."
    docker-compose logs -f
}

# Run health tests
run_health_tests() {
    print_status "Running health tests..."

    # Test API health
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        print_success "API health check passed"
    else
        print_warning "API health check failed"
    fi

    # Test database connectivity
    if docker-compose exec -T api python -c "
import asyncio
from app.core.config import settings
async def test_db():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.begin() as conn:
            await conn.execute('SELECT 1')
        print('Database connection: OK')
    except Exception as e:
        print(f'Database connection failed: {e}')
asyncio.run(test_db())
" 2>/dev/null; then
        print_success "Database connectivity test passed"
    else
        print_warning "Database connectivity test failed"
    fi

    print_success "Health tests completed"
}

# Main startup function
main_startup() {
    print_status "Starting AP Intake & Validation System..."
    echo ""

    check_docker
    check_requirements
    start_core_services

    if [ "$INIT_ONLY" != "true" ]; then
        initialize_database
        start_application

        if [ "$WITH_FRONTEND" = "true" ]; then
            start_frontend
        fi

        if [ "$RUN_TESTS" = "true" ]; then
            run_health_tests
        fi

        display_urls
        print_success "System startup completed!"
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -c|--core-only)
            CORE_ONLY=true
            shift
            ;;
        -a|--app-only)
            APP_ONLY=true
            shift
            ;;
        -f|--with-frontend)
            WITH_FRONTEND=true
            shift
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
            RUN_TESTS=true
            shift
            ;;
        --init-only)
            INIT_ONLY=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Handle different startup modes
if [ "$CORE_ONLY" = "true" ]; then
    print_status "Starting core services only..."
    check_docker
    check_requirements
    start_core_services
    display_urls
    print_success "Core services started!"
elif [ "$APP_ONLY" = "true" ]; then
    print_status "Starting application services only..."
    check_docker
    initialize_database
    start_application

    if [ "$RUN_TESTS" = "true" ]; then
        run_health_tests
    fi

    display_urls
    print_success "Application services started!"
else
    main_startup
fi

# Cleanup function for graceful shutdown
cleanup() {
    print_status "Shutting down..."
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    exit 0
}

# Trap signals for graceful shutdown
trap cleanup SIGINT SIGTERM

# Keep script running if frontend was started
if [ ! -z "$FRONTEND_PID" ]; then
    print_status "Press Ctrl+C to stop all services..."
    wait $FRONTEND_PID
fi