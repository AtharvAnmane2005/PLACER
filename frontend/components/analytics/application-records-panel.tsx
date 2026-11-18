"use client";

import { useEffect, useState } from "react";
import { AlertCircle, ChevronLeft, ChevronRight, X } from "lucide-react";

import { ApplicationStatusBadge } from "@/components/shared/application-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTpoApplicationRecords } from "@/hooks/use-analytics";
import { formatCount, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

export interface ApplicationDrilldownFilter {
  status?: string;
  companyId?: string;
  companyName?: string;
  department?: string;
  driveId?: string;
  driveLabel?: string;
  dateFrom?: string;
  dateTo?: string;
}

const STATUS_LABELS: Record<string, string> = {
  applied: "Applied",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
};

function describeFilter(filter: ApplicationDrilldownFilter): string {
  const parts: string[] = [];
  if (filter.status) parts.push(STATUS_LABELS[filter.status] ?? filter.status);
  if (filter.companyName) parts.push(filter.companyName);
  if (filter.department) parts.push(filter.department);
  if (filter.driveLabel) parts.push(filter.driveLabel);
  return parts.length > 0 ? parts.join(" · ") : "All applications";
}

/**
 * Drill-down table behind the TPO dashboard charts.
 *
 * The filter is supplied by whichever chart element was clicked, so the rows
 * here are exactly the applications that produced that number. Only identity
 * and outcome fields are shown; contact details, resumes and answers stay
 * private. The backend enforces drive ownership, so another TPO's applicants
 * can never be reached through a crafted filter.
 */
export function ApplicationRecordsPanel({
  filter,
  onClear,
}: {
  filter: ApplicationDrilldownFilter;
  onClear: () => void;
}) {
  const [page, setPage] = useState(1);
  const filterKey = JSON.stringify(filter);

  useEffect(() => {
    setPage(1);
  }, [filterKey]);

  const { data, isLoading, isError, isFetching } = useTpoApplicationRecords({
    status: filter.status,
    companyId: filter.companyId,
    department: filter.department,
    driveId: filter.driveId,
    dateFrom: filter.dateFrom,
    dateTo: filter.dateTo,
    page,
    limit: PAGE_SIZE,
  });

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const entries = data?.entries ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <CardTitle className="text-base">Application records</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {describeFilter(filter)}
            {data ? ` · ${formatCount(total)} ${total === 1 ? "application" : "applications"}` : ""}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={onClear}>
          <X className="mr-1 h-4 w-4" />
          Clear drill-down
        </Button>
      </CardHeader>
      <CardContent>
        {isError ? (
          <div className="flex items-start gap-3 rounded-md border border-border p-4">
            <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
            <div>
              <p className="text-sm font-medium">Could not load these application records</p>
              <p className="text-xs text-muted-foreground">
                Your charts and drives are unaffected. Clear the drill-down or try again.
              </p>
            </div>
          </div>
        ) : isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : entries.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No applications match this selection.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Student</th>
                    <th className="py-2 pr-4 font-medium">Department</th>
                    <th className="py-2 pr-4 font-medium">Drive</th>
                    <th className="py-2 pr-4 font-medium">Company</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">Applied</th>
                  </tr>
                </thead>
                <tbody className={cn(isFetching && "opacity-60 transition-opacity")}>
                  {entries.map((entry) => (
                    <tr key={entry.application_id} className="border-b border-border/60 last:border-0">
                      <td className="py-2.5 pr-4 font-medium">{entry.student_name}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{entry.department ?? "Not specified"}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{entry.job_title}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{entry.company_name}</td>
                      <td className="py-2.5 pr-4">
                        <ApplicationStatusBadge status={entry.status} />
                      </td>
                      <td className="py-2.5 text-muted-foreground">{formatDate(entry.applied_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>
                Page {page} of {totalPages} · showing {entries.length} of {formatCount(total)}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || isFetching}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page >= totalPages || isFetching}
                  aria-label="Next page"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
