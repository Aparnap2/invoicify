"""Ollama client using OpenAI SDK for OpenAI-compatible API."""

import logging
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)


class OllamaChatResponse(BaseModel):
    """Response from Ollama chat endpoint."""
    model: str
    message: dict
    done: bool
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    eval_count: Optional[int] = None


class OllamaEmbedResponse(BaseModel):
    """Response from Ollama embed endpoint."""
    embeddings: list[list[float]]
    total_duration: Optional[int] = None


class OllamaClient:
    """Client for interacting with Ollama using OpenAI SDK."""

    def __init__(self, base_url: Optional[str] = None, api_key: str = "ollama"):
        """Initialize the Ollama client."""
        settings = get_settings()
        self.base_url = base_url or f"{settings.ollama_base_url}/v1"
        self.timeout = 120.0

        # Use OpenAI SDK with custom base URL for Ollama compatibility
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=api_key,  # Ollama doesn't require real API key
            timeout=self.timeout,
        )

    async def chat(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
    ) -> OllamaChatResponse:
        """Send a chat request to Ollama."""
        # Strip "ollama/" prefix if present for model name
        model_name = model.replace("ollama/", "")

        response = await self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=stream,
        )

        # Convert OpenAI response to our format
        return OllamaChatResponse(
            model=response.model,
            message={"role": response.choices[0].message.role, "content": response.choices[0].message.content},
            done=response.choices[0].finish_reason == "stop",
        )

    async def ask(self, prompt: str, model: Optional[str] = None) -> str:
        """Simple Q&A interface."""
        settings = get_settings()
        model_name = (model or settings.llm_model).replace("ollama/", "")

        messages = [{"role": "user", "content": prompt}]
        response = await self.client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
    ) -> dict:
        """Generate text using Ollama (via completions endpoint)."""
        model_name = model.replace("ollama/", "")

        response = await self.client.completions.create(
            model=model_name,
            prompt=prompt,
            stream=stream,
        )
        return {
            "response": response.choices[0].text,
            "model": response.model,
        }

    async def embed(
        self,
        model: str,
        input_text: str | list[str],
    ) -> OllamaEmbedResponse:
        """Generate embeddings using Ollama."""
        model_name = model.replace("ollama/", "")

        response = await self.client.embeddings.create(
            model=model_name,
            input=input_text,
        )

        return OllamaEmbedResponse(
            embeddings=[d.embedding for d in response.data],
        )

    async def embed_single(self, text: str, model: Optional[str] = None) -> list[float]:
        """Generate embedding for a single text string."""
        settings = get_settings()
        embed_model = (model or settings.embedding_model).replace("ollama/", "")

        response = await self.client.embeddings.create(
            model=embed_model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_batch(
        self,
        texts: list[str],
        model: Optional[str] = None,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        settings = get_settings()
        embed_model = (model or settings.embedding_model).replace("ollama/", "")

        response = await self.client.embeddings.create(
            model=embed_model,
            input=texts,
        )
        return [d.embedding for d in response.data]

    async def list_models(self) -> list[str]:
        """List available models in Ollama."""
        try:
            response = await self.client.models.list()
            return [m.id for m in response.data]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []


# Singleton instance
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get the singleton Ollama client instance."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client
