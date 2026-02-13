import { NextRequest, NextResponse } from "next/server"
import { prisma } from "@/lib/prisma"
import { submitApproval } from "@/lib/ai-client"

// POST /api/invoices/[id]/approve - Approve/reject invoice
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const { decision, comments, approverEmail, approverId, threadId } = body

    // Validate decision
    if (!["APPROVED", "REJECTED"].includes(decision)) {
      return NextResponse.json(
        { error: "Invalid decision. Must be APPROVED or REJECTED" },
        { status: 400 }
      )
    }

    // Get invoice
    const invoice = await prisma.invoice.findUnique({
      where: { id },
    })

    if (!invoice) {
      return NextResponse.json(
        { error: "Invoice not found" },
        { status: 404 }
      )
    }

    // Create approval record
    const approval = await prisma.invoiceApproval.create({
      data: {
        invoiceId: id,
        approverId: approverId || "system",
        status: decision,
        comments,
        riskLevel: "MEDIUM",
        decisionAt: new Date(),
      },
    })

    // Update invoice status
    const newStatus = decision === "APPROVED" ? "APPROVED" : "REJECTED"
    await prisma.invoice.update({
      where: { id },
      data: {
        status: newStatus,
        updatedAt: new Date(),
      },
    })

    // Resume AI workflow if threadId provided
    if (threadId) {
      try {
        await submitApproval(
          threadId,
          decision === "APPROVED" ? "approve" : "reject",
          approverEmail,
          approverId,
          comments
        )
      } catch (aiError) {
        console.error("AI approval submission failed:", aiError)
      }
    }

    // Create audit log
    await prisma.auditLog.create({
      data: {
        action: decision === "APPROVED" ? "APPROVE" : "REJECT",
        entityType: "Invoice",
        entityId: id,
        newValue: { decision, comments, approverId },
        performedBy: approverId || "system",
      },
    })

    return NextResponse.json({
      success: true,
      approval,
      invoice: { id, status: newStatus },
    })
  } catch (error) {
    console.error("Error processing approval:", error)
    return NextResponse.json(
      { error: "Failed to process approval" },
      { status: 500 }
    )
  }
}
