"use client";

import { categoryColor } from "@/lib/chart-theme";
import { cn } from "@/lib/utils";

const STATUS_LABELS: Record<string, string> = {
  applied: "Applied",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
  // Legacy rows are mapped into shortlisted everywhere, including here, so a
  // stale record can never render a "Selected" pill in the current workflow.
  selected: "Shortlisted",
};

/**
 * Application status pill using the one global semantic palette:
 * Applied blue, Shortlisted green, Rejected red.
 *
 * Used by analytics drill-downs and the student application list so a status
 * never changes colour between pages.
 */
export function ApplicationStatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const key = status.toLowerCase();
  const label = STATUS_LABELS[key] ?? status;
  const color = categoryColor(label);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        className
      )}
      style={{ backgroundColor: `${color}1a`, color }}
    >
      {label}
    </span>
  );
}
