"use client";

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";

interface StatusBreakdownProps {
  data: Array<{
    status: string;
    count: number;
  }>;
  title?: string;
  height?: number;
}

const STATUS_COLORS: Record<string, string> = {
  NEW: "#3b82f6",
  EXTRACTED: "#8b5cf6",
  VALIDATED: "#06b6d4",
  APPROVED: "#22c55e",
  REJECTED: "#ef4444",
  PENDING: "#f59e0b",
  PAID: "#10b981",
  FAILED: "#dc2626",
};

const STATUS_LABELS: Record<string, string> = {
  NEW: "New",
  EXTRACTED: "Extracted",
  VALIDATED: "Validated",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  PENDING: "Pending",
  PAID: "Paid",
  FAILED: "Failed",
};

export function StatusBreakdown({
  data,
  title = "Invoice Status",
  height = 300,
}: StatusBreakdownProps) {
  const chartData = data.map((item) => ({
    name: STATUS_LABELS[item.status] || item.status,
    value: item.count,
    color: STATUS_COLORS[item.status] || "#6b7280",
  }));

  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
              }}
              formatter={(value: number) => [
                `${value} (${total > 0 ? ((value / total) * 100).toFixed(1) : 0}%)`,
                "Count",
              ]}
            />
            <Legend
              formatter={(value) => (
                <span className="text-sm">{value}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="mt-4 text-center text-sm text-muted-foreground">
          Total: {total.toLocaleString()} invoices
        </div>
      </CardContent>
    </Card>
  );
}
