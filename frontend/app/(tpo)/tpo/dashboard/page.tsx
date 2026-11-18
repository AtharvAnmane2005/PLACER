"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, Briefcase, Percent, PlusCircle, Target, Users } from "lucide-react";

import { ApplicationRecordsPanel, type ApplicationDrilldownFilter } from "@/components/analytics/application-records-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ChartCard } from "@/components/shared/chart-card";
import { DonutChart } from "@/components/shared/donut-chart";
import { EmptyState } from "@/components/shared/empty-state";
import { GroupedBarChart } from "@/components/shared/grouped-bar-chart";
import { HorizontalBarChart } from "@/components/shared/horizontal-bar-chart";
import { StatCard } from "@/components/shared/stat-card";
import { useTpoApplicationAnalytics } from "@/hooks/use-analytics";
import { useMyDrives } from "@/hooks/use-tpo-drives";
import { CHART_PALETTE } from "@/lib/chart-theme";
import { formatCount, formatDate, formatMonthKey, formatPercent } from "@/lib/format";
import type { TpoCompanySort } from "@/types/analytics";

function formatDeadline(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

const TOP_N_OPTIONS = ["5", "8", "10", "15"] as const;
const MAX_CATEGORY_ROWS = 12;

const STATUS_SERIES = [
  { key: "Applied", label: "Applied" },
  { key: "Shortlisted", label: "Shortlisted" },
  { key: "Rejected", label: "Rejected" },
];

export default function TpoOverviewPage() {
  const { data: drives, isLoading } = useMyDrives();

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [topN, setTopN] = useState<string>("8");
  const [companySort, setCompanySort] = useState<TpoCompanySort>("applications");
  const [drilldown, setDrilldown] = useState<ApplicationDrilldownFilter | null>(null);

  const {
    data: applicationAnalytics,
    isLoading: analyticsLoading,
    isError: analyticsError,
    refetch: refetchAnalytics,
    isRefetching: analyticsRefetching,
    isFetching: analyticsFetching,
  } = useTpoApplicationAnalytics({
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    topN: Number(topN),
    companySort,
  });

  const openCount = drives?.filter((d) => d.status === "open").length ?? 0;
  const closedCount = drives?.filter((d) => d.status === "closed").length ?? 0;

  const breakdown = applicationAnalytics?.status_breakdown;
  const totalApplications = applicationAnalytics?.total_applications ?? 0;
  const studentsWithApplications = applicationAnalytics?.students_with_applications ?? 0;

  const statusData = [
    { name: "Applied", value: breakdown?.applied ?? 0 },
    { name: "Shortlisted", value: breakdown?.shortlisted ?? 0 },
    { name: "Rejected", value: breakdown?.rejected ?? 0 },
  ];
  const pipelineTotal = statusData.reduce((sum, entry) => sum + entry.value, 0);

  const departmentRowsAll =
    applicationAnalytics?.departments.map((row) => ({
      department: row.department,
      Applied: row.applied,
      Shortlisted: row.shortlisted,
      Rejected: row.rejected,
    })) ?? [];
  const departmentRows = departmentRowsAll.slice(0, MAX_CATEGORY_ROWS);

  const companyRows =
    applicationAnalytics?.companies.map((row) => ({
      name: row.company_name,
      value: row.total,
      color: CHART_PALETTE.blue,
      detail: `${row.applied} applied · ${row.shortlisted} shortlisted · ${row.rejected} rejected`,
    })) ?? [];
  const companyIdByName = new Map(
    (applicationAnalytics?.companies ?? []).map((row) => [row.company_name, row.company_id])
  );

  const driveRowsAll =
    applicationAnalytics?.drives.map((row) => ({
      drive: `${row.job_title} · ${row.company_name}`,
      Applied: row.applied,
      Shortlisted: row.shortlisted,
      Rejected: row.rejected,
    })) ?? [];
  const driveRows = driveRowsAll.slice(0, MAX_CATEGORY_ROWS);
  const driveIdByLabel = new Map(
    (applicationAnalytics?.drives ?? []).map((row) => [
      `${row.job_title} · ${row.company_name}`,
      row.drive_id,
    ])
  );

  const monthlyRows =
    applicationAnalytics?.monthly_trend.map((row) => ({
      month: row.month,
      Applied: row.applied,
      Shortlisted: row.shortlisted,
      Rejected: row.rejected,
    })) ?? [];
  const monthlyRangeNote =
    monthlyRows.length === 1
      ? `Every application in this view was submitted in ${formatMonthKey(monthlyRows[0]!.month)}, so the trend shows a single month. More months appear automatically as new applications arrive.`
      : "Each column is the month an application was submitted. Months with no applications are shown as zero so the timeline is never compressed.";

  const hasDateFilter = Boolean(dateFrom || dateTo);
  const rangeLabel = hasDateFilter
    ? `${dateFrom ? formatDate(dateFrom) : "first record"} to ${dateTo ? formatDate(dateTo) : "today"}`
    : "all recorded dates";
  const smallSample = totalApplications > 0 && totalApplications < 10;

  const filterDates = {
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold">TPO dashboard</h1>
          <p className="text-sm text-muted-foreground">Manage your placement drives and review applicants.</p>
        </div>
        <Button asChild>
          <Link href="/tpo/dashboard/drives/new">
            <PlusCircle className="mr-2 h-4 w-4" />
            New drive
          </Link>
        </Button>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Placement drives
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Total drives"
            value={isLoading ? <Skeleton className="h-7 w-10" /> : (drives?.length ?? 0)}
            icon={Briefcase}
          />
          <StatCard label="Open" value={isLoading ? <Skeleton className="h-7 w-10" /> : openCount} icon={Briefcase} />
          <StatCard label="Closed" value={isLoading ? <Skeleton className="h-7 w-10" /> : closedCount} icon={Users} />
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Application analytics
        </h2>

      {analyticsError ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
              <div>
                <p className="text-sm font-medium">Could not load application analytics</p>
                <p className="text-xs text-muted-foreground">
                  Your drives and applicants are unaffected. Check the date range and try again.
                </p>
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => refetchAnalytics()}
              disabled={analyticsRefetching}
            >
              {analyticsRefetching ? "Retrying…" : "Retry"}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs text-muted-foreground">
                {analyticsLoading ? (
                  "Loading application data…"
                ) : (
                  <>
                    Showing <span className="font-medium text-foreground">{formatCount(totalApplications)}</span>{" "}
                    {totalApplications === 1 ? "application" : "applications"} from{" "}
                    <span className="font-medium text-foreground">{formatCount(studentsWithApplications)}</span>{" "}
                    {studentsWithApplications === 1 ? "student" : "students"} · {rangeLabel}.
                    {smallSample && (
                      <span className="ml-1">
                        Small sample: counts are exact, but percentages are indicative.
                      </span>
                    )}
                  </>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  From
                  <Input
                    type="date"
                    value={dateFrom}
                    max={dateTo || undefined}
                    onChange={(event) => {
                      setDateFrom(event.target.value);
                      setDrilldown(null);
                    }}
                    className="h-9 w-[148px]"
                    aria-label="Filter applications from date"
                  />
                </label>
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  To
                  <Input
                    type="date"
                    value={dateTo}
                    min={dateFrom || undefined}
                    onChange={(event) => {
                      setDateTo(event.target.value);
                      setDrilldown(null);
                    }}
                    className="h-9 w-[148px]"
                    aria-label="Filter applications to date"
                  />
                </label>
                {hasDateFilter && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setDateFrom("");
                      setDateTo("");
                      setDrilldown(null);
                    }}
                  >
                    Clear
                  </Button>
                )}
                {analyticsFetching && !analyticsLoading && (
                  <span className="text-xs text-muted-foreground">Updating…</span>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total students"
              value={analyticsLoading ? <Skeleton className="h-7 w-10" /> : formatCount(studentsWithApplications)}
              icon={Users}
            />
            <StatCard
              label="Applications"
              value={analyticsLoading ? <Skeleton className="h-7 w-10" /> : formatCount(totalApplications)}
              icon={Briefcase}
            />
            <StatCard
              label="Shortlisting rate"
              value={
                analyticsLoading ? (
                  <Skeleton className="h-7 w-14" />
                ) : (
                  formatPercent(applicationAnalytics?.shortlisting_rate_pct ?? 0, 1)
                )
              }
              icon={Target}
            />
            <StatCard
              label="Rejection rate"
              value={
                analyticsLoading ? (
                  <Skeleton className="h-7 w-14" />
                ) : (
                  formatPercent(applicationAnalytics?.rejection_rate_pct ?? 0, 1)
                )
              }
              icon={Percent}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Application status"
              description="Applied, shortlisted and rejected applications across your drives. Exact counts and shares are listed under the ring; click a slice to list those applications."
              footer="PLACER stores one current status per application, so this ring is a status snapshot of the three stages you manage."
            >
              {analyticsLoading ? (
                <Skeleton className="h-[240px] w-full" />
              ) : (
                <DonutChart
                  data={statusData}
                  ariaLabel="Application status donut chart for your drives"
                  centerValue={pipelineTotal}
                  centerLabel="in the pipeline"
                  onSliceClick={(name) =>
                    setDrilldown({ status: name.toLowerCase(), ...filterDates })
                  }
                  emptyTitle="No applications yet"
                  emptyDescription="Applications to your drives will appear here as students apply."
                />
              )}
            </ChartCard>

            <ChartCard
              title="Company-wise applications"
              description="Companies ranked by total applications, with each company's applied/shortlisted/rejected split in the tooltip. Click a bar to list that company's applications."
              action={
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={companySort} onValueChange={(value) => setCompanySort(value as TpoCompanySort)}>
                    <SelectTrigger className="h-9 w-[168px]" aria-label="Sort companies by">
                      <SelectValue placeholder="Sort by" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="applications">Most applications</SelectItem>
                      <SelectItem value="shortlisted">Most shortlisted</SelectItem>
                      <SelectItem value="name">Company name</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={topN} onValueChange={setTopN}>
                    <SelectTrigger className="h-9 w-[112px]" aria-label="Number of companies to show">
                      <SelectValue placeholder="Top N" />
                    </SelectTrigger>
                    <SelectContent>
                      {TOP_N_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          Top {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              }
              footer={`${formatCount(applicationAnalytics?.company_count ?? 0)} ${
                (applicationAnalytics?.company_count ?? 0) === 1 ? "company has" : "companies have"
              } applications in this view. Bars show total applications per company.`}
            >
              {analyticsLoading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : (
                <HorizontalBarChart
                  data={companyRows}
                  ariaLabel="Company-wise application totals horizontal bar chart"
                  valueLabel="Applications"
                  shareTotal={totalApplications}
                  onBarClick={(name) =>
                    setDrilldown({
                      companyId: companyIdByName.get(name) ?? undefined,
                      companyName: name,
                      ...filterDates,
                    })
                  }
                  emptyTitle="No company activity in this view"
                  emptyDescription="Try widening the date range or clearing the filters."
                />
              )}
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Department-wise applications and shortlisting"
              description="Every application to your drives, grouped by the student's recorded department. Click a bar to list that department's applications."
              footer={
                departmentRowsAll.length > MAX_CATEGORY_ROWS
                  ? `Showing the ${MAX_CATEGORY_ROWS} departments with the most applications of ${departmentRowsAll.length}.`
                  : "Departments are normalised, so aliases such as “CS” and “Computer Science” are combined."
              }
            >
              {analyticsLoading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : (
                <GroupedBarChart
                  data={departmentRows}
                  categoryKey="department"
                  series={STATUS_SERIES}
                  ariaLabel="Department-wise applications and shortlisting grouped bar chart"
                  categoryAxisLabel="Department"
                  valueAxisLabel="Applications"
                  xTickAngle={-15}
                  showValueLabels
                  onBarClick={(name) => setDrilldown({ department: name, ...filterDates })}
                  emptyTitle="No applications for this view"
                  emptyDescription="Applications will appear once students apply to your drives."
                />
              )}
            </ChartCard>

            <ChartCard
              title="Drive-wise applications and shortlisting"
              description="Only drives that received at least one application are shown. Click a bar to list that drive's applications."
              footer={
                driveRowsAll.length > MAX_CATEGORY_ROWS
                  ? `Showing the ${MAX_CATEGORY_ROWS} drives with the most applications of ${driveRowsAll.length} drives that received applications.`
                  : `${formatCount(applicationAnalytics?.drive_count ?? 0)} ${
                      (applicationAnalytics?.drive_count ?? 0) === 1 ? "drive has" : "drives have"
                    } received applications in this view.`
              }
            >
              {analyticsLoading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : (
                <GroupedBarChart
                  data={driveRows}
                  categoryKey="drive"
                  series={STATUS_SERIES}
                  ariaLabel="Drive-wise applications and shortlisting grouped bar chart"
                  categoryAxisLabel="Drive · company"
                  valueAxisLabel="Applications"
                  xTickAngle={-15}
                  showValueLabels
                  onBarClick={(label) => {
                    const driveId = driveIdByLabel.get(label);
                    setDrilldown({ driveId, driveLabel: label, ...filterDates });
                  }}
                  emptyTitle="No drives with applications yet"
                  emptyDescription="A drive appears here once a student applies to it."
                />
              )}
            </ChartCard>
          </div>

          <ChartCard
            title="Monthly Application Trends"
            description={`Applications grouped by the month they were submitted, from ${rangeLabel}. Every month in the range is shown, including zero-activity months.`}
            footer={monthlyRangeNote}
          >
            {analyticsLoading ? (
              <Skeleton className="h-[280px] w-full" />
            ) : (
              <GroupedBarChart
                data={monthlyRows}
                categoryKey="month"
                series={STATUS_SERIES}
                ariaLabel="Monthly application trends column chart"
                categoryAxisLabel="Month applied"
                valueAxisLabel="Applications"
                categoryFormatter={formatMonthKey}
                showValueLabels
                emptyTitle="No applications in this range"
                emptyDescription="Widen or clear the date range to see your application history."
              />
            )}
          </ChartCard>

          {drilldown && (
            <ApplicationRecordsPanel filter={drilldown} onClear={() => setDrilldown(null)} />
          )}
        </>
      )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent drives</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : !drives || drives.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No drives yet"
              description="Create your first placement drive to start accepting applications."
              action={
                <Button asChild size="sm">
                  <Link href="/tpo/dashboard/drives/new">Create a drive</Link>
                </Button>
              }
            />
          ) : (
            <div className="space-y-2">
              {drives.slice(0, 5).map((drive) => (
                <Link key={drive.id} href={`/tpo/dashboard/drives/${drive.id}`}>
                  <div className="flex items-center justify-between gap-3 rounded-md border border-border px-4 py-3 text-sm transition-colors hover:border-primary">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{drive.job_title}</p>
                      <p className="truncate text-muted-foreground">
                        {drive.company.name} · Apply by {formatDeadline(drive.deadline)}
                      </p>
                    </div>
                    <Badge
                      variant={drive.status === "open" ? "success" : "secondary"}
                      className="shrink-0"
                    >
                      {drive.status}
                    </Badge>
                  </div>
                </Link>
              ))}
              {drives.length > 5 && (
                <Link href="/tpo/dashboard/drives" className="inline-block text-sm text-primary underline underline-offset-2">
                  View all {drives.length} drives
                </Link>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
