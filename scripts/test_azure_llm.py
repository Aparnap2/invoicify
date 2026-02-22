#!/usr/bin/env python3
"""
Test Azure OpenAI connection with correct endpoint configuration.

The key issue: Azure OpenAI endpoint should NOT include /openai/v1 suffix
because AsyncAzureOpenAI SDK adds the API version path automatically.

Correct: https://aparnaopenai.openai.azure.com/
Wrong:   https://aparnaopenai.openai.azure.com/openai/v1

Run:
    python scripts/test_azure_llm.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent-core" / "src"))


async def test_azure_openai_connection():
    """Test Azure OpenAI connection with correct endpoint."""
    from openai import AsyncAzureOpenAI
    
    # Load from .env
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://aparnaopenai.openai.azure.com/")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-oss-120b")
    
    print("="*60)
    print("AZURE OPENAI CONNECTION TEST")
    print("="*60)
    print(f"\nEndpoint: {endpoint}")
    print(f"Deployment: {deployment}")
    print(f"API Key: {api_key[:10]}...{api_key[-5:]}")
    
    # Verify endpoint format
    if "/openai/v1" in endpoint or "/v1" in endpoint:
        print("\n⚠️  WARNING: Endpoint should NOT include /openai/v1 or /v1")
        print("   AsyncAzureOpenAI SDK adds the API version path automatically")
        print("   Correct format: https://<resource>.openai.azure.com/")
    
    # Create client
    client = AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version="2024-08-01-preview",
    )
    
    # Test connection
    print("\nTesting connection...")
    try:
        response = await client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in one word"}
            ],
            max_tokens=10,
            timeout=30.0,
        )
        
        print(f"\n✅ SUCCESS!")
        print(f"   Response: {response.choices[0].message.content}")
        print(f"   Model: {response.model}")
        print(f"   Usage: {response.usage}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        
        # Provide troubleshooting hints
        if "404" in str(e):
            print("\n   Troubleshooting:")
            print("   - Check deployment name exists in Azure portal")
            print("   - Check deployment is in same region as endpoint")
            print("   - Wait 5 minutes after creating deployment")
        elif "401" in str(e):
            print("\n   Troubleshooting:")
            print("   - Check API key is correct")
            print("   - Check key hasn't expired")
        elif "connection" in str(e).lower():
            print("\n   Troubleshooting:")
            print("   - Check endpoint URL is correct")
            print("   - Check network connectivity")
        
        return False


async def test_extractor_agent_with_azure():
    """Test ExtractorAgent with Azure OpenAI."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "agent-core" / "src"))
    
    from agents.extractor_agent import ExtractorAgent
    
    print("\n" + "="*60)
    print("EXTRACTOR AGENT TEST WITH AZURE OPENAI")
    print("="*60)
    
    # Create agent with Azure config
    agent = ExtractorAgent(config={
        "llm_provider": "azure",
        "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-oss-120b"),
    })
    
    # Test with simple markdown
    test_markdown = """
    # Invoice INV-TEST-001
    Vendor: Test Vendor
    Total: $100.00
    """
    
    print("\nTesting extraction...")
    try:
        result = await agent._extract_with_llm(test_markdown)
        print(f"\n✅ Extraction successful!")
        print(f"   Result: {result}")
        return True
    except Exception as e:
        print(f"\n❌ Extraction failed: {e}")
        return False


async def main():
    """Run all tests."""
    # Test 1: Basic Azure OpenAI connection
    test1_passed = await test_azure_openai_connection()
    
    # Test 2: Extractor agent with Azure
    if test1_passed:
        test2_passed = await test_extractor_agent_with_azure()
    else:
        print("\n⚠️  Skipping extractor test (connection failed)")
        test2_passed = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Azure Connection: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"Extractor Agent:  {'✅ PASS' if test2_passed else '❌ FAIL'}")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
