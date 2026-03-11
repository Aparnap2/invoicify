"""
Telegram Bot MCP Server — FREE unlimited invoice entrypoint

Vendors send invoice PDFs via Telegram → Azure Blob → AP Pipeline → QuickBooks/HubSpot

Setup:
1. Message @BotFather on Telegram
2. /newbot → "InvoicifyBot" → get BOT_TOKEN
3. Add TELEGRAM_BOT_TOKEN to .env

Cost: $0 forever (Telegram Bot API is free unlimited)
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional
from datetime import datetime

import httpx
import structlog
from mcp.server import FastMCP

logger = structlog.get_logger()

# Initialize MCP server
mcp = FastMCP("telegram")

# Config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""


@mcp.tool()
async def telegram_receive_invoice(
    file_id: str,
    chat_id: str,
    sender_username: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Vendor sends invoice PDF via Telegram → process through AP pipeline.
    
    Args:
        file_id: Telegram file ID from message.document
        chat_id: Telegram chat ID for replies
        sender_username: Telegram username (optional)
    
    Returns:
        {
            "trace_id": str,
            "blob_url": str,
            "status": "processing" | "completed" | "failed",
            "invoice_number": Optional[str],
        }
    """
    trace_id = str(uuid.uuid4())
    log = logger.bind(trace_id=trace_id, chat_id=chat_id)
    
    if not BOT_TOKEN:
        log.error("telegram_bot_token_missing")
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")
    
    try:
        # 1. Download file from Telegram
        log.info("telegram_download_started")
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get file info
            resp = await client.get(
                f"{TELEGRAM_BASE_URL}/getFile",
                params={"file_id": file_id},
            )
            resp.raise_for_status()
            file_info = resp.json()["result"]
            file_path = file_info["file_path"]
            
            # Download file bytes
            file_resp = await client.get(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            )
            file_resp.raise_for_status()
            file_bytes = file_resp.read()
        
        log.info(
            "telegram_download_complete",
            file_size=len(file_bytes),
            file_name=file_info.get("file_name", "unknown"),
        )
        
        # 2. Upload to Azure Blob (lazy import to avoid circular deps)
        from src.storage.azure_blob import upload_pdf_bytes
        
        blob_name = f"invoices/telegram/{datetime.now().strftime('%Y/%m')}/{trace_id}.pdf"
        blob_url = await upload_pdf_bytes(
            file_bytes,
            blob_name,
            metadata={
                "source": "telegram",
                "chat_id": chat_id,
                "sender": sender_username,
            }
        )
        
        log.info("azure_blob_uploaded", blob_url=blob_url)
        
        # 3. Run AP workflow pipeline (lazy import)
        from src.graph.ap_workflow import ap_workflow
        
        log.info("ap_workflow_started")
        result = await ap_workflow.ainvoke({
            "trace_id": trace_id,
            "pdf_url": blob_url,
            "source": "telegram",
        })
        
        invoice_number = result.get("extracted_invoice", {}).get("invoice_number")
        status = result.get("final_decision", "processing")
        
        log.info(
            "ap_workflow_complete",
            invoice_number=invoice_number,
            status=status,
        )
        
        # 4. Send status update to vendor
        await send_telegram_message(
            chat_id,
            f"✅ Invoice #{invoice_number} processing complete!\n\n"
            f"Status: {status}\n"
            f"QuickBooks Bill ID: {result.get('quickbooks_bill_id', 'N/A')}\n"
            f"HubSpot Deal ID: {result.get('hubspot_deal_id', 'N/A')}"
        )
        
        return {
            "trace_id": trace_id,
            "blob_url": blob_url,
            "status": status,
            "invoice_number": invoice_number,
        }
        
    except httpx.HTTPStatusError as e:
        log.error("telegram_api_error", status_code=e.response.status_code, error=str(e))
        await send_telegram_message(
            chat_id,
            f"❌ Error processing invoice: {e.response.status_code}"
        )
        raise
    
    except Exception as e:
        log.error("invoice_processing_failed", error=str(e))
        await send_telegram_message(
            chat_id,
            f"❌ Invoice processing failed. Please contact support."
        )
        raise


@mcp.tool()
async def telegram_send_message(
    chat_id: str,
    text: str,
    parse_mode: str = "Markdown",
) -> Dict[str, Any]:
    """
    Send status update to vendor via Telegram.
    
    Args:
        chat_id: Telegram chat ID
        text: Message text (supports Markdown)
        parse_mode: "Markdown" | "HTML" | None
    
    Returns:
        Telegram API response
    """
    return await send_telegram_message(chat_id, text, parse_mode)


async def send_telegram_message(
    chat_id: str,
    text: str,
    parse_mode: str = "Markdown",
) -> Dict[str, Any]:
    """Send message to Telegram chat."""
    if not BOT_TOKEN:
        logger.warning("telegram_bot_token_missing")
        return {"ok": False, "error": "BOT_TOKEN not configured"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{TELEGRAM_BASE_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        
        logger.info(
            "telegram_message_sent",
            chat_id=chat_id,
            message_id=result["result"]["message_id"],
        )
        
        return result


# CLI entry point for testing
if __name__ == "__main__":
    import sys
    
    if "--test" in sys.argv:
        # Run quick test
        print("Telegram MCP Server - Test Mode")
        print(f"BOT_TOKEN configured: {bool(BOT_TOKEN)}")
        print(f"TELEGRAM_BASE_URL: {TELEGRAM_BASE_URL[:50] if TELEGRAM_BASE_URL else 'N/A'}...")
        print("✅ Server ready")
    else:
        # Run MCP server
        mcp.run()
