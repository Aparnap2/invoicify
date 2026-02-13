"use client";

import { useState, useEffect, useCallback } from "react";
import type { Invoice, InvoiceListResponse, InvoiceStats, AuditEvent, AuditTrailResponse } from "~/types/invoice";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8787/api/v1";

interface UseInvoicesOptions {
  page?: number;
  limit?: number;
  status?: string;
  vendor?: string;
  from?: string;
  to?: string;
}

interface UseInvoicesReturn {
  invoices: Invoice[];
  loading: boolean;
  error: string | null;
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
  refetch: () => Promise<void>;
}

export function useInvoices(options: UseInvoicesOptions = {}): UseInvoicesReturn {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    totalPages: 0,
  });

  const fetchInvoices = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (options.page) params.set("page", String(options.page));
    if (options.limit) params.set("limit", String(options.limit));
    if (options.status) params.set("status", options.status);
    if (options.vendor) params.set("vendor", options.vendor);
    if (options.from) params.set("from", options.from);
    if (options.to) params.set("to", options.to);

    try {
      const response = await fetch(`${API_BASE}/invoices?${params.toString()}`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Failed to fetch invoices");

      const data: InvoiceListResponse = await response.json();
      setInvoices(data.data);
      setPagination(data.pagination);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
    return controller;
  }, [options.page, options.limit, options.status, options.vendor, options.from, options.to]);

  useEffect(() => {
    const controller = new AbortController();
    fetchInvoices();
    return () => controller.abort();
  }, [fetchInvoices]);

  return { invoices, loading, error, pagination, refetch: fetchInvoices };
}

export function useInvoice(invoiceId: string | null) {
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInvoice = useCallback(async () => {
    if (!invoiceId) {
      setInvoice(null);
      return;
    }

    setLoading(true);
    setError(null);
    setInvoice(null); // Clear stale data

    try {
      const response = await fetch(`${API_BASE}/invoices/${invoiceId}`);
      if (!response.ok) throw new Error("Failed to fetch invoice");

      const data = await response.json();
      setInvoice(data);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchInvoice();
    return () => controller.abort();
  }, [fetchInvoice]);

  return { invoice, loading, error, refetch: fetchInvoice };
}

export function useInvoiceStats() {
  const [stats, setStats] = useState<InvoiceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/invoices/stats/overview`);
        if (!response.ok) throw new Error("Failed to fetch stats");

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

export function useRiskStats() {
  const [stats, setStats] = useState<RiskStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/risk/stats/overview`);
        if (!response.ok) throw new Error("Failed to fetch risk stats");

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

export function useHighRiskInvoices(threshold: number = 50) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHighRisk = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/risk/list/high-risk?threshold=${threshold}`
        );
        if (!response.ok) throw new Error("Failed to fetch high-risk invoices");

        const data = await response.json();
        setInvoices(data.invoices || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    fetchHighRisk();
  }, [threshold]);

  return { invoices, loading, error };
}

/**
 * Hook to get audit trail for an invoice
 */
export function useAuditTrail(invoiceId: string | null) {
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
        if (!response.ok) throw new Error("Failed to fetch audit trail");

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
