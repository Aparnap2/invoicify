import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@/lib/prisma"
import { processInvoice } from "@/lib/ai-client"

// GET /api/invoices - List invoices
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const status = searchParams.get("status")
    const page = parseInt(searchParams.get("page") || "1")
    const limit = parseInt(searchParams.get("limit") || "10")
    const skip = (page - 1) * limit

    const where = status ? { status: status as any } : {}

    const [invoices, total] = await Promise.all([
      prisma.invoice.findMany({
        where,
        include: {
          lineItems: true,
          approvals: {
            include: {
              approver: {
                select: { id: true, name: true, email: true },
              },
            },
          },
        },
        orderBy: { createdAt: "desc" },
        skip,
        take: limit,
      }),
      prisma.invoice.count({ where }),
    ])

    return NextResponse.json({
      invoices,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    })
  } catch (error) {
    console.error("Error fetching invoices:", error)
    return NextResponse.json(
      { error: "Failed to fetch invoices" },
      { status: 500 }
    )
  }
}

// POST /api/invoices - Create new invoice
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { rawContent, ...invoiceData } = body

    // Process with AI service if raw content provided
    let extractedData = null
    let confidenceScore = null

    if (rawContent) {
      try {
        const aiResult = await processInvoice(rawContent)
        if (aiResult.success && aiResult.result) {
          extractedData = aiResult.result
          confidenceScore = 0.85 // Would come from actual AI response
        }
      } catch (aiError) {
        console.error("AI processing failed:", aiError)
        // Continue without AI processing
      }
    }

    const invoice = await prisma.invoice.create({
      data: {
        ...invoiceData,
        extractedData: extractedData || undefined,
        confidenceScore,
        status: "NEW",
        createdById: "system", // Would come from auth session
      },
      include: {
        lineItems: true,
      },
    })

    // Create audit log
    await prisma.auditLog.create({
      data: {
        action: "CREATE",
        entityType: "Invoice",
        entityId: invoice.id,
        newValue: invoice,
        performedBy: "system",
      },
    })

    return NextResponse.json(invoice, { status: 201 })
  } catch (error) {
    console.error("Error creating invoice:", error)
    return NextResponse.json(
      { error: "Failed to create invoice" },
      { status: 500 }
    )
  }
}
