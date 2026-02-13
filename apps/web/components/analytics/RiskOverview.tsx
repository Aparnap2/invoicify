"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";

interface RiskOverviewProps {
  data: Array<{
    level: string;
    count: number;
    totalAmount?: number;
  }>;
  title?: string;
  height?: number;
}

const RISK_COLORS: Record<string, string> = {
  LOW: "#22c55e",
  MEDIUM: "#f59e0b",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

export function RiskOverview({
  data,
  title = "Risk Distribution",
  height = 250,
}: RiskOverviewProps) {
  const chartData = data.map((item) => ({
    name: item.level,
    count: item.count,
    amount: item.totalAmount || 0,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => value.toLocaleString()}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
              }}
              formatter={(value: number, name: string) => [
                name === "amount" ? `$${value.toLocaleString()}` : value,
                name === "count" ? "Count" : "Total Amount",
              ]}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={RISK_COLORS[entry.name] || "#6b7280"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

/**
 * Risk level badge component
 */
interface RiskBadgeProps {
  level: string;
  score?: number;
  showScore?: boolean;
  className?: string;
}

export function RiskBadge({
  level,
  score,
  showScore = false,
  className,
}: RiskBadgeProps) {
  const colors: Record<string, string> = {
    LOW: "bg-green-100 text-green-800",
    MEDIUM: "bg-yellow-100 text-yellow-800",
    HIGH: "bg-orange-100 text-orange-800",
    CRITICAL: "bg-red-100 text-red-800",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        colors[level] || "bg-gray-100 text-gray-800",
        className
      )}
    >
      {level}
      {showScore && score !== undefined && (
        <span className="ml-1 opacity-75">({score})</span>
      )}
    </span>
  );
}
