FROM python:3.11-slim

# Set environment variables for caching
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CACHE_DIR=/root/.cache/pip \
    UV_CACHE_DIR=/root/.cache/uv

# Create cache directories
RUN mkdir -p /root/.cache/pip /root/.cache/uv

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
        libmagic1 \
        libmagic-dev \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        python3-click \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install uv for fast Python package management
RUN pip install --cache-dir /root/.cache/pip uv

# Copy dependency files first for better caching
COPY pyproject.toml ./

# Install Python dependencies using uv with cache
RUN uv sync --cache-dir /root/.cache/uv

# Install additional dependencies that might be missing
RUN uv add --cache-dir /root/.cache/uv click fastapi uvicorn[standard] pydantic-settings python-multipart

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini ./
COPY test_api_response.py ./

# Create necessary directories
RUN mkdir -p storage exports langgraph_storage logs

# Set permissions for Python scripts
RUN chmod +x scripts/*.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command - use uv run to ensure we're using the virtual environment
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]