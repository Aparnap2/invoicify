"use client";

import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { cn } from "~/lib/utils";

interface KpiCardProps {
  title: string;
  value: number | string;
  change?: number;
  changeLabel?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  className?: string;
  formatter?: (value: number | string) => string;
}

export function KpiCard({
  title,
  value,
  change,
  changeLabel,
  trend,
  icon,
  className,
  formatter = defaultFormatter,
}: KpiCardProps) {
  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : Minus;
  const trendColor = trend === "up"
    ? "text-green-600"
    : trend === "down"
    ? "text-red-600"
    : "text-gray-500";

  return (
    <div className={cn("rounded-lg border bg-card p-6 shadow-sm", className)}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </div>
      <div className="mt-2">
        <p className="text-3xl font-bold">{formatter(value)}</p>
        {change !== undefined && (
          <div className="mt-1 flex items-center gap-1">
            <TrendIcon className={cn("h-4 w-4", trendColor)} />
            <span className={cn("text-sm font-medium", trendColor)}>
              {change > 0 ? "+" : ""}
              {change.toFixed(1)}%
            </span>
            {changeLabel && (
              <span className="text-sm text-muted-foreground">{changeLabel}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function defaultFormatter(value: number | string): string {
  if (typeof value === "number") {
    return value.toLocaleString();
  }
  return value;
}

/**
 * Format currency value
 */
export function formatCurrency(value: number, currency: string = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format percentage
 */
export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Format large numbers
 */
export function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}
