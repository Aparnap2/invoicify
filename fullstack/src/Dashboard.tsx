import { useState, useEffect } from "react";
import { format } from "date-fns";
import type { Invoice, InvoiceListResponse, InvoiceStats, RiskStats } from "../types/invoice";

const API_BASE = (import.meta.env.VITE_API_URL as string) || "http://localhost:8787/api/v1";

// ============ Local Hooks ============

function useInvoices(options: { page?: number; limit?: number; status?: string } = {}) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchInvoices = async () => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (options.page) params.set("page", String(options.page));
      if (options.limit) params.set("limit", String(options.limit));
      if (options.status) params.set("status", options.status);

      try {
        const response = await fetch(`${API_BASE}/invoices?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to fetch");
        const data: InvoiceListResponse = await response.json();
        setInvoices(data.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchInvoices();
  }, [options.page, options.limit, options.status]);

  return { invoices, loading, error };
}

function useInvoiceStats() {
  const [stats, setStats] = useState<InvoiceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/invoices/stats/overview`);
        if (!response.ok) throw new Error("Failed");
        const data = await response.json();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  return { stats, loading, error };
}

function useRiskStats() {
  const [stats, setStats] = useState<RiskStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/risk/stats/overview`);
        if (!response.ok) throw new Error("Failed");
        const data = await response.json();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  return { stats, loading, error };
}

// ============ Components ============

function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[200px]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );
}

function KpiCard({ title, value, icon, trend }: { title: string; value: string | number; icon?: string; trend?: "up" | "down" }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
        </div>
        {icon && <span className="text-2xl">{icon}</span>}
      </div>
      {trend && (
        <div className={`mt-2 text-sm ${trend === "up" ? "text-green-600" : "text-red-600"}`}>
          {trend === "up" ? "↑" : "↓"} vs last month
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    APPROVED: "bg-green-100 text-green-800",
    REJECTED: "bg-red-100 text-red-800",
    APPROVAL_PENDING: "bg-yellow-100 text-yellow-800",
    PAID: "bg-blue-100 text-blue-800",
    NEW: "bg-gray-100 text-gray-800",
  };
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${colors[status] || "bg-gray-100 text-gray-800"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function RiskBadge({ level }: { level?: string }) {
  if (!level) return null;
  const colors: Record<string, string> = {
    CRITICAL: "bg-red-100 text-red-800",
    HIGH: "bg-orange-100 text-orange-800",
    MEDIUM: "bg-yellow-100 text-yellow-800",
    LOW: "bg-green-100 text-green-800",
  };
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${colors[level] || "bg-gray-100 text-gray-800"}`}>
      {level} RISK
    </span>
  );
}

export function Dashboard() {
  const { stats: invoiceStats, loading: invoiceLoading } = useInvoiceStats();
  const { stats: riskStats, loading: riskLoading } = useRiskStats();
  const { invoices: recentInvoices, loading: invoicesLoading } = useInvoices({ limit: 5 });
  const { invoices: pendingInvoices } = useInvoices({ status: "APPROVAL_PENDING" });

  if (invoiceLoading || riskLoading || invoicesLoading) {
    return <Loading />;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h1 className="text-3xl font-bold mb-8">Invoicify AI Dashboard</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <KpiCard
          title="Total Invoices"
          value={invoiceStats?.totals?.total || 0}
          icon="📄"
        />
        <KpiCard
          title="Pending Review"
          value={pendingInvoices.length}
          icon="⚠️"
        />
        <KpiCard
          title="Avg Amount"
          value={`$${(invoiceStats?.totals?.avg || 0).toLocaleString()}`}
          icon="💰"
        />
        <KpiCard
          title="Critical Risk"
          value={riskStats?.criticalCount || 0}
          icon="🚨"
        />
      </div>

      {/* Risk Overview */}
      {riskStats && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-lg font-bold mb-4">Risk Overview</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {riskStats.byRiskLevel?.map((r: any) => (
              <div key={r.level} className="text-center p-4 bg-gray-50 rounded">
                <RiskBadge level={r.level} />
                <p className="text-2xl font-bold mt-2">{r.count}</p>
                <p className="text-sm text-gray-500">${(r.totalAmount || 0).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Invoices */}
      <div className="bg-white rounded-lg shadow overflow-hidden mb-8">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-bold">Recent Invoices</h2>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Invoice</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Vendor</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Amount</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {recentInvoices.map((invoice) => (
              <tr key={invoice.id}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{invoice.invoiceNumber}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{invoice.vendorName}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  ${invoice.totalAmount.toLocaleString()}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <StatusBadge status={invoice.status} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <RiskBadge level={invoice.riskLevel} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {invoice.invoiceDate ? format(new Date(invoice.invoiceDate), "MMM d, yyyy") : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Status Breakdown */}
      {invoiceStats?.byStatus && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-bold mb-4">Status Breakdown</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {invoiceStats.byStatus.map((s: any) => (
              <div key={s.status} className="text-center p-4 bg-gray-50 rounded">
                <StatusBadge status={s.status} />
                <p className="text-2xl font-bold mt-2">{s.count}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
