"use client";

import Link from "next/link";
import {
  AlertCircle,
  Briefcase,
  Building2,
  GraduationCap,
  ListChecks,
  PlusCircle,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ChartCard } from "@/components/shared/chart-card";
import { DonutChart } from "@/components/shared/donut-chart";
import { StatCard } from "@/components/shared/stat-card";
import { useAdminActivity, useAdminAnalytics } from "@/hooks/use-analytics";
import { CHART_PALETTE } from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";

const ROLE_LABELS: Record<string, string> = {
  student: "Students",
  tpo: "TPOs",
  admin: "Admins",
};

function Metric({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold leading-tight tabular-nums text-foreground">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export default function AdminOverviewPage() {
  const {
    data: adminAnalytics,
    isLoading: adminAnalyticsLoading,
    isError: adminAnalyticsError,
    refetch: refetchAdminAnalytics,
    isRefetching: adminAnalyticsRefetching,
  } = useAdminAnalytics();

  const {
    data: activity,
    isLoading: activityLoading,
    isError: activityError,
    refetch: refetchActivity,
    isRefetching: activityRefetching,
  } = useAdminActivity();

  const totalApplications = adminAnalytics?.total_applications ?? 0;
  const totalStudents = adminAnalytics?.total_students ?? 0;
  const studentsWithApplications = adminAnalytics?.students_with_applications ?? 0;
  const totalTpos = adminAnalytics?.total_tpos ?? 0;
  const totalCompanies = adminAnalytics?.total_companies ?? 0;
  const totalDrives = adminAnalytics?.total_drives ?? 0;
  const openDrives = adminAnalytics?.open_drives ?? 0;
  const closedDrives = adminAnalytics?.closed_drives ?? 0;
  const totalAttempts = adminAnalytics?.total_attempts ?? 0;
  const submittedAttempts = adminAnalytics?.submitted_attempts ?? 0;
  const completionRate = totalAttempts > 0 ? (submittedAttempts / totalAttempts) * 100 : null;

  const roleData =
    activity?.user_distribution.map((row) => ({
      name: ROLE_LABELS[row.role] ?? row.role,
      value: row.count,
    })) ?? [];

  const platformSnapshot = [
    {
      label: "Total students",
      value: formatCount(totalStudents),
      detail: `${formatCount(studentsWithApplications)} with at least one application`,
      color: CHART_PALETTE.blue,
    },
    {
      label: "Total companies",
      value: formatCount(totalCompanies),
      detail: "companies with at least one drive",
      color: CHART_PALETTE.purple,
    },
    {
      label: "Total drives",
      value: formatCount(totalDrives),
      detail: `${formatCount(openDrives)} open · ${formatCount(closedDrives)} closed`,
      color: CHART_PALETTE.green,
    },
    {
      label: "Students with applications",
      value: formatCount(studentsWithApplications),
      detail: "students, not application records",
      color: CHART_PALETTE.amber,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Admin overview</h1>
          <p className="text-sm text-muted-foreground">
            Platform activity, assessment performance and the question bank in one place.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/admin/dashboard/questions/new">
              <PlusCircle className="mr-2 h-4 w-4" />
              New question
            </Link>
          </Button>
          <Button asChild>
            <Link href="/admin/dashboard/assessments/new">
              <PlusCircle className="mr-2 h-4 w-4" />
              New assessment
            </Link>
          </Button>
        </div>
      </div>

      {adminAnalyticsError ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
              <div>
                <p className="text-sm font-medium">Could not load platform analytics</p>
                <p className="text-xs text-muted-foreground">
                  The question bank and assessment tools are unaffected. Try again.
                </p>
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => refetchAdminAnalytics()}
              disabled={adminAnalyticsRefetching}
            >
              {adminAnalyticsRefetching ? "Retrying…" : "Retry"}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">Platform</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              <StatCard
                label="Students"
                value={adminAnalyticsLoading ? <Skeleton className="h-7 w-12" /> : formatCount(totalStudents)}
                hint={`${formatCount(studentsWithApplications)} with at least one application`}
                icon={GraduationCap}
              />
              <StatCard
                label="Companies"
                value={adminAnalyticsLoading ? <Skeleton className="h-7 w-12" /> : formatCount(totalCompanies)}
                hint="Companies with at least one drive"
                icon={Building2}
              />
              <StatCard
                label="Drives"
                value={adminAnalyticsLoading ? <Skeleton className="h-7 w-12" /> : formatCount(totalDrives)}
                hint={`${formatCount(openDrives)} open · ${formatCount(closedDrives)} closed`}
                icon={Briefcase}
              />
              <StatCard
                label="Applications"
                value={adminAnalyticsLoading ? <Skeleton className="h-7 w-12" /> : formatCount(totalApplications)}
                hint="Across all drives"
                icon={ListChecks}
              />
              <StatCard
                label="TPOs"
                value={adminAnalyticsLoading ? <Skeleton className="h-7 w-12" /> : formatCount(totalTpos)}
                hint="Placement officers"
                icon={Users}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <ChartCard
                title="Platform snapshot"
                description="Live totals from the platform's own records."
              >
                {adminAnalyticsLoading ? (
                  <Skeleton className="h-[240px] w-full" />
                ) : (
                  <div className="space-y-3 py-1">
                    {platformSnapshot.map((row) => (
                      <div
                        key={row.label}
                        className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5"
                      >
                        <span className="flex items-center gap-2 text-sm">
                          <span
                            aria-hidden="true"
                            className="inline-block h-2.5 w-2.5 rounded-sm"
                            style={{ backgroundColor: row.color }}
                          />
                          {row.label}
                        </span>
                        <span className="text-right tabular-nums">
                          <span className="text-sm font-semibold">{row.value}</span>
                          <span className="block text-xs text-muted-foreground">{row.detail}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </ChartCard>

              {activityError ? (
                <Card>
                  <CardContent className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
                      <div>
                        <p className="text-sm font-medium">Could not load user distribution</p>
                        <p className="text-xs text-muted-foreground">Try again.</p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => refetchActivity()}
                      disabled={activityRefetching}
                    >
                      {activityRefetching ? "Retrying…" : "Retry"}
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <ChartCard title="User distribution" description="Every account in the system, counted once.">
                  {activityLoading ? (
                    <Skeleton className="h-[240px] w-full" />
                  ) : (
                    <DonutChart
                      data={roleData}
                      ariaLabel="User distribution by role donut chart"
                      centerValue={activity?.total_users ?? 0}
                      centerLabel="total accounts"
                      emptyTitle="No accounts yet"
                      emptyDescription="User accounts will appear here once people register."
                    />
                  )}
                </ChartCard>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">Assessment performance</h2>
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
                  <Metric
                    label="Assessments"
                    value={adminAnalyticsLoading ? <Skeleton className="h-6 w-10" /> : formatCount(adminAnalytics?.total_assessments)}
                  />
                  <Metric
                    label="Attempts"
                    value={adminAnalyticsLoading ? <Skeleton className="h-6 w-10" /> : formatCount(totalAttempts)}
                  />
                  <Metric
                    label="Submitted"
                    value={adminAnalyticsLoading ? <Skeleton className="h-6 w-10" /> : formatCount(submittedAttempts)}
                    hint="Completed attempts"
                  />
                  <Metric
                    label="Average score"
                    value={
                      adminAnalyticsLoading ? (
                        <Skeleton className="h-6 w-12" />
                      ) : (
                        formatPercent(adminAnalytics?.average_score_pct, 1)
                      )
                    }
                    hint="Submitted attempts"
                  />
                  <Metric
                    label="Completion rate"
                    value={
                      adminAnalyticsLoading ? (
                        <Skeleton className="h-6 w-12" />
                      ) : (
                        formatPercent(completionRate, 1)
                      )
                    }
                    hint="Submitted ÷ all attempts"
                  />
                  <Metric
                    label="Questions"
                    value={adminAnalyticsLoading ? <Skeleton className="h-6 w-10" /> : formatCount(adminAnalytics?.total_questions)}
                    hint="Question bank"
                  />
                  <Metric
                    label="Categories"
                    value={adminAnalyticsLoading ? <Skeleton className="h-6 w-10" /> : formatCount(adminAnalytics?.total_categories)}
                    hint="Question bank"
                  />
                </div>
              </CardContent>
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
