import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { useState, useEffect } from "react";
import { format } from "date-fns";
import "./index.css";
import { Dashboard } from "./Dashboard";

// Types
import type { Invoice, InvoiceListResponse, AuditEvent, AuditTrailResponse } from "../types/invoice";

const API_BASE = (import.meta.env.VITE_API_URL as string) || "http://localhost:8787/api/v1";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

// ============ API Hooks ============

function useInvoices(options: { page?: number; limit?: number; status?: string } = {}) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });

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
        if (!response.ok) throw new Error("Failed to fetch invoices");
        const data: InvoiceListResponse = await response.json();
        setInvoices(data.data);
        setPagination(data.pagination);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchInvoices();
  }, [options.page, options.limit, options.status]);

  return { invoices, loading, error, pagination };
}

function useHitlInvoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchInvoices = async () => {
      try {
        const response = await fetch(`${API_BASE}/invoices?status=APPROVAL_PENDING`);
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
  }, []);

  return { invoices, loading, error };
}

function useAuditTrail(invoiceId: string | null) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!invoiceId) {
      setEvents([]);
      return;
    }
    const fetchAudit = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE}/risk/${invoiceId}/audit`);
        if (!response.ok) throw new Error("Failed");
        const data: AuditTrailResponse = await response.json();
        setEvents(data.events || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchAudit();
  }, [invoiceId]);

  return { events, loading, error };
}

// ============ Components ============

function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[200px]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      Error: {message}
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
      {level}
    </span>
  );
}

function NavBar() {
  const location = useLocation();
  const navItems = [
    { path: "/", label: "Dashboard", icon: "📊" },
    { path: "/invoices", label: "Invoices", icon: "📄" },
    { path: "/hitl", label: "HITL Review", icon: "⚠️" },
    { path: "/audit", label: "Audit Trail", icon: "📋" },
  ];

  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Invoicify AI</h1>
        <div className="flex gap-4">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                location.pathname === item.path
                  ? "bg-blue-100 text-blue-700"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              <span className="mr-2">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}

function InvoicesPage() {
  const { invoices, loading, error } = useInvoices({ page: 1, limit: 20 });

  if (loading) return <Loading />;
  if (error) return <ErrorMessage message={error} />;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h2 className="text-2xl font-bold mb-6">Invoices</h2>
      <div className="bg-white rounded-lg shadow overflow-hidden">
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
            {invoices.map((invoice) => (
              <tr key={invoice.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {invoice.invoiceNumber}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{invoice.vendorName}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
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
    </div>
  );
}

function HitlReviewPage() {
  const { invoices, loading, error } = useHitlInvoices();
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [approving, setApproving] = useState(false);

  const handleApprove = async (invoiceId: string, decision: "approved" | "rejected") => {
    setApproving(true);
    try {
      const response = await fetch(`${API_BASE}/invoices/${invoiceId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comments: "Approved via HITL" }),
      });
      if (!response.ok) throw new Error("Failed");
      setSelectedInvoice(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setApproving(false);
    }
  };

  if (loading) return <Loading />;
  if (error) return <ErrorMessage message={error} />;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h2 className="text-2xl font-bold mb-6">⚠️ Human-in-the-Loop Review</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium mb-4">Pending Approval ({invoices.length})</h3>
          <div className="space-y-3">
            {invoices.map((invoice) => (
              <div
                key={invoice.id}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  selectedInvoice?.id === invoice.id
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
                onClick={() => setSelectedInvoice(invoice)}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-medium">{invoice.invoiceNumber}</p>
                    <p className="text-sm text-gray-500">{invoice.vendorName}</p>
                  </div>
                  <span className="text-lg font-semibold">${invoice.totalAmount.toLocaleString()}</span>
                </div>
                <RiskBadge level={invoice.riskLevel} />
              </div>
            ))}
            {invoices.length === 0 && (
              <p className="text-gray-500 text-center py-8">No invoices pending approval</p>
            )}
          </div>
        </div>
        <div>
          {selectedInvoice ? (
            <div className="bg-white rounded-lg border border-gray-200 p-6 sticky top-6">
              <h3 className="text-lg font-bold mb-4">{selectedInvoice.invoiceNumber}</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-500">Vendor</p>
                  <p className="font-medium">{selectedInvoice.vendorName}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Amount</p>
                  <p className="font-medium text-lg">${selectedInvoice.totalAmount.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Due Date</p>
                  <p className="font-medium">
                    {selectedInvoice.dueDate ? format(new Date(selectedInvoice.dueDate), "MMM d, yyyy") : "-"}
                  </p>
                </div>
                <div className="pt-4 flex gap-3">
                  <button
                    onClick={() => handleApprove(selectedInvoice.id, "approved")}
                    disabled={approving}
                    className="flex-1 bg-green-600 text-white py-2 px-4 rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {approving ? "..." : "Approve"}
                  </button>
                  <button
                    onClick={() => handleApprove(selectedInvoice.id, "rejected")}
                    disabled={approving}
                    className="flex-1 bg-red-600 text-white py-2 px-4 rounded-lg hover:bg-red-700 disabled:opacity-50"
                  >
                    {approving ? "..." : "Reject"}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg border border-gray-200 p-6 text-center text-gray-500">
              Select an invoice to review
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AuditTimelinePage() {
  const [invoiceId, setInvoiceId] = useState("");
  const [searchId, setSearchId] = useState("");
  const { events, loading, error } = useAuditTrail(searchId || null);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h2 className="text-2xl font-bold mb-6">📋 Audit Trail</h2>
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">Invoice ID</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={invoiceId}
            onChange={(e) => setInvoiceId(e.target.value)}
            placeholder="Enter invoice ID..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            onClick={() => setSearchId(invoiceId)}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Search
          </button>
        </div>
      </div>
      {loading && <Loading />}
      {error && <ErrorMessage message={error} />}
      {events.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="font-medium mb-4">Audit Events for {searchId}</h3>
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200"></div>
            <div className="space-y-6">
              {events.map((event, index) => (
                <div key={index} className="relative pl-10">
                  <div className="absolute left-2 w-4 h-4 bg-blue-500 rounded-full border-2 border-white"></div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <span className="font-medium">{event.action}</span>
                      <span className="text-sm text-gray-500">
                        {format(new Date(event.performedAt), "MMM d, yyyy HH:mm")}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600">
                      By: <span className="font-medium">{event.performedBy}</span>
                    </p>
                    {event.details && Object.keys(event.details).length > 0 && (
                      <pre className="mt-2 text-xs bg-gray-100 p-2 rounded overflow-x-auto">
                        {JSON.stringify(event.details, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============ Main App ============

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50">
          <NavBar />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/invoices" element={<InvoicesPage />} />
            <Route path="/hitl" element={<HitlReviewPage />} />
            <Route path="/audit" element={<AuditTimelinePage />} />
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
