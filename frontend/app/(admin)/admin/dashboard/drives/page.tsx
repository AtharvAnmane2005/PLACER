"use client";

import {
  AlertCircle,
  Briefcase,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApplicationStatusBadge } from "@/components/shared/application-status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { useAdminApplicationFilters, useAdminApplications } from "@/hooks/use-analytics";
import { useUpdateApplicationStatusForDrive } from "@/hooks/use-tpo-drives";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AdminAssessmentCompletionFilter } from "@/types/analytics";
import type { ManagedApplicationStatus } from "@/types/drive";

const PAGE_SIZE = 20;
const STATUS_OPTIONS: ManagedApplicationStatus[] = ["applied", "shortlisted", "rejected"];

const ASSESSMENT_FILTERS: { value: AdminAssessmentCompletionFilter; label: string }[] = [
  { value: "all", label: "All assessments" },
  { value: "completed", label: "Completed (passed/failed)" },
  { value: "pending", label: "Pending / expired" },
  { value: "not_required", label: "No assessment required" },
];

function statusLabel(status: ManagedApplicationStatus): string {
  switch (status) {
    case "shortlisted":
      return "Shortlisted";
    case "rejected":
      return "Rejected";
    default:
      return "Applied";
  }
}

function assessmentLabel(status: string): string {
  switch (status) {
    case "passed":
      return "Passed";
    case "failed":
      return "Failed";
    case "expired":
      return "Expired";
    case "pending":
      return "Pending";
    default:
      return "Not required";
  }
}

/**
 * Admin application management across every placement drive.
 *
 * Summary cards are computed by the backend before the status filter, so all
 * four stay meaningful while a status is selected. Status changes go through
 * the audited PATCH endpoint; `selected` is never offered because it is a
 * legacy, read-only outcome (read-time mapped to shortlisted).
 */
export default function AdminApplicationsPage() {
  const [companyId, setCompanyId] = useState("all");
  const [driveId, setDriveId] = useState("all");
  const [department, setDepartment] = useState("all");
  const [status, setStatus] = useState<"all" | ManagedApplicationStatus>("all");
  const [assessmentCompletion, setAssessmentCompletion] =
    useState<AdminAssessmentCompletionFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const filters = useAdminApplicationFilters();
  const { data, isLoading, isError, isFetching, refetch } = useAdminApplications({
    company_id: companyId === "all" ? undefined : companyId,
    drive_id: driveId === "all" ? undefined : driveId,
    department: department === "all" ? undefined : department,
    status: status === "all" ? undefined : status,
    assessment_completion: assessmentCompletion,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page,
    limit: PAGE_SIZE,
  });

  const updateStatus = useUpdateApplicationStatusForDrive();
  const { toast } = useToast();

  // Reset to the first page whenever a filter changes.
  const filterKey = `${companyId}|${driveId}|${department}|${status}|${assessmentCompletion}|${dateFrom}|${dateTo}`;
  useEffect(() => {
    setPage(1);
  }, [filterKey]);

  // A drive filter that belongs to another company would be impossible to
  // satisfy; narrow the drive options to the selected company.
  const driveOptions = useMemo(() => {
    const drives = filters.data?.drives ?? [];
    if (companyId === "all") return drives;
    return drives.filter((drive) => {
      const company = filters.data?.companies.find((c) => c.id === companyId);
      return company ? drive.company_name === company.name : true;
    });
  }, [filters.data, companyId]);

  const summary = data?.summary;
  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasActiveFilters =
    companyId !== "all" ||
    driveId !== "all" ||
    department !== "all" ||
    status !== "all" ||
    assessmentCompletion !== "all" ||
    Boolean(dateFrom) ||
    Boolean(dateTo);

  const clearFilters = () => {
    setCompanyId("all");
    setDriveId("all");
    setDepartment("all");
    setStatus("all");
    setAssessmentCompletion("all");
    setDateFrom("");
    setDateTo("");
  };

  const handleStatusChange = async (
    row: { application_id: string; drive_id: string; student_name: string },
    next: ManagedApplicationStatus
  ) => {
    try {
      await updateStatus.mutateAsync({
        driveId: row.drive_id,
        applicationId: row.application_id,
        status: next,
      });
      toast({
        title: "Status updated",
        description: `${row.student_name} is now ${statusLabel(next).toLowerCase()}.`,
      });
    } catch (err: any) {
      toast({
        title: "Could not update status",
        description: err?.response?.data?.detail ?? err?.message ?? "Please try again.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Applications</h1>
        <p className="text-sm text-muted-foreground">
          Review applications across every placement drive and manage their status.
        </p>
      </div>

      <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3 text-sm">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-muted-foreground">
          Status changes are recorded in the audit log with the previous and new status. Students
          cannot change their own application status.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total applications" value={summary?.total ?? 0} icon={ClipboardList} />
        <StatCard label="Applied / Under review" value={summary?.applied ?? 0} icon={Clock} />
        <StatCard label="Shortlisted" value={summary?.shortlisted ?? 0} icon={CheckCircle2} />
        <StatCard label="Rejected" value={summary?.rejected ?? 0} icon={XCircle} />
      </div>

      <Card>
        <CardHeader className="space-y-0">
          <CardTitle className="text-base">Filters</CardTitle>
          <CardDescription>
            Summary cards reflect every filter except status, so all four stay visible.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="filter-company">Company</Label>
              <Select
                value={companyId}
                onValueChange={(value) => {
                  setCompanyId(value);
                  setDriveId("all");
                }}
              >
                <SelectTrigger id="filter-company">
                  <SelectValue placeholder="All companies" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All companies</SelectItem>
                  {(filters.data?.companies ?? []).map((company) => (
                    <SelectItem key={company.id} value={company.id}>
                      {company.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-drive">Drive</Label>
              <Select value={driveId} onValueChange={setDriveId}>
                <SelectTrigger id="filter-drive">
                  <SelectValue placeholder="All drives" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All drives</SelectItem>
                  {driveOptions.map((drive) => (
                    <SelectItem key={drive.id} value={drive.id}>
                      {drive.company_name} · {drive.job_title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-department">Department</Label>
              <Select value={department} onValueChange={setDepartment}>
                <SelectTrigger id="filter-department">
                  <SelectValue placeholder="All departments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All departments</SelectItem>
                  {(filters.data?.departments ?? []).map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-status">Status</Label>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as "all" | ManagedApplicationStatus)}
              >
                <SelectTrigger id="filter-status">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="applied">Applied</SelectItem>
                  <SelectItem value="shortlisted">Shortlisted</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-assessment">Assessment</Label>
              <Select
                value={assessmentCompletion}
                onValueChange={(value) =>
                  setAssessmentCompletion(value as AdminAssessmentCompletionFilter)
                }
              >
                <SelectTrigger id="filter-assessment">
                  <SelectValue placeholder="All assessments" />
                </SelectTrigger>
                <SelectContent>
                  {ASSESSMENT_FILTERS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-from">Applied from</Label>
              <Input
                id="filter-from"
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="filter-to">Applied to</Label>
              <Input
                id="filter-to"
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </div>

            <div className="flex items-end">
              <Button
                variant="outline"
                className="w-full"
                onClick={clearFilters}
                disabled={!hasActiveFilters}
              >
                Clear filters
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-2 space-y-0 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="text-base">All applications</CardTitle>
            <CardDescription>
              {data
                ? `${total} application${total === 1 ? "" : "s"} matching the current filters.`
                : "Loading applications…"}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" className="gap-2" onClick={() => refetch()}>
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {isError ? (
            <div className="flex flex-col items-start gap-3 rounded-md border border-border p-4">
              <p className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="h-4 w-4" /> Could not load applications.
              </p>
              <Button variant="outline" size="sm" className="gap-2" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" /> Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : entries.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No applications match"
              description={
                hasActiveFilters
                  ? "Try clearing a filter to see more applications."
                  : "Students who apply to a drive will appear here."
              }
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[980px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Student</th>
                      <th className="py-2 pr-4 font-medium">Company</th>
                      <th className="py-2 pr-4 font-medium">Drive</th>
                      <th className="py-2 pr-4 font-medium">Assessment</th>
                      <th className="py-2 pr-4 font-medium">Ranking</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Applied</th>
                    </tr>
                  </thead>
                  <tbody className={cn(isFetching && "opacity-60 transition-opacity")}>
                    {entries.map((row) => (
                      <tr key={row.application_id} className="border-b border-border/60 last:border-0">
                        <td className="py-3 pr-4">
                          <p className="flex items-center gap-2 font-medium">
                            {row.student_name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {row.department ?? "Not specified"}
                          </p>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">{row.company_name}</td>
                        <td className="py-3 pr-4 text-muted-foreground">{row.job_title}</td>
                        <td className="py-3 pr-4">
                          <p className="text-muted-foreground">
                            {row.assessment_title ?? "No assessment"}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {assessmentLabel(row.assessment_status)}
                            {row.assessment_score_pct != null &&
                              ` · ${row.assessment_score_pct.toFixed(1)}%`}
                          </p>
                        </td>
                        <td className="py-3 pr-4 tabular-nums">
                          {row.rank != null ? `#${row.rank}` : "—"}
                        </td>
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-2">
                            <ApplicationStatusBadge status={row.status} />
                            <Select
                              value={row.status}
                              onValueChange={(value) =>
                                handleStatusChange(row, value as ManagedApplicationStatus)
                              }
                              disabled={updateStatus.isPending}
                            >
                              <SelectTrigger className="h-8 w-32 text-xs" aria-label="Change status">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {STATUS_OPTIONS.map((option) => (
                                  <SelectItem key={option} value={option}>
                                    {statusLabel(option)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </td>
                        <td className="py-3 text-muted-foreground">{formatDate(row.applied_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  Page {page} of {totalPages} · showing {entries.length} of {total}
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
    </div>
  );
}
