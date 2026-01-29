"""
Dagster Pipeline for Invoice Processing

Pipeline steps:
1. fetch_invoices - Load invoices from database
2. generate_embeddings - Create vector embeddings for semantic search
3. index_to_qdrant - Push vectors to Qdrant vector database
4. generate_report - Create weekly analysis report

Run with: dagster job execute -f ai/dagster/pipelines.py
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import dagster as dg
from pydantic import BaseModel


# ============================================================================
# Configuration
# ============================================================================

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///invoices.db")


# ============================================================================
# Data Models
# ============================================================================


class InvoiceRow(BaseModel):
    """Invoice data from database."""
    id: str
    vendor_name: str
    invoice_number: str
    total_amount: float
    currency: str
    invoice_date: Optional[str] = None
    status: str
    extracted_data: Optional[str] = None


class EmbeddedInvoice(BaseModel):
    """Invoice with embedding."""
    invoice_id: str
    tenant_id: str
    vendor_name: str
    invoice_number: str
    total_amount: float
    currency: str
    invoice_date: Optional[str] = None
    status: str
    extracted_text: str
    embedding: list[float]


# ============================================================================
# Assets
# ============================================================================


@dg.asset
def raw_invoices(context: dg.AssetExecutionContext) -> pd.DataFrame:
    """
    Fetch invoices from database for processing.

    Returns DataFrame with invoice data.
    """
    context.log.info("Fetching invoices from database")

    # Simulated database fetch - replace with actual DB query
    # In production, connect to Drizzle/SQLite
    mock_data = [
        {
            "id": "inv-001",
            "vendor_name": "Uber Technologies",
            "invoice_number": "INV-2024-001",
            "total_amount": 156.50,
            "currency": "USD",
            "invoice_date": "2024-01-15",
            "status": "APPROVED",
            "extracted_data": json.dumps({
                "ride_trips": 12,
                "business_purpose": "Client meetings",
                "department": "Sales"
            }),
        },
        {
            "id": "inv-002",
            "vendor_name": "AWS",
            "invoice_number": "AWS-12345",
            "total_amount": 2450.00,
            "currency": "USD",
            "invoice_date": "2024-01-20",
            "status": "PENDING",
            "extracted_data": json.dumps({
                "services": ["EC2", "S3", "RDS"],
                "usage_type": "Production",
                "region": "us-east-1"
            }),
        },
        {
            "id": "inv-003",
            "vendor_name": "Slack Technologies",
            "invoice_number": "SLACK-789",
            "total_amount": 850.00,
            "currency": "USD",
            "invoice_date": "2024-01-25",
            "status": "APPROVED",
            "extracted_data": json.dumps({
                "seats": 25,
                "plan": "Business+",
                "billing_period": "Monthly"
            }),
        },
    ]

    df = pd.DataFrame(mock_data)
    context.log.info(f"Fetched {len(df)} invoices")
    return df


@dg.asset
def invoice_text_for_embedding(raw_invoices: pd.DataFrame) -> list[EmbeddedInvoice]:
    """
    Prepare invoice text for embedding generation.

    Creates searchable text from invoice fields.
    """
    embedded_invoices = []

    for _, row in raw_invoices.iterrows():
        # Create searchable text
        extracted_data = {}
        if row.get("extracted_data"):
            try:
                extracted_data = json.loads(row["extracted_data"])
            except json.JSONDecodeError:
                pass

        # Build searchable text
        text_parts = [
            f"Vendor: {row['vendor_name']}",
            f"Invoice: {row['invoice_number']}",
            f"Amount: {row['total_amount']} {row['currency']}",
            f"Date: {row['invoice_date'] or 'N/A'}",
            f"Status: {row['status']}",
        ]

        # Add extracted fields
        for key, value in extracted_data.items():
            text_parts.append(f"{key}: {value}")

        embedded_text = " | ".join(text_parts)

        embedded_invoices.append(
            EmbeddedInvoice(
                invoice_id=row["id"],
                tenant_id="default",  # Get from context in production
                vendor_name=row["vendor_name"],
                invoice_number=row["invoice_number"],
                total_amount=row["total_amount"],
                currency=row["currency"],
                invoice_date=row["invoice_date"],
                status=row["status"],
                extracted_text=embedded_text,
                embedding=[],  # Will be filled by next asset
            )
        )

    return embedded_invoices


@dg.asset
def generate_embeddings(
    context: dg.AssetExecutionContext,
    invoice_text_for_embedding: list[EmbeddedInvoice],
) -> list[EmbeddedInvoice]:
    """
    Generate vector embeddings for invoices using FastEmbed.

    Uses BAAI/bge-small-en-v1.5 model for high-quality embeddings.
    """
    from app.services.qdrant import get_qdrant_service

    context.log.info(f"Generating embeddings for {len(invoice_text_for_embedding)} invoices")

    # Initialize Qdrant service for embedding
    qdrant = get_qdrant_service()

    # Extract texts
    texts = [inv.extracted_text for inv in invoice_text_for_embedding]

    # Generate embeddings in batch
    embeddings = qdrant.generate_embeddings_batch(texts)

    # Attach embeddings to invoices
    for invoice, embedding in zip(invoice_text_for_embedding, embeddings):
        invoice.embedding = embedding

    context.log.info(f"Generated {len(embeddings)} embeddings, dim={len(embeddings[0])}")

    return invoice_text_for_embedding


@dg.asset
def index_to_qdrant(
    context: dg.AssetExecutionContext,
    generate_embeddings: list[EmbeddedInvoice],
) -> dict:
    """
    Index invoice vectors to Qdrant.

    Creates collection if needed and upserts all invoice vectors.
    """
    from app.services.qdrant import get_qdrant_service, InvoiceDocument

    context.log.info(f"Indexing {len(generate_embeddings)} invoices to Qdrant")

    qdrant = get_qdrant_service()

    # Ensure collection exists
    if not qdrant.ensure_collection():
        raise Exception("Failed to create Qdrant collection")

    # Convert to document format
    documents = []
    for emb_inv in generate_embeddings:
        doc = InvoiceDocument(
            invoice_id=emb_inv.invoice_id,
            tenant_id=emb_inv.tenant_id,
            vendor_name=emb_inv.vendor_name,
            invoice_number=emb_inv.invoice_number,
            total_amount=emb_inv.total_amount,
            currency=emb_inv.currency,
            invoice_date=emb_inv.invoice_date,
            status=emb_inv.status,
            extracted_text=emb_inv.extracted_text,
        )
        documents.append(doc)

    # Upsert in batch
    successful, failed = qdrant.upsert_invoices_batch(documents)

    context.log.info(f"Indexed {successful} invoices, {failed} failed")

    return {
        "indexed": successful,
        "failed": failed,
        "total": len(generate_embeddings),
    }


@dg.asset
def vendor_stats(index_to_qdrant: dict, raw_invoices: pd.DataFrame) -> pd.DataFrame:
    """
    Generate vendor statistics from indexed invoices.

    Used for weekly reports and analytics.
    """
    # Group by vendor and calculate stats
    stats = raw_invoices.groupby("vendor_name").agg(
        total_amount=("total_amount", "sum"),
        invoice_count=("id", "count"),
        avg_amount=("total_amount", "mean"),
    ).reset_index()

    stats.columns = ["vendor", "total_spend", "invoice_count", "avg_amount"]
    return stats


@dg.asset
def weekly_report(
    context: dg.AssetExecutionContext,
    vendor_stats: pd.DataFrame,
) -> str:
    """
    Generate markdown weekly report.

    Includes vendor spending and invoice metrics.
    """
    total_spend = vendor_stats["total_spend"].sum()
    total_invoices = vendor_stats["invoice_count"].sum()
    top_vendor = vendor_stats.loc[vendor_stats["total_spend"].idxmax()]

    report = f"""# Weekly Invoice Report
Generated: {datetime.now().isoformat()}

## Summary
- **Total Spend**: ${total_spend:,.2f}
- **Total Invoices**: {total_invoices}
- **Average Invoice**: ${total_spend / total_invoices:,.2f}

## Top Vendor
- **{top_vendor['vendor']}**: ${top_vendor['total_spend']:,.2f} ({top_vendor['invoice_count']} invoices)

## Vendor Breakdown
| Vendor | Total Spend | Invoices | Avg Amount |
|--------|-------------|----------|------------|
"""

    for _, row in vendor_stats.iterrows():
        report += f"| {row['vendor']} | ${row['total_spend']:,.2f} | {row['invoice_count']} | ${row['avg_amount']:,.2f} |\n"

    context.log.info("Generated weekly report")
    return report


# ============================================================================
# Job Definition
# ============================================================================


@dg.job
def invoice_pipeline():
    """
    Main invoice processing pipeline.

    Flow:
    raw_invoices -> invoice_text_for_embedding -> generate_embeddings -> index_to_qdrant
                                                                 |
                                                                 v
                                                          vendor_stats -> weekly_report
    """
    raw_invoices_result = raw_invoices()
    text_result = invoice_text_for_embedding(raw_invoices_result)
    embedding_result = generate_embeddings(text_result)
    qdrant_result = index_to_qdrant(embedding_result)
    stats_result = vendor_stats(qdrant_result, raw_invoices_result)
    weekly_report(stats_result)


# ============================================================================
# Schedule
# ============================================================================


@dg.job(schedule={"cron_schedule": "0 9 * * 1"})  # Monday 9am
def weekly_invoice_pipeline():
    """Weekly pipeline run."""
    invoice_pipeline()


# ============================================================================
# Sensor (for event-driven)
# ============================================================================


@dg.sensor
def new_invoice_sensor(context: dg.SensorExecutionContext):
    """
    Sensor for new invoice events from Redpanda.

    Triggers pipeline when new invoices are published.
    """
    # In production, check Redpanda for new events
    # For now, return no runs
    return dg.RunRequest(key=None, run_key=None, tags={})
