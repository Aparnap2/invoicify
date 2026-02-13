# apps/agent-core/Dockerfile
FROM python:3.11-slim

# Install system dependencies for PDF processing (Docling requirements)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    libmagic1 \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install Python dependencies
RUN uv sync --frozen

# Copy source code
COPY src ./src

# Create a symlink or just make sure src is on PYTHONPATH
ENV PYTHONPATH=/app

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
