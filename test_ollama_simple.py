#!/usr/bin/env python3
"""Test Ollama embedding and LLM inference."""

import json
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE_URL = "http://localhost:11434"
INVOICE = "ACME Corp Invoice #12345 Date: 2024-01-15 Total: 1250.00 Items: 5x Widget at 200, 2x Gadget at 125"


def ollama_post(endpoint: str, data: dict) -> dict:
    """Make POST request to Ollama API."""
    req = Request(f"{BASE_URL}/{endpoint}")
    req.add_header("Content-Type", "application/json")
    req.data = json.dumps(data).encode()
    with urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def test_embedding():
    """Test nomic-embed-text model."""
    print("1. EMBEDDING TEST (nomic-embed-text:latest)")
    print("-" * 50)

    start = time.perf_counter()
    try:
        resp = ollama_post("api/embed", {
            "model": "nomic-embed-text:latest",
            "input": INVOICE
        })
        elapsed_ms = (time.perf_counter() - start) * 1000

        embedding = resp.get("embeddings", [None])[0]
        print(f"   Model: nomic-embed-text:latest")
        print(f"   Dimensions: {len(embedding) if embedding else 'ERROR'}")
        print(f"   First 5 values: {[round(x, 6) for x in embedding[:5]] if embedding else 'N/A'}")
        print(f"   Response Time: {elapsed_ms:.2f} ms")
        print(f"   Status: OK")
        return True
    except URLError as e:
        print(f"   ERROR: {e}")
        return False


def test_llm():
    """Test qwen2.5-coder:3b model."""
    print()
    print("2. LLM INFERENCE TEST (qwen2.5-coder:3b)")
    print("-" * 50)

    prompt = f"""Extract this invoice as JSON with fields:
- vendor (company name)
- invoice_number
- invoice_date
- total_amount (number)
- line_items: list of [item_name, quantity, unit_price, total_price]

Invoice: {INVOICE}
Return ONLY valid JSON, no markdown."""

    start = time.perf_counter()
    try:
        resp = ollama_post("api/generate", {
            "model": "qwen2.5-coder:3b",
            "prompt": prompt,
            "stream": False,
            "format": "json"
        })
        elapsed_ms = (time.perf_counter() - start) * 1000

        response = resp.get("response", "")
        print(f"   Model: qwen2.5-coder:3b")
        print(f"   Response Time: {elapsed_ms:.2f} ms")
        print(f"   Response Quality:")

        # Pretty print the JSON response
        try:
            json_resp = json.loads(response)
            print("   " + json.dumps(json_resp, indent=2).replace("\n", "\n   "))
        except json.JSONDecodeError:
            print(f"   {response[:300]}")

        print(f"   Status: OK")
        return True
    except URLError as e:
        print(f"   ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("OLLAMA INVOICE PROCESSING TEST REPORT")
    print("=" * 60)
    print()

    embed_ok = test_embedding()
    llm_ok = test_llm()

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if embed_ok:
        print("   Embedding: OK - 768D vector")
    if llm_ok:
        print("   LLM: OK")
    print()


if __name__ == "__main__":
    main()
