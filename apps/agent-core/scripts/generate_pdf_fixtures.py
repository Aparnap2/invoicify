#!/usr/bin/env python3
"""
Generate real PDF invoice fixtures for E2E testing.

Creates professional-looking invoice PDFs with actual text that can be
extracted by Docling + LLM.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib import units
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.colors import HexColor
from io import BytesIO
from pathlib import Path


def create_simple_invoice(output_path: str):
    """
    Create a simple invoice PDF for testing.
    
    Invoice details:
    - Vendor: Acme Supplies Pvt Ltd
    - Invoice #: INV-2024-001
    - Total: $3,540.00
    - Line items: Office Chairs, Desks
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5*units.inch,
        leftMargin=0.5*units.inch,
        topMargin=0.5*units.inch,
        bottomMargin=0.5*units.inch
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Right', alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
    
    elements = []
    
    # Header
    header_data = [
        [Paragraph("<b>ACME SUPPLIES PVT LTD</b>", styles['Normal']), 
         Paragraph("<b>INVOICE</b>", styles['Right'])],
        ["123 Business Park, Mumbai 400001", f"<b>Invoice #:</b> INV-2024-001"],
        ["GST: 27AABCU9603R1ZM", f"<b>Date:</b> January 15, 2024"],
        ["Phone: +91-22-12345678", f"<b>Due Date:</b> February 15, 2024"],
        ["Email: billing@acme.in", ""],
    ]
    
    header_table = Table(header_data, colWidths=[3*units.inch, 3*units.inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Bill To
    elements.append(Paragraph("<b>Bill To:</b>", styles['Normal']))
    elements.append(Paragraph("TechCorp Solutions", styles['Normal']))
    elements.append(Paragraph("456 IT Park, Bangalore 560001", styles['Normal']))
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Line Items Table
    line_items = [
        ["Description", "Qty", "Unit Price", "Total"],
        ["Premium Office Chairs (Ergonomic)", "10", "$150.00", "$1,500.00"],
        ["Executive Desks (Wooden)", "5", "$300.00", "$1,500.00"],
        ["", "", "Subtotal:", "$3,000.00"],
        ["", "", "Tax (18%):", "$540.00"],
        ["", "", "<b>Total:</b>", "<b>$3,540.00</b>"],
    ]
    
    items_table = Table(line_items, colWidths=[3*units.inch, 0.7*units.inch, 1.2*units.inch, 1.2*units.inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (3, 3), (3, 5), 'RIGHT'),
        ('FONTNAME', (3, 5), (3, 5), 'Helvetica-Bold'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Payment Terms
    elements.append(Paragraph("<b>Payment Terms:</b>", styles['Normal']))
    elements.append(Paragraph("Net 30 days. Please make payment via bank transfer.", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    # Bank Details
    elements.append(Paragraph("<b>Bank Details:</b>", styles['Normal']))
    elements.append(Paragraph("HDFC Bank, Account: XXXX-1234, IFSC: HDFC0001234", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    # Footer
    elements.append(Paragraph("<i>Thank you for your business!</i>", styles['Center']))
    
    doc.build(elements)
    print(f"✓ Created: {output_path}")


def create_complex_invoice(output_path: str):
    """
    Create a complex invoice PDF with multiple line items.
    
    Invoice details:
    - Vendor: TechParts India Pvt Ltd
    - Invoice #: PO-98765
    - Total: $12,750.50
    - Line items: 7 items with various products
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5*units.inch,
        leftMargin=0.5*units.inch,
        topMargin=0.5*units.inch,
        bottomMargin=0.5*units.inch
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Right', alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Center', alignment=TA_CENTER))
    
    elements = []
    
    # Header
    header_data = [
        [Paragraph("<b>TECHPARTS INDIA PVT LTD</b>", styles['Normal']), 
         Paragraph("<b>TAX INVOICE</b>", styles['Right'])],
        ["Plot 45, Industrial Area, Phase II", f"<b>Invoice #:</b> PO-98765"],
        ["Pune, Maharashtra 411019", f"<b>PO Number:</b> PUR-2024-042"],
        ["GST: 27AABCT1234P1Z5", f"<b>Date:</b> February 1, 2024"],
        ["Phone: +91-20-98765432", f"<b>Due Date:</b> March 3, 2024"],
        ["Email: accounts@techparts.in", f"<b>Payment Terms:</b> Net 30"],
    ]
    
    header_table = Table(header_data, colWidths=[3.5*units.inch, 2.5*units.inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Ship To
    elements.append(Paragraph("<b>Ship To:</b>", styles['Normal']))
    elements.append(Paragraph("Global Manufacturing Corp", styles['Normal']))
    elements.append(Paragraph("SEZ Unit, Electronic City", styles['Normal']))
    elements.append(Paragraph("Hyderabad, Telangana 500035", styles['Normal']))
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Line Items Table
    line_items = [
        ["Item Code", "Description", "Qty", "Unit Price", "Amount"],
        ["TP-IC-001", "Integrated Circuit LM358 (Dual Op-Amp)", "500", "$2.50", "$1,250.00"],
        ["TP-RS-002", "Resistor Pack 10K Ohm (100 pcs)", "200", "$5.00", "$1,000.00"],
        ["TP-CP-003", "Ceramic Capacitor 100uF (50 pcs)", "300", "$3.50", "$1,050.00"],
        ["TP-LED-004", "LED Display 7-Segment Red", "150", "$8.00", "$1,200.00"],
        ["TP-TR-005", "Transistor BC547 NPN (100 pcs)", "400", "$4.00", "$1,600.00"],
        ["TP-DB-006", "Debug Board with USB Interface", "50", "$25.00", "$1,250.00"],
        ["TP-PS-007", "Power Supply Module 5V/3A", "100", "$15.00", "$1,500.00"],
        ["", "", "", "Subtotal:", "$8,850.00"],
        ["", "", "", "CGST (9%):", "$796.50"],
        ["", "", "", "SGST (9%):", "$796.50"],
        ["", "", "", "IGST (0%):", "$0.00"],
        ["", "", "", "<b>Total:</b>", "<b>$10,443.00</b>"],
    ]
    
    items_table = Table(line_items, colWidths=[1*units.inch, 2.5*units.inch, 0.6*units.inch, 1*units.inch, 1*units.inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 1), (-1, 7), colors.HexColor('#E3F2FD')),
        ('ALIGN', (4, 8), (4, 11), 'RIGHT'),
        ('FONTNAME', (4, 11), (4, 11), 'Helvetica-Bold'),
        ('BACKGROUND', (3, 11), (4, 11), colors.lightgrey),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3*units.inch))
    
    # Notes
    elements.append(Paragraph("<b>Notes:</b>", styles['Normal']))
    elements.append(Paragraph("1. All items are subject to quality inspection before dispatch.", styles['Normal']))
    elements.append(Paragraph("2. Warranty: 12 months from date of purchase.", styles['Normal']))
    elements.append(Paragraph("3. Please quote PO number in all correspondence.", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    # Bank Details
    elements.append(Paragraph("<b>Bank Details for Payment:</b>", styles['Normal']))
    elements.append(Paragraph("State Bank of India, Branch: Pune Industrial Area", styles['Normal']))
    elements.append(Paragraph("Account: 12345678901, IFSC: SBIN0012345", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    # Footer
    elements.append(Paragraph("<i>This is a computer-generated invoice. No signature required.</i>", styles['Normal']))
    
    doc.build(elements)
    print(f"✓ Created: {output_path}")


def create_low_confidence_invoice(output_path: str):
    """
    Create an invoice with intentionally poor formatting 
    (to test low confidence extraction).
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=1*units.inch,
        leftMargin=1*units.inch,
        topMargin=1*units.inch,
        bottomMargin=1*units.inch
    )
    
    styles = getSampleStyleSheet()
    
    elements = []
    
    # Minimal, hard-to-parse content
    elements.append(Paragraph("Invoice", styles['Heading1']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    # Unstructured text
    elements.append(Paragraph("From: Small Vendor, Some Street, City", styles['Normal']))
    elements.append(Paragraph("To: Customer Name", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    elements.append(Paragraph("Items:", styles['Normal']))
    elements.append(Paragraph("- Stuff x 5 @ 100 = 500", styles['Normal']))
    elements.append(Paragraph("- Things x 3 @ 200 = 600", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    elements.append(Paragraph("Total: 1100 (maybe? check math)", styles['Normal']))
    elements.append(Spacer(1, 0.2*units.inch))
    
    elements.append(Paragraph("Date: sometime in Jan 2024", styles['Normal']))
    elements.append(Paragraph("Pay pls", styles['Normal']))
    
    doc.build(elements)
    print(f"✓ Created: {output_path}")


if __name__ == "__main__":
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "invoices"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating PDF invoice fixtures for E2E testing...\n")
    
    # Create test invoices
    create_simple_invoice(str(fixtures_dir / "simple_invoice.pdf"))
    create_complex_invoice(str(fixtures_dir / "complex_invoice.pdf"))
    create_low_confidence_invoice(str(fixtures_dir / "low_confidence_invoice.pdf"))
    
    print(f"\n✓ All fixtures created in: {fixtures_dir}")
    print("\nFixture details:")
    print("  - simple_invoice.pdf: Acme Supplies, $3,540.00, 2 line items")
    print("  - complex_invoice.pdf: TechParts India, $10,443.00, 7 line items")
    print("  - low_confidence_invoice.pdf: Poorly formatted, for testing")
