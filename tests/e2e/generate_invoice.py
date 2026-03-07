#!/usr/bin/env python3
"""
Test Invoice PDF Generator for E2E Testing.

Generates realistic test invoice PDFs with configurable parameters
for end-to-end testing of the Invoicify pipeline.

Usage:
    python generate_invoice.py --output test_invoice.pdf
    python generate_invoice.py --vendor "Acme Corp" --amount 1500.00 --output invoice.pdf
"""

import argparse
import hashlib
import io
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass
class InvoiceLineItem:
    """Represents a line item on an invoice."""

    description: str
    quantity: int
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class TestInvoiceData:
    """Test invoice data for PDF generation."""

    vendor_name: str = "Acme Corporation"
    vendor_address: str = "123 Business Street\nSan Francisco, CA 94105"
    vendor_email: str = "billing@acmecorp.com"
    vendor_phone: str = "(555) 123-4567"

    customer_name: str = "Test Company Inc."
    customer_address: str = "456 Client Avenue\nNew York, NY 10001"

    invoice_number: str = "INV-2025-001"
    invoice_date: date = None
    due_date: date = None

    line_items: list = None
    tax_rate: float = 0.0
    notes: str = "Thank you for your business!"

    # Metadata for testing
    trust_level: str = "STANDARD"
    test_id: str = "e2e-test-001"

    def __post_init__(self):
        if self.invoice_date is None:
            self.invoice_date = date.today()
        if self.due_date is None:
            self.due_date = self.invoice_date + timedelta(days=30)
        if self.line_items is None:
            self.line_items = [
                InvoiceLineItem("Professional Services - Consulting", 10, 150.00),
                InvoiceLineItem("Software License - Annual", 1, 500.00),
            ]

    @property
    def subtotal(self) -> float:
        return sum(item.total for item in self.line_items)

    @property
    def tax_amount(self) -> float:
        return self.subtotal * self.tax_rate

    @property
    def total_amount(self) -> float:
        return self.subtotal + self.tax_amount

    @property
    def currency(self) -> str:
        return "USD"


class TestInvoiceGenerator:
    """
    Generates test invoice PDFs for E2E testing.

    Creates realistic-looking invoices with all standard fields
    that the Invoicify pipeline expects to extract.
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize the generator.

        Args:
            output_dir: Directory to save generated PDFs. Defaults to current dir.
        """
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        invoice_data: Optional[TestInvoiceData] = None,
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        Generate a test invoice PDF.

        Args:
            invoice_data: Invoice data to use. Creates default if None.
            output_filename: Output filename. Auto-generates if None.

        Returns:
            Path to the generated PDF file.
        """
        if invoice_data is None:
            invoice_data = TestInvoiceData()

        if output_filename is None:
            output_filename = f"test_invoice_{invoice_data.invoice_number.replace('/', '-')}.pdf"

        output_path = self.output_dir / output_filename

        # Create PDF document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        # Build PDF content
        story = self._build_story(invoice_data)
        doc.build(story)

        # Generate and store hash for verification
        pdf_hash = self._generate_file_hash(output_path)

        # Create metadata file
        metadata = {
            "invoice_number": invoice_data.invoice_number,
            "vendor_name": invoice_data.vendor_name,
            "total_amount": invoice_data.total_amount,
            "invoice_date": invoice_data.invoice_date.isoformat(),
            "due_date": invoice_data.due_date.isoformat(),
            "currency": invoice_data.currency,
            "tax_rate": invoice_data.tax_rate,
            "line_items_count": len(invoice_data.line_items),
            "trust_level": invoice_data.trust_level,
            "test_id": invoice_data.test_id,
            "pdf_hash": pdf_hash,
            "pdf_path": str(output_path),
            "generated_at": date.today().isoformat(),
        }

        # Save metadata as JSON
        import json

        metadata_path = output_path.with_suffix(".json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return output_path

    def _build_story(self, invoice_data: TestInvoiceData) -> list:
        """Build the PDF story (content elements)."""
        story = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            spaceAfter=30,
            alignment=1,  # Center
        )

        section_style = ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=12,
        )

        normal_style = styles["Normal"]
        normal_style.fontSize = 10

        # Title
        story.append(Paragraph("INVOICE", title_style))
        story.append(Spacer(1, 0.3 * inch))

        # Invoice header table
        header_data = [
            [
                Paragraph(f"<b>Invoice #:</b> {invoice_data.invoice_number}", normal_style),
                Paragraph(f"<b>Date:</b> {invoice_data.invoice_date}", normal_style),
            ],
            [
                Paragraph(f"<b>Due Date:</b> {invoice_data.due_date}", normal_style),
                Paragraph(
                    f"<b>Test ID:</b> {invoice_data.test_id}",
                    normal_style,
                ),
            ],
        ]
        header_table = Table(header_data, colWidths=[3 * inch, 3 * inch])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 0.3 * inch))

        # Vendor and Customer info
        story.append(Paragraph("From:", section_style))
        story.append(Paragraph(invoice_data.vendor_name, normal_style))
        for line in invoice_data.vendor_address.split("\n"):
            story.append(Paragraph(line, normal_style))
        story.append(Paragraph(f"Email: {invoice_data.vendor_email}", normal_style))
        story.append(Paragraph(f"Phone: {invoice_data.vendor_phone}", normal_style))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("To:", section_style))
        story.append(Paragraph(invoice_data.customer_name, normal_style))
        for line in invoice_data.customer_address.split("\n"):
            story.append(Paragraph(line, normal_style))
        story.append(Spacer(1, 0.3 * inch))

        # Line items table
        story.append(Paragraph("Line Items:", section_style))

        table_data = [
            [
                Paragraph("<b>Description</b>", normal_style),
                Paragraph("<b>Qty</b>", normal_style),
                Paragraph("<b>Unit Price</b>", normal_style),
                Paragraph("<b>Total</b>", normal_style),
            ]
        ]

        for item in invoice_data.line_items:
            table_data.append(
                [
                    Paragraph(item.description, normal_style),
                    Paragraph(str(item.quantity), normal_style),
                    Paragraph(f"${item.unit_price:,.2f}", normal_style),
                    Paragraph(f"${item.total:,.2f}", normal_style),
                ]
            )

        # Add subtotal, tax, total
        table_data.append(
            [
                "",
                "",
                Paragraph("<b>Subtotal:</b>", normal_style),
                Paragraph(f"${invoice_data.subtotal:,.2f}", normal_style),
            ]
        )

        if invoice_data.tax_rate > 0:
            table_data.append(
                [
                    "",
                    "",
                    Paragraph(f"<b>Tax ({invoice_data.tax_rate * 100:.1f}%):</b>", normal_style),
                    Paragraph(f"${invoice_data.tax_amount:,.2f}", normal_style),
                ]
            )

        table_data.append(
            [
                "",
                "",
                Paragraph("<b>Total:</b>", normal_style),
                Paragraph(f"<b>${invoice_data.total_amount:,.2f}</b>", normal_style),
            ]
        )

        items_table = Table(table_data, colWidths=[3 * inch, 0.75 * inch, 1.25 * inch, 1.25 * inch])
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (1, 0), (3, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(items_table)
        story.append(Spacer(1, 0.3 * inch))

        # Payment terms and notes
        story.append(Paragraph("Payment Terms:", section_style))
        story.append(
            Paragraph(
                f"Payment is due within 30 days of invoice date ({invoice_data.due_date}).",
                normal_style,
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        if invoice_data.notes:
            story.append(Paragraph("Notes:", section_style))
            story.append(Paragraph(invoice_data.notes, normal_style))
            story.append(Spacer(1, 0.2 * inch))

        # Test metadata (hidden from extraction but useful for verification)
        story.append(Spacer(1, 0.5 * inch))
        story.append(
            Paragraph(
                f"<i>Test Metadata: Trust Level={invoice_data.trust_level} | Test ID={invoice_data.test_id}</i>",
                ParagraphStyle("Meta", parent=normal_style, fontSize=8, textColor=colors.grey),
            )
        )

        return story

    def _generate_file_hash(self, file_path: Path) -> str:
        """Generate SHA-256 hash of the PDF file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def generate_batch(
        self,
        count: int = 5,
        output_dir: Optional[str] = None,
    ) -> list[Path]:
        """
        Generate a batch of test invoices with varying data.

        Args:
            count: Number of invoices to generate.
            output_dir: Output directory.

        Returns:
            List of generated PDF paths.
        """
        output_dir = Path(output_dir) if output_dir else self.output_dir
        generated_files = []

        vendors = [
            ("Acme Corporation", "Professional Services"),
            ("TechSupply Inc.", "Equipment & Supplies"),
            ("Cloud Services LLC", "Cloud Infrastructure"),
            ("Office Depot", "Office Supplies"),
            ("Legal Partners LLP", "Legal Services"),
        ]

        for i in range(count):
            vendor_name, category = vendors[i % len(vendors)]
            amount = 500.00 + (i * 250.00)

            invoice_data = TestInvoiceData(
                vendor_name=vendor_name,
                invoice_number=f"INV-2025-{str(i + 1).zfill(3)}",
                line_items=[
                    InvoiceLineItem(f"{category} - Service {i + 1}", 1, amount),
                ],
                tax_rate=0.08 if i % 2 == 0 else 0.0,
                trust_level=["PROBATION", "STANDARD", "CORE", "STRATEGIC"][i % 4],
                test_id=f"e2e-batch-{i + 1:03d}",
            )

            pdf_path = self.generate(
                invoice_data=invoice_data,
                output_filename=f"test_invoice_{i + 1:03d}.pdf",
            )
            generated_files.append(pdf_path)

        return generated_files


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate test invoice PDFs for E2E testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate single invoice with defaults
  python generate_invoice.py --output test_invoice.pdf

  # Generate invoice with custom vendor and amount
  python generate_invoice.py --vendor "TechCorp" --amount 2500.00 --output tech_invoice.pdf

  # Generate batch of 10 invoices
  python generate_invoice.py --batch 10 --output-dir ./test_invoices

  # Generate with specific invoice number
  python generate_invoice.py --invoice-number "INV-TEST-001" --output custom.pdf
        """,
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="test_invoice.pdf",
        help="Output PDF filename (default: test_invoice.pdf)",
    )

    parser.add_argument(
        "-d",
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: current directory)",
    )

    parser.add_argument(
        "-v",
        "--vendor",
        type=str,
        default="Acme Corporation",
        help="Vendor name (default: Acme Corporation)",
    )

    parser.add_argument(
        "-a",
        "--amount",
        type=float,
        default=1500.00,
        help="Total invoice amount (default: 1500.00)",
    )

    parser.add_argument(
        "-n",
        "--invoice-number",
        type=str,
        default=None,
        help="Invoice number (default: auto-generated)",
    )

    parser.add_argument(
        "-t",
        "--tax-rate",
        type=float,
        default=0.0,
        help="Tax rate as decimal (default: 0.0, e.g., 0.08 for 8%%)",
    )

    parser.add_argument(
        "-b",
        "--batch",
        type=int,
        default=0,
        help="Generate batch of N invoices (default: 0, single invoice)",
    )

    parser.add_argument(
        "--trust-level",
        type=str,
        choices=["PROBATION", "STANDARD", "CORE", "STRATEGIC"],
        default="STANDARD",
        help="Vendor trust level for testing (default: STANDARD)",
    )

    args = parser.parse_args()

    generator = TestInvoiceGenerator(output_dir=args.output_dir)

    if args.batch > 0:
        # Generate batch
        print(f"Generating {args.batch} test invoices...")
        files = generator.generate_batch(count=args.batch, output_dir=args.output_dir)
        print(f"Generated {len(files)} invoices:")
        for f in files:
            print(f"  - {f}")
        return 0
    else:
        # Generate single invoice
        import random

        invoice_data = TestInvoiceData(
            vendor_name=args.vendor,
            invoice_number=args.invoice_number or f"INV-TEST-{random.randint(1000, 9999)}",
            line_items=[
                InvoiceLineItem("Professional Services", 1, args.amount),
            ],
            tax_rate=args.tax_rate,
            trust_level=args.trust_level,
        )

        pdf_path = generator.generate(
            invoice_data=invoice_data,
            output_filename=args.output,
        )

        print(f"Generated test invoice: {pdf_path}")
        print(f"  Vendor: {invoice_data.vendor_name}")
        print(f"  Amount: ${invoice_data.total_amount:,.2f}")
        print(f"  Invoice #: {invoice_data.invoice_number}")
        print(f"  Trust Level: {invoice_data.trust_level}")
        print(f"  PDF Hash: {generator._generate_file_hash(pdf_path)[:16]}...")

        return 0


if __name__ == "__main__":
    sys.exit(main())
