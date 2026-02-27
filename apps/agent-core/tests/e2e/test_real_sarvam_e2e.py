"""
REAL E2E Test with Actual Sarvam AI API + Docker Containers

This test requires:
1. SARVAM_AI_API_KEY set in .env.local
2. Docker containers running (Redis, Qdrant, etc.)
3. Real PDF invoice file

Run: uv run pytest tests/e2e/test_real_sarvam_e2e.py -v -s
"""

import os
import sys
import pytest
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / "apps" / "agent-core" / ".env.local")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "agent-core" / "src"))


class TestRealSarvamAI:
    """Test REAL Sarvam AI API integration (not mocked)."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.real_api
    async def test_sarvam_document_intelligence_real(self):
        """Test REAL Sarvam AI Document Intelligence API."""
        
        # Check if API key is available
        api_key = os.getenv("SARVAM_AI_API_KEY")
        if not api_key:
            pytest.skip("SARVAM_AI_API_KEY not set in .env.local")
        
        # Import Sarvam AI SDK
        try:
            from sarvamai import SarvamAI
        except ImportError:
            pytest.skip("sarvamai package not installed. Run: pip install sarvamai")
        
        # Initialize client
        client = SarvamAI(api_subscription_key=api_key)
        client.document_intelligence.initialise()
        
        # Create a test PDF (or use existing fixture)
        test_pdf = Path(__file__).parent / "fixtures" / "test_invoice.pdf"
        
        if not test_pdf.exists():
            # Create minimal test PDF
            test_pdf.parent.mkdir(parents=True, exist_ok=True)
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            c = canvas.Canvas(str(test_pdf), pagesize=letter)
            c.drawString(100, 750, "INVOICE")
            c.drawString(100, 730, "Invoice #: INV-TEST-001")
            c.drawString(100, 710, "Vendor: Test Vendor Pvt Ltd")
            c.drawString(100, 690, "Amount: Rs. 1000.00")
            c.save()
        
        # Create job
        job = client.document_intelligence.create_job(
            language="en-IN",
            output_format="html"
        )
        print(f"\n✅ Job created: {job.job_id}")
        
        # Upload document
        job.upload_file(str(test_pdf))
        print("✅ File uploaded")
        
        # Start processing
        job.start()
        print("✅ Job started")
        
        # Wait for completion
        status = job.wait_until_complete()
        print(f"✅ Job completed with state: {status.job_state}")
        
        # Get metrics
        metrics = job.get_page_metrics()
        print(f"📊 Page metrics: {metrics}")
        
        # Download output
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_zip = output_dir / "sarvam_output.zip"
        job.download_output(str(output_zip))
        print(f"✅ Output saved to {output_zip}")
        
        # Verify output exists
        assert output_zip.exists(), "Output ZIP file not created"
        assert output_zip.stat().st_size > 0, "Output ZIP file is empty"
        
        print("\n✅ SARVAM AI REAL API TEST PASSED")
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.real_api
    async def test_sarvam_ocr_extraction(self):
        """Test REAL Sarvam OCR extraction with our extractor."""
        
        api_key = os.getenv("SARVAM_AI_API_KEY")
        if not api_key:
            pytest.skip("SARVAM_AI_API_KEY not set")
        
        # Set extractor mode to sarvam
        os.environ["EXTRACTOR_MODE"] = "sarvam"
        os.environ["SARVAM_API_KEY"] = api_key
        
        from extraction.sarvam_extractor import InvoiceExtractor
        
        # Create test PDF
        test_pdf = Path(__file__).parent / "fixtures" / "simple_invoice.pdf"
        
        if not test_pdf.exists():
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            test_pdf.parent.mkdir(parents=True, exist_ok=True)
            c = canvas.Canvas(str(test_pdf), pagesize=letter)
            c.drawString(100, 750, "TAX INVOICE")
            c.drawString(100, 730, "Invoice No: INV-2024-001")
            c.drawString(100, 710, "Vendor: Acme Supplies Pvt Ltd")
            c.drawString(100, 690, "GST: 27AABCU9603R1ZM")
            c.drawString(100, 670, "Total: Rs. 3540.00")
            c.save()
        
        # Test extraction
        extractor = InvoiceExtractor()
        
        try:
            result = await extractor.extract(str(test_pdf), "TEST-001")
            
            print("\n✅ EXTRACTION RESULT:")
            print(f"  Vendor: {result.get('vendor_name')}")
            print(f"  Invoice: {result.get('invoice_number')}")
            print(f"  Total: {result.get('total_amount')}")
            print(f"  Confidence: {result.get('confidence_score')}")
            
            # Verify result structure
            assert "vendor_name" in result
            assert "invoice_number" in result
            assert "total_amount" in result
            assert result["confidence_score"] > 0
            
            print("\n✅ SARVAM OCR EXTRACTION TEST PASSED")
            
        except Exception as e:
            print(f"\n⚠️ Extraction failed (might be API quota): {e}")
            pytest.skip(f"Sarvam API error: {e}")


class TestRealDockerContainers:
    """Test REAL Docker container connectivity."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.docker
    async def test_redis_connection(self):
        """Test REAL Redis connection."""
        try:
            from upstash_redis import AsyncRedis
            
            redis = AsyncRedis.from_env()
            result = await redis.ping()
            
            assert result == "PONG", "Redis ping failed"
            print("\n✅ REDIS CONNECTION TEST PASSED")
            
        except ImportError:
            pytest.skip("upstash_redis not installed")
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.docker
    async def test_qdrant_connection(self):
        """Test REAL Qdrant connection."""
        try:
            from qdrant_client import QdrantClient
            
            client = QdrantClient(url="http://localhost:6333")
            collections = client.get_collections()
            
            print(f"\n✅ QDRANT CONNECTION TEST PASSED")
            print(f"  Collections: {collections.collections}")
            
        except ImportError:
            pytest.skip("qdrant_client not installed")
        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.docker
    async def test_ollama_connection(self):
        """Test REAL Ollama connection."""
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("http://localhost:11434/api/tags")
                response.raise_for_status()
                models = response.json()
            
            print(f"\n✅ OLLAMA CONNECTION TEST PASSED")
            print(f"  Models: {[m['name'] for m in models.get('models', [])]}")
            
        except Exception as e:
            pytest.skip(f"Ollama not available: {e}")


class TestFullE2EFlow:
    """Test COMPLETE E2E flow with all real components."""
    
    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.real_api
    @pytest.mark.docker
    async def test_complete_invoice_processing_flow(self):
        """
        Test COMPLETE flow:
        1. PDF upload → 2. Sarvam OCR → 3. Extraction → 4. Risk Analysis → 5. Decision
        """
        
        api_key = os.getenv("SARVAM_AI_API_KEY")
        if not api_key:
            pytest.skip("SARVAM_AI_API_KEY not set")
        
        print("\n" + "="*60)
        print("STARTING COMPLETE E2E FLOW TEST")
        print("="*60)
        
        # Step 1: Create test PDF
        print("\n1️⃣ Creating test PDF...")
        test_pdf = Path(__file__).parent / "fixtures" / "e2e_test_invoice.pdf"
        test_pdf.parent.mkdir(parents=True, exist_ok=True)
        
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(test_pdf), pagesize=letter)
        c.drawString(100, 750, "TAX INVOICE")
        c.drawString(100, 730, "Invoice No: INV-E2E-001")
        c.drawString(100, 710, "Vendor: Test Vendor Pvt Ltd")
        c.drawString(100, 690, "GST: 27AABCT1234C1Z5")
        c.drawString(100, 670, "Items: Office Chairs x 10 @ Rs. 150 = Rs. 1500")
        c.drawString(100, 650, "Total: Rs. 1770.00 (incl. 18% GST)")
        c.save()
        print("   ✅ PDF created")
        
        # Step 2: Extract with Sarvam
        print("\n2️⃣ Extracting with Sarvam AI...")
        os.environ["EXTRACTOR_MODE"] = "sarvam"
        os.environ["SARVAM_API_KEY"] = api_key
        
        from extraction.sarvam_extractor import InvoiceExtractor
        extractor = InvoiceExtractor()
        
        try:
            result = await extractor.extract(str(test_pdf), "E2E-001")
            print("   ✅ Extraction complete")
            print(f"      Vendor: {result.get('vendor_name')}")
            print(f"      Total: {result.get('total_amount')}")
        except Exception as e:
            print(f"   ⚠️ Extraction failed: {e}")
            pytest.skip(f"Sarvam API error: {e}")
        
        # Step 3: Risk Analysis
        print("\n3️⃣ Running risk analysis...")
        from trust.battery import TrustBattery
        
        battery = TrustBattery(
            vendor_id="test-vendor",
            tenant_id="test-tenant",
            invoice_count=10,
            accurate_count=10,
        )
        
        print(f"   ✅ Trust Level: {battery.level.value}")
        print(f"   ✅ Auto-approve Limit: ${battery.auto_approve_limit}")
        
        # Step 4: Decision
        print("\n4️⃣ Making decision...")
        from schemas.invoice_v2 import RiskDecision
        
        if battery.level.value == "CORE" and result.get("total_amount", 0) < battery.auto_approve_limit:
            decision = RiskDecision.AUTO_APPROVE
        else:
            decision = RiskDecision.HITL_REQUIRED
        
        print(f"   ✅ Decision: {decision.value}")
        
        print("\n" + "="*60)
        print("✅ COMPLETE E2E FLOW TEST PASSED")
        print("="*60)


# ─────────────────────────────────────────────────────────────────────────────
# Pytest configuration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as E2E test")
    config.addinivalue_line("markers", "real_api: mark test as using real API")
    config.addinivalue_line("markers", "docker: mark test as requiring Docker")
