# AP Intake & Validation System

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A comprehensive AP (Accounts Payable) invoice processing and validation system built with Python, FastAPI, and modern web technologies.

## 🎯 Overview

AP Intake & Validation is an enterprise-grade system designed to:
- **Process invoices** from multiple sources (email, upload, API)
- **Validate and extract** invoice data using AI/ML
- **Manage workflows** for approval and processing
- **Integrate** with external systems (QuickBooks, etc.)
- **Provide analytics** and reporting capabilities

## 🏗️ Architecture

### Modern Tech Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy
- **Database**: PostgreSQL with Alembic migrations
- **Cache**: Redis for performance optimization
- **Queue**: Celery with Redis broker
- **Frontend**: React with TypeScript
- **Containerization**: Docker & Docker Compose
- **Testing**: Pytest with comprehensive coverage

### Key Features
- ✅ **Email Integration** - Gmail OAuth and IMAP support
- ✅ **AI-Powered Extraction** - LLM-based invoice data extraction
- ✅ **Workflow Management** - Configurable approval workflows
- ✅ **Multi-Provider Support** - Email, QuickBooks, N8N integrations
- ✅ **Real-time Processing** - WebSocket-based updates
- ✅ **Comprehensive API** - RESTful API with OpenAPI docs
- ✅ **Security First** - JWT auth, RBAC, encryption
- ✅ **Monitoring** - Prometheus metrics, structured logging

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Docker & Docker Compose (optional)

### Development Setup

```bash
# 1. Clone the repository
git clone <repository-url>
cd ap_intake

# 2. Run the automated setup
chmod +x scripts/setup/dev-setup.sh
./scripts/setup/dev-setup.sh

# 3. Start the development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Setup

```bash
# Using development configuration
docker-compose -f config/docker/docker-compose.yml up -d

# Using production configuration
docker-compose -f config/docker/docker-compose.prod.yml up -d
```

## 📁 Project Structure

```
ap_intake/
├── 📁 app/                    # Main application code
│   ├── 📁 api/               # API endpoints and routing
│   ├── 📁 core/               # Core configuration and utilities
│   ├── 📁 db/                 # Database models and sessions
│   ├── 📁 models/             # SQLAlchemy model definitions
│   ├── 📁 services/           # Business logic and services
│   ├── 📁 utils/              # Utility modules (NEW!)
│   └── 📁 workers/            # Background task workers
├── 📁 config/                 # Configuration files
│   ├── 📁 environments/       # Environment-specific configs
│   ├── 📁 docker/             # Docker configurations
│   └── 📁 database/           # Database configurations
├── 📁 docs/                   # 📚 Documentation
│   ├── 📁 architecture/         # System architecture docs
│   ├── 📁 guides/              # Setup and usage guides
│   └── 📁 summaries/           # Implementation summaries
├── 📁 scripts/                # 🛠️ Utility scripts
│   ├── 📁 setup/              # Development setup scripts
│   ├── 📁 deployment/         # Deployment scripts
│   └── 📁 production/         # Production utilities
├── 📁 tests/                  # 🧪 Test suite
│   ├── 📁 fixtures/           # Test data and fixtures
│   ├── 📁 e2e/               # End-to-end tests
│   └── 📁 unit/               # Unit tests
├── 📁 web/                    # Frontend application
└── 📁 examples/               # Example configurations
```

## 📚 Documentation

### 🎯 Essential Reading
- **[📖 Documentation Hub](docs/README.md)** - Complete documentation index
- **[🏗️ Architecture Overview](docs/architecture/COMPREHENSIVE_CODEBASE_REFACTORING_PLAN.md)** - System design
- **[🛠️ Developer Experience](docs/architecture/DEVELOPER_EXPERIENCE_IMPROVEMENTS.md)** - DX improvements
- **[📋 Implementation Roadmap](docs/architecture/REFACTORING_IMPLEMENTATION_ROADMAP.md)** - Progress tracking

### 🚀 Setup Guides
- **[📧 Gmail Setup](docs/guides/GMAIL_OAUTH_SETUP.md)** - Email integration
- **[🏭 Production Setup](docs/guides/PRODUCTION_EMAIL_SETUP.md)** - Production deployment
- **[⚡ Quick Setup](docs/guides/STREAMLINED_GMAIL_SETUP.md)** - Simplified setup

### 📊 Progress Reports
- **[📈 Implementation Summaries](docs/summaries/)** - All progress summaries
- **[🔄 Refactoring Progress](docs/summaries/REFACTORING_IMPLEMENTATION_SUMMARY.md)** - Current status

## 🛠️ Development

### Code Quality Tools
```bash
# Code formatting
uv run black app/

# Type checking
uv run mypy app/

# Linting
uv run flake8 app/

# Testing with coverage
uv run pytest --cov=app tests/
```

### Pre-commit Hooks
```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Environment Variables
```bash
# Copy example configuration
cp config/environments/.env.example .env

# Edit with your settings
vim .env
```

## 🧪 Testing

### Run Tests
```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=app --cov-report=html

# Specific test file
uv run pytest tests/test_invoice_processing.py -v
```

### Test Structure
- **Unit Tests**: `tests/unit/` - Individual component tests
- **Integration Tests**: `tests/integration/` - Service integration tests
- **E2E Tests**: `tests/e2e/` - End-to-end workflow tests
- **Fixtures**: `tests/fixtures/` - Test data and configurations

## 🚀 Deployment

### Development
```bash
# Using Docker Compose
docker-compose -f config/docker/docker-compose.yml up -d

# Using uvicorn directly
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Production
```bash
# Production Docker setup
docker-compose -f config/docker/docker-compose.prod.yml up -d

# With environment file
docker-compose -f config/docker/docker-compose.prod.yml --env-file .env up -d
```

### Environment Configuration
- **Development**: `config/environments/.env.development`
- **Testing**: `config/environments/.env.test`
- **Production**: `config/environments/.env.production`

## 🔧 Configuration

### Key Configuration Files
- **`pyproject.toml`** - Python dependencies and project metadata
- **`config/database/alembic.ini`** - Database migration configuration
- **`config/docker/docker-compose.yml`** - Development container setup
- **`config/environments/.env.example`** - Environment variable template

### Database Migrations
```bash
# Create new migration
uv run alembic revision --autogenerate -m "Description"

# Apply migrations
uv run alembic upgrade head

# Rollback migration
uv run alembic downgrade -1
```

## 📊 Monitoring & Logging

### Application Logs
```bash
# View application logs
tail -f logs/app.log

# View worker logs
tail -f logs/worker.log
```

### Health Checks
- **API Health**: `GET /health` - Application health status
- **Database Health**: `GET /health/db` - Database connectivity
- **Redis Health**: `GET /health/redis` - Cache connectivity

### Metrics
- **Prometheus**: `/metrics` - Application metrics
- **Performance**: Built-in performance monitoring
- **Error Tracking**: Structured error logging

## 🔐 Security

### Authentication & Authorization
- **JWT Tokens**: Secure token-based authentication
- **RBAC**: Role-based access control
- **OAuth Integration**: Gmail, QuickBooks OAuth flows
- **API Keys**: Secure API key management

### Data Protection
- **Encryption**: Sensitive data encryption at rest
- **Input Validation**: Comprehensive input sanitization
- **SQL Injection Prevention**: Parameterized queries
- **XSS Protection**: Output encoding and CSP headers

## 🤝 Contributing

### Development Workflow
1. **Fork** the repository
2. **Create** feature branch (`git checkout -b feature/amazing-feature`)
3. **Run** development setup (`./scripts/setup/dev-setup.sh`)
4. **Make** changes with tests
5. **Run** tests and linting (`uv run pytest && uv run black app/`)
6. **Commit** changes (`git commit -m 'Add amazing feature'`)
7. **Push** to branch (`git push origin feature/amazing-feature`)
8. **Create** Pull Request

### Code Standards
- **Python**: Follow PEP 8, use type hints
- **Documentation**: Comprehensive docstrings
- **Testing**: Maintain 85%+ coverage
- **Security**: Follow security best practices

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Documentation
- **[📚 Full Documentation](docs/README.md)** - Complete guide
- **[🔧 Setup Guides](docs/guides/)** - Step-by-step setup
- **[🏗️ Architecture](docs/architecture/)** - System design

### Community
- **Issues**: [GitHub Issues](https://github.com/your-org/ap-intake/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/ap-intake/discussions)
- **Wiki**: [GitHub Wiki](https://github.com/your-org/ap-intake/wiki)

---

## 🎉 Quick Links

| 🎯 Purpose | 🔗 Link |
|-------------|---------|
| **📖 Documentation** | [docs/README.md](docs/README.md) |
| **🚀 Quick Start** | [scripts/setup/dev-setup.sh](scripts/setup/dev-setup.sh) |
| **🏗️ Architecture** | [docs/architecture/](docs/architecture/) |
| **📊 Progress** | [docs/summaries/](docs/summaries/) |
| **🧪 Testing** | [tests/](tests/) |
| **⚙️ Configuration** | [config/](config/) |

---

**Version**: 1.0.0  
**Last Updated**: 2025-11-25  
**Maintainers**: AP Intake Development Team