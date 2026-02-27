FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    transformers \
    torch \
    torchaudio \
    fastapi \
    uvicorn \
    python-multipart \
    soundfile \
    librosa \
    numpy

COPY server.py .

EXPOSE 8881

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8881"]
