#!/bin/bash

# AP Intake & Validation - Developer Setup Script
# This script sets up the development environment for new developers

set -e  # Exit on any error

echo "🚀 Setting up AP Intake & Validation Development Environment"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "app" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

print_status "Verified project structure"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
print_info "Python version: $python_version"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    print_warning "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    print_status "uv installed"
else
    print_status "uv found: $(uv --version)"
fi

# Install dependencies
print_info "Installing Python dependencies..."
uv pip install -e .

# Install development dependencies
print_info "Installing development dependencies..."
uv pip install -r requirements.txt
uv pip install pytest pytest-cov black flake8 mypy pre-commit

# Setup environment files
print_info "Setting up environment configuration..."

if [ ! -f ".env" ]; then
    if [ -f "config/environments/.env.example" ]; then
        cp config/environments/.env.example .env
        print_status "Created .env from example"
    else
        print_warning "No .env.example found. Please create .env manually"
    fi
else
    print_status ".env already exists"
fi

# Setup database configuration
if [ ! -f "config/database/alembic.ini" ]; then
    print_warning "Database configuration not found. Please check config/database/"
fi

# Setup pre-commit hooks
print_info "Setting up pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    print_status "Pre-commit hooks installed"
else
    print_warning "pre-commit not found. Skipping hook setup."
fi

# Create necessary directories
print_info "Creating necessary directories..."
mkdir -p logs
mkdir -p temp
mkdir -p storage/uploads
mkdir -p storage/exports
print_status "Created required directories"

# Set proper permissions
chmod +x scripts/deployment/*.sh
chmod +x scripts/setup/*.sh
print_status "Set executable permissions on scripts"

# Check Docker installation
if command -v docker &> /dev/null; then
    print_status "Docker found: $(docker --version)"
    
    if command -v docker-compose &> /dev/null; then
        print_status "Docker Compose found: $(docker-compose --version)"
    else
        print_warning "Docker Compose not found. Install it for containerized development."
    fi
else
    print_warning "Docker not found. Install it for containerized development."
fi

# Run database migrations (if database is available)
print_info "Checking database connectivity..."
if [ -f ".env" ]; then
    # Try to run alembic check
    if uv run alembic check &> /dev/null 2>&1; then
        print_info "Running database migrations..."
        uv run alembic upgrade head
        print_status "Database migrations completed"
    else
        print_warning "Database not accessible. Skip migrations."
    fi
else
    print_warning "No .env file found. Skip database migrations."
fi

# Run tests to verify setup
print_info "Running tests to verify setup..."
if uv run pytest tests/ -v --tb=short; then
    print_status "All tests passed! Environment is ready."
else
    print_warning "Some tests failed. Check the output above."
fi

# Print next steps
echo ""
echo "🎉 Development Environment Setup Complete!"
echo "======================================"
echo ""
print_info "Next Steps:"
echo "1. Review the project structure: cat docs/README.md"
echo "2. Start development server: uv run uvicorn app.main:app --reload"
echo "3. Run tests: uv run pytest"
echo "4. Check code quality: uv run black app/ && uv run flake8 app/"
echo ""
print_info "Useful Commands:"
echo "- Start development:     uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo "- Run tests:            uv run pytest tests/ -v"
echo "- Test coverage:        uv run pytest --cov=app tests/"
echo "- Code formatting:       uv run black app/"
echo "- Type checking:         uv run mypy app/"
echo "- Linting:             uv run flake8 app/"
echo ""
print_info "Documentation:"
echo "- Architecture:          docs/architecture/"
echo "- Setup Guides:          docs/guides/"
echo "- Developer Experience:   docs/architecture/DEVELOPER_EXPERIENCE_IMPROVEMENTS.md"
echo ""
print_status "Happy coding! 🚀"