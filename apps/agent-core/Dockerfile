# apps/agent-core/Dockerfile — Azure Container Apps build
# Removed: poppler-utils, tesseract (not needed with Azure Document Intelligence)
# Azure DI accepts raw PDF bytes via REST; no local OCR toolchain required.

FROM python:3.11-slim

# Minimal system deps (libmagic for MIME detection; gcc for some wheel builds)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock* ./

# Install Python dependencies
RUN uv sync --frozen

# Copy source code
COPY src ./src

ENV PYTHONPATH=/app

# Health check for Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
