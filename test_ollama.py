#!/usr/bin/env python3
"""Test Ollama embedding and LLM inference for invoice processing."""

import time
import httpx
from typing import Any

OLLAMA_BASE_URL = "http://localhost:11434"

SAMPLE_INVOICE = """ACME Corp
Invoice #12345
Date: 2024-01-15
Total: $1,250.00
Items: 5x Widget @ $200, 2x Gadget @ $125"""

INVOICE_EXTRACTION_PROMPT = """Extract the following information from this invoice as JSON:
- vendor: company name
- invoice_number
- invoice_date
- total_amount (as number, not string)
- line_items: list of objects with item_name, quantity, unit_price, total_price

Invoice:
{ACME Corp
Invoice #12345
Date: 2024-01-15
Total: $1,250.00
Items: 5x Widget @ $200, 2x Gadget @ $125}"""


async def test_embedding() -> dict[str, Any]:
    """Test embedding generation with nomic-embed-text:latest"""
    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": "nomic-embed-text:latest",
                "input": SAMPLE_INVOICE,
            },
        )
        response.raise_for_status()
        data = response.json()

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    embeddings = data.get("embeddings", [])
    embedding = embeddings[0] if embeddings else []

    return {
        "model": "nomic-embed-text:latest",
        "dimensions": len(embedding),
        "first_5_values": embedding[:5] if embedding else [],
        "response_time_ms": round(elapsed_ms, 2),
        "full_response": data,
    }


async def test_llm_inference() -> dict[str, Any]:
    """Test LLM inference with qwen2.5-coder:3b"""
    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "qwen2.5-coder:3b",
                "prompt": INVOICE_EXTRACTION_PROMPT,
                "stream": False,
                "format": "json",
            },
        )
        response.raise_for_status()
        data = response.json()

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return {
        "model": "qwen2.5-coder:3b",
        "response": data.get("response", ""),
        "response_time_ms": round(elapsed_ms, 2),
        "done": data.get("done", False),
    }


async def main() -> None:
    print("=" * 60)
    print("OLLAMA INVOICE PROCESSING TEST REPORT")
    print("=" * 60)
    print()

    # Test 1: Embedding
    print("1. EMBEDDING TEST (nomic-embed-text:latest)")
    print("-" * 50)
    try:
        embedding_result = await test_embedding()
        print(f"   Model: {embedding_result['model']}")
        print(f"   Dimensions: {embedding_result['dimensions']}")
        print(f"   First 5 values: {embedding_result['first_5_values']}")
        print(f"   Response Time: {embedding_result['response_time_ms']:.2f} ms")
    except Exception as e:
        print(f"   ERROR: {e}")
        embedding_result = None

    print()

    # Test 2: LLM Inference
    print("2. LLM INFERENCE TEST (qwen2.5-coder:3b)")
    print("-" * 50)
    try:
        llm_result = await test_llm_inference()
        print(f"   Model: {llm_result['model']}")
        print(f"   Response Time: {llm_result['response_time_ms']:.2f} ms")
        print(f"   Response Quality:")
        print(f"   {llm_result['response']}")
    except Exception as e:
        print(f"   ERROR: {e}")
        llm_result = None

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if embedding_result:
        print(f"   Embedding: OK - {embedding_result['dimensions']}D vector in {embedding_result['response_time_ms']:.2f}ms")
    if llm_result:
        print(f"   LLM: OK - Response in {llm_result['response_time_ms']:.2f}ms")
    print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
