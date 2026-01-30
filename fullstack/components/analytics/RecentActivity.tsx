"use client";

import {
  FileText,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Upload,
  Download,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { cn } from "~/lib/utils";

interface ActivityItem {
  id: string;
  action: string;
  entityType: string;
  entityId: string;
  performedBy?: string;
  performedAt: string;
  changes?: string;
}

interface RecentActivityProps {
  activities: ActivityItem[];
  title?: string;
  maxItems?: number;
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  CREATE: <FileText className="h-4 w-4 text-blue-500" />,
  UPDATE: <FileText className="h-4 w-4 text-blue-500" />,
  DELETE: <XCircle className="h-4 w-4 text-red-500" />,
  STATUS_CHANGE: <Clock className="h-4 w-4 text-yellow-500" />,
  APPROVE: <CheckCircle className="h-4 w-4 text-green-500" />,
  REJECT: <XCircle className="h-4 w-4 text-red-500" />,
  EXTRACT: <FileText className="h-4 w-4 text-purple-500" />,
  FILE_UPLOAD: <Upload className="h-4 w-4 text-blue-500" />,
  FILE_DELETE: <XCircle className="h-4 w-4 text-red-500" />,
  QUICKBOOKS_SYNC: <Download className="h-4 w-4 text-green-500" />,
  RISK_ANALYSIS: <AlertTriangle className="h-4 w-4 text-orange-500" />,
};

const ACTION_LABELS: Record<string, string> = {
  CREATE: "Created",
  UPDATE: "Updated",
  DELETE: "Deleted",
  STATUS_CHANGE: "Status changed",
  APPROVE: "Approved",
  REJECT: "Rejected",
  EXTRACT: "Extracted data",
  FILE_UPLOAD: "Uploaded file",
  FILE_DELETE: "Deleted file",
  QUICKBOOKS_SYNC: "Synced to QuickBooks",
  RISK_ANALYSIS: "Analyzed risk",
};

export function RecentActivity({
  activities,
  title = "Recent Activity",
  maxItems = 10,
}: RecentActivityProps) {
  const sortedActivities = [...activities]
    .sort(
      (a, b) =>
        new Date(b.performedAt).getTime() - new Date(a.performedAt).getTime()
    )
    .slice(0, maxItems);

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return "Unknown time";
    }
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {sortedActivities.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No recent activity
            </p>
          ) : (
            sortedActivities.map((activity) => (
              <div
                key={activity.id}
                className="flex items-start gap-3 text-sm"
              >
                <div className="mt-0.5">
                  {ACTION_ICONS[activity.action] || (
                    <FileText className="h-4 w-4 text-gray-500" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium truncate">
                      {ACTION_LABELS[activity.action] || activity.action}
                    </p>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatTime(activity.performedAt)}
                    </span>
                  </div>
                  <p className="text-muted-foreground truncate">
                    {activity.entityType === "invoice"
                      ? `Invoice #${activity.entityId.slice(0, 8)}`
                      : activity.entityId}
                    {activity.performedBy && ` by ${activity.performedBy}`}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
