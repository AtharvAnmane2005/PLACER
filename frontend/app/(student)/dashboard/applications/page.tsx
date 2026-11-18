"use client";

import Link from "next/link";
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ClipboardList,
  Clock,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApplicationStatusBadge } from "@/components/shared/application-status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { MarkdownText } from "@/components/shared/markdown-text";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssessments } from "@/hooks/use-assessments";
import { useDrives, useMyApplications } from "@/hooks/use-drives";
import { useApplicationExplanation } from "@/hooks/use-explanation";
import { formatDate } from "@/lib/format";

const PAGE_SIZE = 10;

type StatusFilter = "all" | "applied" | "shortlisted" | "rejected";
type AssessmentFilter = "all" | "completed" | "pending" | "not_required";

/** Legacy `selected` rows are read as shortlisted, matching the analytics. */
function displayStatus(status: string): string {
  return status === "selected" ? "shortlisted" : status;
}

function assessmentLabel(status: string | undefined): string {
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

function ExplanationDrawer({ applicationId }: { applicationId: string }) {
  const { data: explanation, isLoading } = useApplicationExplanation(applicationId);

  if (isLoading) {
    return <Skeleton className="h-24 w-full" />;
  }
  if (!explanation) {
    return <p className="text-xs text-muted-foreground">No explanation report available yet.</p>;
  }

  return (
    <div className="space-y-3 rounded-b-md border-t border-border bg-muted/40 p-4 text-xs">
      {explanation.final_score !== null && (
        <div className="space-y-1.5 rounded border bg-card p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 font-semibold text-foreground">
              <Sparkles className="h-3.5 w-3.5 text-primary" /> Deterministic Match Score:{" "}
              {Math.round(explanation.final_score * 100)}%
            </span>
            {explanation.assessment_score_pct !== null && (
              <span className="font-mono text-muted-foreground">
                Assessment: {Math.round(explanation.assessment_score_pct)}% (
                {explanation.assessment_status})
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 pt-1 text-muted-foreground sm:grid-cols-3">
            <div>Semantic Relevance: {Math.round((explanation.semantic_score || 0) * 100)}%</div>
            <div>Skills Match: {Math.round((explanation.skills_score || 0) * 100)}%</div>
            <div>Exp Fit: {Math.round((explanation.experience_score || 0) * 100)}%</div>
          </div>
        </div>
      )}

      {explanation.rejection_reasons && explanation.rejection_reasons.length > 0 && (
        <div className="space-y-1 rounded border border-destructive/30 bg-destructive/10 p-3 text-destructive">
          <p className="flex items-center gap-1 font-semibold">
            <AlertCircle className="h-3.5 w-3.5" /> Decision Factors:
          </p>
          <p className="text-foreground">{explanation.rejection_reasons.join(", ")}</p>
          {explanation.rejection_note && (
            <p className="text-xs italic text-muted-foreground">
              &quot;{explanation.rejection_note}&quot;
            </p>
          )}
        </div>
      )}

      {explanation.narrative && (
        <div className="space-y-1.5 rounded border border-primary/20 bg-primary/5 p-3">
          <p className="flex items-center gap-1 font-semibold text-primary">
            <Brain className="h-3.5 w-3.5" /> Placement Advisor Insights:
          </p>
          <MarkdownText content={explanation.narrative} className="text-xs" />
        </div>
      )}
    </div>
  );
}

export default function ApplicationsPage() {
  const { data: applications, isLoading: applicationsLoading } = useMyApplications();
  const { data: drives, isLoading: drivesLoading } = useDrives();
  const { data: assessments } = useAssessments();
  const [expandedAppId, setExpandedAppId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [companyFilter, setCompanyFilter] = useState("all");
  const [driveFilter, setDriveFilter] = useState("all");
  const [assessmentFilter, setAssessmentFilter] = useState<AssessmentFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  // The dashboard donut links here with ?status=applied|shortlisted|...
  // Read it after mount so server/client markup stays identical.
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("status");
    if (param === "applied" || param === "shortlisted" || param === "rejected") {
      setStatusFilter(param);
    }
  }, []);

  const driveById = useMemo(
    () => new Map((drives ?? []).map((drive) => [drive.id, drive])),
    [drives]
  );
  const assessmentByDrive = useMemo(
    () =>
      new Map(
        (assessments ?? [])
          .filter((assessment) => assessment.drive_id)
          .map((assessment) => [assessment.drive_id as string, assessment])
      ),
    [assessments]
  );

  const rows = useMemo(() => {
    return (applications ?? []).map((application) => {
      const drive = driveById.get(application.drive_id);
      const assessment = assessmentByDrive.get(application.drive_id);
      return {
        application,
        drive,
        assessment,
        status: displayStatus(application.status),
        companyName: drive?.company.name ?? "—",
      };
    });
  }, [applications, driveById, assessmentByDrive]);

  const summary = useMemo(() => {
    const counts = { total: rows.length, applied: 0, shortlisted: 0, rejected: 0 };
    for (const row of rows) {
      if (row.status === "applied") counts.applied += 1;
      else if (row.status === "shortlisted") counts.shortlisted += 1;
      else if (row.status === "rejected") counts.rejected += 1;
    }
    return counts;
  }, [rows]);

  const companyOptions = useMemo(
    () => Array.from(new Set(rows.map((row) => row.companyName).filter((name) => name !== "—"))).sort(),
    [rows]
  );

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (companyFilter !== "all" && row.companyName !== companyFilter) return false;
      if (driveFilter !== "all" && row.application.drive_id !== driveFilter) return false;

      const assessmentStatus = row.application.assessment_status ?? "not_required";
      if (assessmentFilter === "completed" && !["passed", "failed"].includes(assessmentStatus)) {
        return false;
      }
      if (assessmentFilter === "pending" && !["pending", "expired"].includes(assessmentStatus)) {
        return false;
      }
      if (assessmentFilter === "not_required" && assessmentStatus !== "not_required") return false;

      const appliedAt = new Date(row.application.applied_at).getTime();
      if (dateFrom && appliedAt < new Date(`${dateFrom}T00:00:00`).getTime()) return false;
      if (dateTo && appliedAt > new Date(`${dateTo}T23:59:59.999`).getTime()) return false;
      return true;
    });
  }, [rows, statusFilter, companyFilter, driveFilter, assessmentFilter, dateFrom, dateTo]);

  const filterKey = `${statusFilter}|${companyFilter}|${driveFilter}|${assessmentFilter}|${dateFrom}|${dateTo}`;
  useEffect(() => {
    setPage(1);
  }, [filterKey]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const isLoading = applicationsLoading || drivesLoading;
  const hasActiveFilters =
    statusFilter !== "all" ||
    companyFilter !== "all" ||
    driveFilter !== "all" ||
    assessmentFilter !== "all" ||
    Boolean(dateFrom) ||
    Boolean(dateTo);

  const clearFilters = () => {
    setStatusFilter("all");
    setCompanyFilter("all");
    setDriveFilter("all");
    setAssessmentFilter("all");
    setDateFrom("");
    setDateTo("");
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">My Applications</h1>
        <p className="text-sm text-muted-foreground">
          Track application progress, review evaluations, and view constructive feedback.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total applications" value={summary.total} icon={ClipboardList} />
        <StatCard label="Applied / Under review" value={summary.applied} icon={Clock} />
        <StatCard label="Shortlisted" value={summary.shortlisted} icon={CheckCircle2} />
        <StatCard label="Rejected" value={summary.rejected} icon={XCircle} />
      </div>

      {!isLoading && rows.length > 0 && (
        <Card>
          <CardContent className="space-y-4 p-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="student-filter-company">Company</Label>
                <Select value={companyFilter} onValueChange={setCompanyFilter}>
                  <SelectTrigger id="student-filter-company">
                    <SelectValue placeholder="All companies" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All companies</SelectItem>
                    {companyOptions.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="student-filter-drive">Drive</Label>
                <Select value={driveFilter} onValueChange={setDriveFilter}>
                  <SelectTrigger id="student-filter-drive">
                    <SelectValue placeholder="All drives" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All drives</SelectItem>
                    {(drives ?? []).map((drive) => (
                      <SelectItem key={drive.id} value={drive.id}>
                        {drive.company.name} · {drive.job_title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="student-filter-status">Status</Label>
                <Select
                  value={statusFilter}
                  onValueChange={(value) => setStatusFilter(value as StatusFilter)}
                >
                  <SelectTrigger id="student-filter-status">
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
                <Label htmlFor="student-filter-assessment">Assessment</Label>
                <Select
                  value={assessmentFilter}
                  onValueChange={(value) => setAssessmentFilter(value as AssessmentFilter)}
                >
                  <SelectTrigger id="student-filter-assessment">
                    <SelectValue placeholder="All assessments" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All assessments</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="pending">Pending / expired</SelectItem>
                    <SelectItem value="not_required">Not required</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Date range lives on its own row so both native date inputs keep
                their intrinsic width and never collide with the selects. */}
            <div className="flex flex-col gap-3 border-t border-border pt-4 lg:flex-row lg:items-end lg:justify-between">
              <div className="w-full min-w-0 space-y-1.5 lg:max-w-sm">
                <Label htmlFor="student-filter-date-from">Applied between</Label>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Input
                    id="student-filter-date-from"
                    type="date"
                    aria-label="Applied from"
                    value={dateFrom}
                    max={dateTo || undefined}
                    onChange={(event) => setDateFrom(event.target.value)}
                    className="min-w-0 [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-60"
                  />
                  <Input
                    id="student-filter-date-to"
                    type="date"
                    aria-label="Applied to"
                    value={dateTo}
                    min={dateFrom || undefined}
                    onChange={(event) => setDateTo(event.target.value)}
                    className="min-w-0 [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-60"
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={clearFilters}
                  disabled={!hasActiveFilters}
                >
                  Clear filters
                </Button>
                <span className="text-xs text-muted-foreground">
                  Showing {filtered.length} of {rows.length}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No applications yet"
          description="Browse open drives and apply to see them tracked here."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No applications match"
          description="Try clearing a filter to see the rest of your applications."
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Company</th>
                    <th className="px-4 py-2 font-medium">Drive</th>
                    <th className="px-4 py-2 font-medium">Assessment</th>
                    <th className="px-4 py-2 font-medium">Score</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Applied</th>
                    <th className="px-4 py-2 font-medium">Report</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map(({ application, drive, assessment, status }) => {
                    const isExpanded = expandedAppId === application.id;
                    return (
                      <tr key={application.id} className="border-b border-border/60 last:border-0">
                        <td className="px-4 py-3 font-medium">{drive?.company.name ?? "—"}</td>
                        <td className="px-4 py-3 text-muted-foreground">
                          <Link
                            href={`/dashboard/drives/${application.drive_id}`}
                            className="hover:underline"
                          >
                            {drive?.job_title ?? "Drive"}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-muted-foreground">
                            {assessment?.title ?? "No assessment"}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {assessmentLabel(application.assessment_status)}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-1">
                            {application.assessment_score_pct != null && (
                              <Badge variant="outline" className="w-fit font-mono text-xs">
                                Assessment {application.assessment_score_pct.toFixed(1)}%
                              </Badge>
                            )}
                            {application.final_score != null && (
                              <Badge
                                variant="outline"
                                className="w-fit border-primary font-mono text-xs text-primary"
                              >
                                Match {Math.round(application.final_score * 100)}%
                              </Badge>
                            )}
                            {application.assessment_score_pct == null &&
                              application.final_score == null && (
                                <span className="text-muted-foreground">—</span>
                              )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <ApplicationStatusBadge status={status} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDate(application.applied_at)}
                        </td>
                        <td className="px-4 py-3">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setExpandedAppId(isExpanded ? null : application.id)}
                            className="h-8 gap-1 text-xs"
                          >
                            {isExpanded ? (
                              <>
                                Hide <ChevronUp className="h-3 w-3" />
                              </>
                            ) : (
                              <>
                                View <ChevronDown className="h-3 w-3" />
                              </>
                            )}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3 text-xs text-muted-foreground">
              <span>
                Page {page} of {totalPages} · showing {pageRows.length} of {filtered.length}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page >= totalPages}
                  aria-label="Next page"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {expandedAppId && (
        <Card>
          <CardContent className="p-0">
            <ExplanationDrawer applicationId={expandedAppId} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
