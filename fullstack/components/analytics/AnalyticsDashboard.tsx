"use client";

import { useMemo } from "react";
import {
  FileText,
  DollarSign,
  AlertTriangle,
  TrendingUp,
  Clock,
  CheckCircle,
} from "lucide-react";
import { KpiCard, formatCurrency, formatCompact } from "./KpiCard";
import { InvoiceChart } from "./InvoiceChart";
import { StatusBreakdown } from "./StatusBreakdown";
import { RiskOverview, RiskBadge } from "./RiskOverview";
import { RecentActivity } from "./RecentActivity";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import type { InvoiceStats, RiskStats, Invoice } from "~/types/invoice";

interface AnalyticsDashboardProps {
  invoiceStats: InvoiceStats | null;
  riskStats: RiskStats | null;
  recentInvoices: Invoice[];
  loading?: boolean;
}

export function AnalyticsDashboard({
  invoiceStats,
  riskStats,
  recentInvoices,
  loading = false,
}: AnalyticsDashboardProps) {
  // Calculate KPIs from stats
  const kpis = useMemo(() => {
    if (!invoiceStats) return null;

    const totalAmount = invoiceStats.totals?.total || 0;
    const avgAmount = invoiceStats.totals?.avg || 0;
    const todayCount = invoiceStats.recentActivity?.today || 0;
    const weekCount = invoiceStats.recentActivity?.week || 0;
    const criticalCount = riskStats?.criticalCount || 0;

    // Calculate week change
    const weekChange = weekCount > 0 ? ((todayCount * 7) / weekCount - 1) * 100 : 0;

    return {
      totalAmount,
      avgAmount,
      todayCount,
      weekCount,
      weekChange,
      criticalCount,
    };
  }, [invoiceStats, riskStats]);

  // Status breakdown data
  const statusData = useMemo(() => {
    if (!invoiceStats?.byStatus) return [];
    return invoiceStats.byStatus.map((s) => ({
      status: s.status,
      count: s.count,
    }));
  }, [invoiceStats]);

  // Risk distribution data
  const riskData = useMemo(() => {
    if (!riskStats?.byRiskLevel) return [];
    return riskStats.byRiskLevel.map((r) => ({
      level: r.level,
      count: r.count,
      totalAmount: r.totalAmount,
    }));
  }, [riskStats]);

  // Generate chart data from recent invoices
  const chartData = useMemo(() => {
    const last14Days = Array.from({ length: 14 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - (13 - i));
      return d.toISOString().split("T")[0];
    });

    return last14Days.map((day) => {
      const dayInvoices = recentInvoices.filter((inv) =>
        inv.createdAt.startsWith(day)
      );
      return {
        date: day,
        count: dayInvoices.length,
        amount: dayInvoices.reduce((sum, inv) => sum + inv.totalAmount, 0),
      };
    });
  }, [recentInvoices]);

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardHeader className="pb-2">
              <div className="h-4 bg-muted rounded w-20" />
            </CardHeader>
            <CardContent>
              <div className="h-8 bg-muted rounded w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Total Processed"
          value={kpis?.todayCount || 0}
          change={kpis?.weekChange}
          changeLabel="vs last week"
          trend={kpis && kpis.weekChange > 0 ? "up" : "down"}
          icon={<FileText className="h-5 w-5" />}
        />
        <KpiCard
          title="Total Amount"
          value={formatCompact(kpis?.totalAmount || 0)}
          change={5.2}
          changeLabel="vs last month"
          trend="up"
          icon={<DollarSign className="h-5 w-5" />}
        />
        <KpiCard
          title="Avg. Invoice"
          value={formatCurrency(kpis?.avgAmount || 0)}
          icon={<TrendingUp className="h-5 w-5" />}
        />
        <KpiCard
          title="Critical Risk"
          value={kpis?.criticalCount || 0}
          icon={<AlertTriangle className="h-5 w-5" />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid gap-4 lg:grid-cols-2">
        <InvoiceChart data={chartData} title="Invoice Trends (14 Days)" />
        <StatusBreakdown data={statusData} />
      </div>

      {/* Risk and Activity Row */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RiskOverview data={riskData} />
        </div>
        <RecentActivity
          activities={recentInvoices.slice(0, 5).map((inv) => ({
            id: inv.id,
            action: "CREATE",
            entityType: "invoice",
            entityId: inv.id,
            performedBy: "system",
            performedAt: inv.createdAt,
          }))}
          title="Recent Invoices"
        />
      </div>

      {/* High Risk Alerts */}
      {riskStats?.criticalCount && riskStats.criticalCount > 0 && (
        <Card className="border-red-200 bg-red-50">
          <CardHeader>
            <CardTitle className="text-red-800 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              High Risk Alerts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-red-700">
              {riskStats.criticalCount} invoices require immediate attention due to
              critical risk indicators.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
