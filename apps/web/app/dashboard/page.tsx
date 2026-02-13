"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { FileText, Upload, CheckSquare, TrendingUp, Clock } from "lucide-react"
import { formatCurrency, formatDate, cn } from "@/lib/utils"

interface Invoice {
  id: string
  vendorName: string
  invoiceNumber: string
  totalAmount: number
  currency: string
  status: string
  dueDate: string
  createdAt: string
}

const statusColors: Record<string, string> = {
  NEW: "bg-gray-100 text-gray-800",
  EXTRACTING: "bg-yellow-100 text-yellow-800",
  EXTRACTED: "bg-blue-100 text-blue-800",
  VALIDATING: "bg-purple-100 text-purple-800",
  MATCHED: "bg-green-100 text-green-800",
  EXCEPTION: "bg-red-100 text-red-800",
  APPROVAL_PENDING: "bg-orange-100 text-orange-800",
  APPROVED: "bg-emerald-100 text-emerald-800",
  REJECTED: "bg-red-100 text-red-800",
  POSTED: "bg-teal-100 text-teal-800",
  ARCHIVED: "bg-slate-100 text-slate-800",
}

export default function DashboardPage() {
  const [stats, setStats] = useState({
    totalInvoices: 0,
    pendingApproval: 0,
    processedThisMonth: 0,
    totalValue: 0,
  })
  const [recentInvoices, setRecentInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch dashboard data
    async function fetchData() {
      try {
        const [invoicesRes, statsRes] = await Promise.all([
          fetch("/api/invoices?limit=5"),
          fetch("/api/invoices/stats"),
        ])

        let total = 0
        let pendingCount = 0

        if (invoicesRes.ok) {
          const data = await invoicesRes.json()
          setRecentInvoices(data.invoices || [])
          total = data.pagination?.total || 0
          pendingCount = data.invoices?.filter((i: Invoice) => i.status === "APPROVAL_PENDING").length || 0
        }

        // Stats would come from a separate endpoint
        setStats({
          totalInvoices: total,
          pendingApproval: pendingCount,
          processedThisMonth: 0,
          totalValue: 0,
        })
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600">Overview of your invoice processing</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Invoices"
          value={stats.totalInvoices}
          icon={FileText}
          color="blue"
        />
        <StatCard
          title="Pending Approval"
          value={stats.pendingApproval}
          icon={Clock}
          color="orange"
        />
        <StatCard
          title="Processed This Month"
          value={stats.processedThisMonth}
          icon={TrendingUp}
          color="green"
        />
        <StatCard
          title="Total Value"
          value={formatCurrency(stats.totalValue)}
          icon={CheckSquare}
          color="purple"
        />
      </div>

      {/* Quick Actions */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Link
          href="/dashboard/upload"
          className="flex items-center gap-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-100">
            <Upload className="h-6 w-6 text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Upload Invoice</h3>
            <p className="text-sm text-gray-600">Process a new invoice with AI</p>
          </div>
        </Link>

        <Link
          href="/dashboard/approvals"
          className="flex items-center gap-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-orange-100">
            <CheckSquare className="h-6 w-6 text-orange-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Pending Approvals</h3>
            <p className="text-sm text-gray-600">
              {stats.pendingApproval} invoices awaiting review
            </p>
          </div>
        </Link>
      </div>

      {/* Recent Invoices */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="font-semibold text-gray-900">Recent Invoices</h2>
          <Link
            href="/dashboard/invoices"
            className="text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            View all
          </Link>
        </div>

        {loading ? (
          <div className="p-6 text-center text-gray-600">Loading...</div>
        ) : recentInvoices.length === 0 ? (
          <div className="p-6 text-center text-gray-600">
            No invoices yet.{" "}
            <Link href="/dashboard/upload" className="text-blue-600 hover:text-blue-700">
              Upload your first invoice
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {recentInvoices.map((invoice) => (
              <div
                key={invoice.id}
                className="flex items-center justify-between px-6 py-4 hover:bg-gray-50"
              >
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                    <FileText className="h-5 w-5 text-gray-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{invoice.vendorName}</p>
                    <p className="text-sm text-gray-600">{invoice.invoiceNumber}</p>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", statusColors[invoice.status] || "bg-gray-100 text-gray-800")}>
                    {invoice.status.replace("_", " ")}
                  </span>
                  <p className="font-medium text-gray-900">
                    {formatCurrency(invoice.totalAmount, invoice.currency)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  color: "blue" | "orange" | "green" | "purple"
}) {
  const colorClasses = {
    blue: "bg-blue-100 text-blue-600",
    orange: "bg-orange-100 text-orange-600",
    green: "bg-green-100 text-green-600",
    purple: "bg-purple-100 text-purple-600",
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={cn("flex h-12 w-12 items-center justify-center rounded-lg", colorClasses[color])}>
          <Icon className="h-6 w-6" />
        </div>
        <div>
          <p className="text-sm text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900">
            {typeof value === "number" ? value.toLocaleString() : value}
          </p>
        </div>
      </div>
    </div>
  )
}
