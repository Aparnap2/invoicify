"use client"

import { useState, useEffect } from "react"
import { CheckCircle, XCircle, Clock, AlertTriangle } from "lucide-react"
import { formatCurrency, formatDate, cn } from "@/lib/utils"

interface ApprovalItem {
  id: string
  vendorName: string
  invoiceNumber: string
  totalAmount: number
  currency: string
  dueDate: string
  status: string
  riskLevel: string
  confidenceScore?: number
  createdAt: string
}

const riskColors: Record<string, string> = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedApproval, setSelectedApproval] = useState<ApprovalItem | null>(null)
  const [processing, setProcessing] = useState(false)

  useEffect(() => {
    fetchApprovals()
  }, [])

  async function fetchApprovals() {
    try {
      const response = await fetch("/api/invoices?status=APPROVAL_PENDING")
      if (response.ok) {
        const data = await response.json()
        setApprovals(data.invoices || [])
      }
    } catch (error) {
      console.error("Failed to fetch approvals:", error)
    } finally {
      setLoading(false)
    }
  }

  async function handleDecision(decision: "APPROVED" | "REJECTED", comments?: string) {
    if (!selectedApproval) return

    setProcessing(true)
    try {
      const response = await fetch(`/api/invoices/${selectedApproval.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision,
          comments,
          approverId: "current-user", // Would come from auth
          approverEmail: "user@example.com",
        }),
      })

      if (response.ok) {
        // Remove from list and clear selection
        setApprovals(approvals.filter((a) => a.id !== selectedApproval.id))
        setSelectedApproval(null)
      }
    } catch (error) {
      console.error("Failed to process approval:", error)
    } finally {
      setProcessing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pending Approvals</h1>
        <p className="text-gray-600">
          {approvals.length} invoice{approvals.length !== 1 ? "s" : ""} awaiting your review
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Approval List */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-4 py-3">
            <h2 className="font-semibold text-gray-900">Invoices to Review</h2>
          </div>

          {loading ? (
            <div className="p-8 text-center text-gray-600">Loading...</div>
          ) : approvals.length === 0 ? (
            <div className="p-8 text-center">
              <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
              <h3 className="mt-4 text-lg font-medium text-gray-900">
                All caught up!
              </h3>
              <p className="mt-2 text-gray-600">
                No invoices are currently pending approval.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 max-h-[600px] overflow-y-auto">
              {approvals.map((approval) => (
                <div
                  key={approval.id}
                  className={cn(
                    "cursor-pointer p-4 transition-colors hover:bg-gray-50",
                    selectedApproval?.id === approval.id && "bg-blue-50"
                  )}
                  onClick={() => setSelectedApproval(approval)}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-medium text-gray-900">{approval.vendorName}</p>
                      <p className="text-sm text-gray-600">{approval.invoiceNumber}</p>
                    </div>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        riskColors[approval.riskLevel] || "bg-gray-100 text-gray-800"
                      )}
                    >
                      {approval.riskLevel.toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-lg font-semibold text-gray-900">
                      {formatCurrency(approval.totalAmount, approval.currency)}
                    </span>
                    <span className="text-sm text-gray-600">
                      Due {formatDate(approval.dueDate)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Approval Detail */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-4 py-3">
            <h2 className="font-semibold text-gray-900">Invoice Details</h2>
          </div>

          {selectedApproval ? (
            <div className="p-4 space-y-6">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-100">
                  <AlertTriangle className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="font-semibold text-gray-900">{selectedApproval.vendorName}</p>
                  <p className="text-sm text-gray-600">{selectedApproval.invoiceNumber}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-sm text-gray-600">Amount</p>
                  <p className="text-xl font-bold text-gray-900">
                    {formatCurrency(selectedApproval.totalAmount, selectedApproval.currency)}
                  </p>
                </div>
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-sm text-gray-600">Due Date</p>
                  <p className="text-lg font-semibold text-gray-900">
                    {formatDate(selectedApproval.dueDate)}
                  </p>
                </div>
              </div>

              <div className="rounded-lg bg-gray-50 p-4">
                <p className="text-sm text-gray-600 mb-1">AI Confidence Score</p>
                <div className="flex items-center gap-2">
                  <div className="h-3 flex-1 rounded-full bg-gray-200">
                    <div
                      className={cn(
                        "h-3 rounded-full",
                        (selectedApproval.confidenceScore || 0) >= 0.8
                          ? "bg-green-500"
                          : (selectedApproval.confidenceScore || 0) >= 0.6
                          ? "bg-yellow-500"
                          : "bg-red-500"
                      )}
                      style={{ width: `${(selectedApproval.confidenceScore || 0.8) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-gray-700">
                    {Math.round((selectedApproval.confidenceScore || 0.8) * 100)}%
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Comments (optional)
                </label>
                <textarea
                  className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  rows={3}
                  placeholder="Add any notes about this decision..."
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => handleDecision("REJECTED")}
                  disabled={processing}
                  className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg border border-red-300 bg-white px-4 py-2.5 font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  <XCircle className="h-5 w-5" />
                  Reject
                </button>
                <button
                  onClick={() => handleDecision("APPROVED")}
                  disabled={processing}
                  className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-2.5 font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  <CheckCircle className="h-5 w-5" />
                  Approve
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center p-12 text-center">
              <Clock className="h-12 w-12 text-gray-400" />
              <p className="mt-4 text-gray-600">
                Select an invoice from the list to review
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
