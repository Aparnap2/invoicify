# Invoicify AI Service

AI-powered invoice extraction and processing service built with:
- **FastAPI** - Web framework
- **Pydantic v2** - Data validation
- **Pydantic AI** - LLM agent framework
- **LangGraph** - Workflow orchestration

## Setup

```bash
# Create virtual environment with uv
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Run tests
uv run pytest

# Start development server
uv run fastapi dev
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL` | LLM model to use | `openai:gpt-4o` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8001` |
| `DEBUG` | Debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |

## API Endpoints

- `GET /api/v1/health` - Health check
- `POST /api/v1/extract` - Extract invoice data
- `POST /api/v1/process` - Process invoice through workflow
- `POST /api/v1/upload` - Upload invoice file
- `POST /api/v1/approve` - Submit approval decision
- `GET /api/v1/status/{thread_id}` - Get processing status
