"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, Award, Briefcase, ClipboardList, FileText, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ChartCard } from "@/components/shared/chart-card";
import { DonutChart } from "@/components/shared/donut-chart";
import { DomainRadarChart } from "@/components/shared/radar-chart";
import { StatCard } from "@/components/shared/stat-card";
import { TrendLineChart } from "@/components/shared/trend-line-chart";
import { useStudentAnalytics } from "@/hooks/use-analytics";
import { useMyApplications } from "@/hooks/use-drives";
import { useResumeHistory } from "@/hooks/use-resumes";
import { useKnowledgeStates } from "@/hooks/use-assessments";
import { useStudentProfile } from "@/hooks/use-student-profile";
import { CHART_PALETTE } from "@/lib/chart-theme";
import { formatCount, formatDate, formatPercent } from "@/lib/format";
import { severityColorFromMastery } from "@/lib/severity";

export default function StudentOverviewPage() {
  const router = useRouter();
  const { data: profile, isLoading: profileLoading } = useStudentProfile();
  const { data: resumes, isLoading: resumesLoading } = useResumeHistory();
  const { data: applications, isLoading: applicationsLoading } = useMyApplications();
  const { data: knowledgeStates, isLoading: knowledgeLoading } = useKnowledgeStates();
  const {
    data: analytics,
    isLoading: analyticsLoading,
    isError: analyticsError,
    refetch: refetchAnalytics,
    isRefetching: analyticsRefetching,
  } = useStudentAnalytics();

  const activeResume = resumes?.find((r) => r.is_active) ?? null;
  const shortlistedCount = analytics?.applications.shortlisted ?? 0;
  const averageScore = analytics?.average_score_pct ?? null;

  const statusData = [
    { name: "Applied", value: analytics?.applications.applied ?? 0 },
    { name: "Shortlisted", value: analytics?.applications.shortlisted ?? 0 },
    { name: "Rejected", value: analytics?.applications.rejected ?? 0 },
  ];
  const pipelineTotal = statusData.reduce((sum, entry) => sum + entry.value, 0);
  const totalApplications = analytics?.total_applications ?? 0;
  const answeredDomains = analytics?.domain_scores.reduce((sum, row) => sum + row.answered, 0) ?? 0;
  const radarData =
    analytics?.domain_scores.map((row) => ({ subject: row.domain, value: row.score_pct })) ?? [];
  const trendData =
    analytics?.assessment_trend.map((point) => ({
      submitted_at: point.submitted_at,
      score: point.score_pct,
      title: point.assessment_title,
    })) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">
          Welcome back{profile?.name ? `, ${profile.name.trim().split(/\s+/)[0] ?? profile.name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">Here&apos;s where your placement prep stands today.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Resume status"
          value={resumesLoading ? <Skeleton className="h-7 w-16" /> : activeResume ? "Uploaded" : "Not uploaded"}
          icon={FileText}
        />
        <StatCard
          label="Applications"
          value={applicationsLoading ? <Skeleton className="h-7 w-10" /> : (applications?.length ?? 0)}
          icon={Briefcase}
        />
        <StatCard
          label="Shortlisted"
          value={analyticsLoading ? <Skeleton className="h-7 w-10" /> : shortlistedCount}
          icon={ClipboardList}
        />
        <StatCard
          label="Avg. assessment score"
          value={
            analyticsLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : averageScore !== null ? (
              `${averageScore.toFixed(1)}%`
            ) : (
              "—"
            )
          }
          icon={TrendingUp}
        />
      </div>

      {analyticsError ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
              <div>
                <p className="text-sm font-medium">Could not load your analytics</p>
                <p className="text-xs text-muted-foreground">
                  Your applications and assessment results are unaffected. Try again.
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
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard
              title="Application status"
              description={`Applied, shortlisted and rejected applications. Exact counts and shares are listed under the ring; click a slice to open those applications.`}
              footer={
                totalApplications > 0 ? (
                  <>
                    Shortlisting rate{" "}
                    <span className="font-medium text-foreground">
                      {formatPercent(analytics?.shortlisting_rate_pct ?? 0, 1)}
                    </span>{" "}
                    · Rejection rate{" "}
                    <span className="font-medium text-foreground">
                      {formatPercent(analytics?.rejection_rate_pct ?? 0, 1)}
                    </span>{" "}
                    · based on {formatCount(totalApplications)}{" "}
                    {totalApplications === 1 ? "application" : "applications"}.
                  </>
                ) : (
                  "Rates appear once you have at least one application."
                )
              }
            >
              {analyticsLoading ? (
                <Skeleton className="h-[240px] w-full" />
              ) : (
                <DonutChart
                  data={statusData}
                  ariaLabel="Application status donut chart"
                  centerValue={pipelineTotal}
                  centerLabel="in the pipeline"
                  onSliceClick={(name) =>
                    router.push(`/dashboard/applications?status=${name.toLowerCase()}`)
                  }
                  emptyTitle="No applications yet"
                  emptyDescription="Apply to a drive and its status will appear here."
                />
              )}
            </ChartCard>

            <ChartCard
              title="Domain readiness"
              description="Difficulty-weighted score across the five placement domains, using graded answers only. Scores are shown on a 0–100 scale."
              footer={
                answeredDomains > 0
                  ? `Based on ${formatCount(answeredDomains)} graded answers across ${formatCount(
                      analytics?.submitted_attempt_count ?? 0
                    )} submitted ${(analytics?.submitted_attempt_count ?? 0) === 1 ? "assessment" : "assessments"}.`
                  : "No graded answers yet. Submit an assessment with graded questions to see your domain profile."
              }
            >
              {analyticsLoading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : (
                <DomainRadarChart
                  data={radarData}
                  hasData={answeredDomains > 0}
                  ariaLabel="Five-domain assessment readiness radar chart"
                />
              )}
            </ChartCard>
          </div>

          <ChartCard
            title="Assessment score trend"
            description="Submitted assessments in chronological order, scored the same way as each result page."
            footer={`Based on ${formatCount(analytics?.submitted_attempt_count ?? 0)} graded ${
              (analytics?.submitted_attempt_count ?? 0) === 1 ? "submission" : "submissions"
            }. In-progress attempts and submitted attempts with no graded answers are excluded.`}
            action={
              <Button asChild size="sm" variant="secondary">
                <Link href="/dashboard/assessments">Assessments</Link>
              </Button>
            }
          >
            {analyticsLoading ? (
              <Skeleton className="h-[280px] w-full" />
            ) : (
              <TrendLineChart
                data={trendData}
                xKey="submitted_at"
                series={[{ key: "score", label: "Score", color: CHART_PALETTE.purple }]}
                ariaLabel="Assessment score trend line chart"
                yDomain={[0, 100]}
                valueFormatter={(value) => formatPercent(value, 1)}
                xValueFormatter={(value) => formatDate(value)}
                xAxisLabel="Submission date"
                yAxisLabel="Score"
                showValueLabels
                emptyTitle="No completed assessments yet"
                emptyDescription="Submit an assessment with graded answers to start tracking your scores."
              />
            )}
          </ChartCard>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile completeness</CardTitle>
            <CardDescription>A fuller profile helps TPOs and drive eligibility checks.</CardDescription>
          </CardHeader>
          <CardContent>
            {profileLoading || !profile ? (
              <Skeleton className="h-4 w-full" />
            ) : (
              <>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{profile.profile_completeness_pct}% complete</span>
                </div>
                <Progress value={profile.profile_completeness_pct} />
                {profile.profile_completeness_pct < 100 && (
                  <Button asChild size="sm" variant="secondary" className="mt-4">
                    <Link href="/dashboard/profile">Complete your profile</Link>
                  </Button>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Resume</CardTitle>
            <CardDescription>
              {activeResume
                ? `Active version: ${activeResume.original_filename}`
                : "No resume on file yet — upload one to start applying to drives."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild size="sm">
              <Link href="/dashboard/resume">{activeResume ? "Manage resume" : "Upload resume"}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Award className="h-4 w-4" /> Knowledge tracing snapshot
          </CardTitle>
          <CardDescription>Mastery estimates from your adaptive assessment attempts.</CardDescription>
        </CardHeader>
        <CardContent>
          {knowledgeLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : !knowledgeStates || knowledgeStates.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No assessments taken yet.{" "}
              <Link href="/dashboard/assessments" className="text-primary underline underline-offset-2">
                Take one
              </Link>{" "}
              to start building your skill profile.
            </div>
          ) : (
            <div className="space-y-3">
              {knowledgeStates.slice(0, 5).map((state) => (
                <div key={state.skill_tag} className="flex items-center gap-2 sm:gap-3">
                  <Badge
                    variant="outline"
                    className="w-24 shrink-0 justify-center truncate sm:w-28"
                  >
                    {state.skill_tag}
                  </Badge>
                  <Progress
                    value={state.mastery_pct}
                    className="min-w-0 flex-1"
                    indicatorStyle={{ backgroundColor: severityColorFromMastery(state.mastery_pct) }}
                  />
                  <span className="w-10 shrink-0 text-right text-sm text-muted-foreground">
                    {Math.round(state.mastery_pct)}%
                  </span>
                </div>
              ))}
              {knowledgeStates.length > 5 && (
                <Link href="/dashboard/assessments" className="inline-block text-sm text-primary underline underline-offset-2">
                  View all {knowledgeStates.length} skills
                </Link>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
