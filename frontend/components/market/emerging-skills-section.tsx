"use client";

import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CHART_AXIS_STYLE,
  CHART_CURSOR_FILL,
  CHART_GRID_STROKE,
  CHART_PALETTE,
  categoryColor,
  chartAxisLabel,
  percentTick,
} from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";
import {
  buildEmergingCandidates,
  formatSignedGrowth,
  summarizeEmerging,
  type EmergingCandidate,
} from "@/lib/market-insights";
import type {
  EmergingSkill,
  HistoricalSkillTrend,
  MarketMeta,
  TrendingSkill,
} from "@/types/market-analytics";

function HistoryTooltip({
  active,
  payload,
  skillName,
  color,
}: {
  active?: boolean;
  payload?: Array<{
    payload: {
      year: number;
      postings: number;
      share: number;
      yoyGrowthPct: number | null;
    };
  }>;
  skillName: string;
  color: string;
}) {
  const entry = payload?.[0];
  if (!active || !entry) return null;
  const point = entry.payload;
  return (
    <ChartTooltipCard
      title={point.year}
      rows={[
        {
          label: skillName,
          value: `${formatCount(point.postings)} posting${point.postings === 1 ? "" : "s"}`,
          color,
          detail: `${formatPercent(point.share, 1)} of that comparable window's postings`,
        },
      ]}
      footer={
        point.yoyGrowthPct == null
          ? "No comparable previous period"
          : `${formatSignedGrowth(point.yoyGrowthPct)} vs the previous comparable window`
      }
    />
  );
}

function LollipopTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: EmergingCandidate }>;
}) {
  const candidate = payload?.[0]?.payload;
  if (!active || !candidate) return null;
  return (
    <ChartTooltipCard
      title={candidate.name}
      subtitle={candidate.category ?? undefined}
      rows={[
        {
          label: "Current demand",
          value: `${formatCount(candidate.currentCount)} posting${candidate.currentCount === 1 ? "" : "s"}`,
          detail:
            candidate.currentWindowDemandPct != null
              ? `${formatPercent(candidate.currentWindowDemandPct, 1)} of the current window`
              : undefined,
        },
        {
          label: "Previous demand",
          value: `${formatCount(candidate.previousCount)} posting${candidate.previousCount === 1 ? "" : "s"}`,
          detail: "comparable previous window",
        },
        {
          label: "Growth",
          value:
            candidate.growthPct == null
              ? "—"
              : formatSignedGrowth(candidate.growthPct),
          color: CHART_PALETTE.red,
        },
      ]}
    />
  );
}

interface LollipopShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: EmergingCandidate;
}

/** Thin stem + circular marker + value label, drawn as one bar shape. */
function LollipopShape(props: LollipopShapeProps) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props;
  const centerY = y + height / 2;
  const endX = x + Math.max(width, 0);
  return (
    <g>
      <line
        x1={x}
        y1={centerY}
        x2={endX}
        y2={centerY}
        stroke={CHART_PALETTE.red}
        strokeWidth={2}
        strokeLinecap="round"
      />
      <circle
        cx={endX}
        cy={centerY}
        r={5.5}
        fill={CHART_PALETTE.red}
        stroke="#FFFFFF"
        strokeWidth={1.5}
      />
      {payload?.growthPct != null && (
        <text
          x={endX + 9}
          y={centerY}
          dy="0.32em"
          fill="#475569"
          fontSize={11}
          fontWeight={600}
        >
          {formatSignedGrowth(payload.growthPct)}
        </text>
      )}
    </g>
  );
}

function TrajectoryChart({
  candidate,
  meta,
}: {
  candidate: EmergingCandidate;
  meta: MarketMeta | undefined;
}) {
  const chartData = candidate.series.map((point) => ({
    year: point.year,
    postings: point.windowPostingCount,
    share: point.windowDemandPct,
    yoyGrowthPct: point.yoyGrowthPct,
  }));
  if (chartData.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No historical demand series is available for this skill under the current filters.
      </p>
    );
  }
  const showPartialNote =
    meta?.is_partial_year &&
    meta?.current_period != null &&
    candidate.series.some((point) => point.year === meta.current_period!.year);
  const color = categoryColor(candidate.name);
  const yMax = Math.max(
    1,
    Math.ceil(Math.max(...chartData.map((point) => point.postings)) * 1.15)
  );
  return (
    <div className="space-y-2 pt-2">
      <div className="overflow-hidden" role="img" aria-label={`Demand history for ${candidate.name}`}>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
            <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="year"
              tick={CHART_AXIS_STYLE}
              tickMargin={6}
              height={30}
              allowDecimals={false}
              label={chartAxisLabel("Year")}
            />
            <YAxis
              domain={[0, yMax]}
              allowDecimals={false}
              tick={CHART_AXIS_STYLE}
              tickMargin={4}
              width={52}
              label={chartAxisLabel("Postings requiring the skill", "insideLeft")}
            />
            <Tooltip content={<HistoryTooltip skillName={candidate.name} color={color} />} />
            <Line
              type="monotone"
              dataKey="postings"
              name={candidate.name}
              stroke={color}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend
        className="justify-start"
        ariaLabel={`Demand history legend for ${candidate.name}`}
        items={[{ label: candidate.name, color }]}
      />
      {showPartialNote && (
        <p className="text-xs text-muted-foreground">
          <Badge variant="warning">{meta!.comparison_period} only</Badge>{" "}
          Every point uses the same comparable window as the growth figure.
        </p>
      )}
    </div>
  );
}

function CurrentDemandFallback({ skills }: { skills: TrendingSkill[] }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Growth classifications need postings from two comparable periods. Current demand
        leaders under the current filters:
      </p>
      <ul className="divide-y divide-border rounded-md border border-border">
        {skills.map((skill) => (
          <li
            key={skill.slug}
            className="flex items-center justify-between gap-3 p-2.5 text-sm"
          >
            <span className="min-w-0 truncate">{skill.name}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {formatCount(skill.posting_count)} postings ·{" "}
              {formatPercent(skill.demand_pct, 1)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Emerging & rising skills.
 *
 * The lollipop plots only skills with a numeric comparable growth value
 * (brand-red stem + marker, sorted high to low). Skills that appeared in the
 * current window but had no demand in the comparable previous window are
 * listed separately as "Newly emerged" because their growth is undefined, not
 * zero. Every figure comes from the backend response; no growth is invented.
 */
export function EmergingSkillsSection({
  emerging,
  trending,
  historical,
  meta,
  isLoading,
}: {
  emerging: EmergingSkill[] | undefined;
  trending: TrendingSkill[] | undefined;
  historical: HistoricalSkillTrend[] | undefined;
  meta: MarketMeta | undefined;
  isLoading: boolean;
}) {
  const [historySlug, setHistorySlug] = useState<string | null>(null);

  const candidates = useMemo(
    () =>
      emerging && trending && historical
        ? buildEmergingCandidates(trending, emerging, historical, meta)
        : [],
    [emerging, trending, historical, meta]
  );
  const summary = useMemo(
    () => summarizeEmerging(emerging ?? [], candidates),
    [emerging, candidates]
  );

  const growthCandidates = useMemo(
    () =>
      candidates
        .filter(
          (candidate): candidate is EmergingCandidate & { growthPct: number } =>
            candidate.growthPct != null && candidate.growthPct > 0
        )
        .sort(
          (a, b) => b.growthPct - a.growthPct || a.name.localeCompare(b.name)
        ),
    [candidates]
  );

  const newlyEmerged = useMemo(
    () =>
      candidates
        .filter((candidate) => candidate.growthPct == null)
        .sort(
          (a, b) => b.currentCount - a.currentCount || a.name.localeCompare(b.name)
        ),
    [candidates]
  );

  const currentDemand = useMemo(
    () =>
      [...(trending ?? [])]
        .sort(
          (a, b) => b.posting_count - a.posting_count || a.name.localeCompare(b.name)
        )
        .slice(0, 8),
    [trending]
  );

  // Declining skills use the backend's own classification and signed growth.
  // They are listed explicitly because a "rising skills" chart alone hides the
  // decline the TPO team most needs to act on.
  const declining = useMemo(
    () =>
      [...(trending ?? [])]
        .filter(
          (skill): skill is TrendingSkill & { yoy_growth_pct: number } =>
            skill.trend === "declining" && skill.yoy_growth_pct != null
        )
        .sort(
          (a, b) =>
            a.yoy_growth_pct - b.yoy_growth_pct || a.name.localeCompare(b.name)
        ),
    [trending]
  );

  const historyCandidate = historySlug
    ? candidates.find((candidate) => candidate.slug === historySlug)
    : undefined;
  const historyOptions = [...growthCandidates, ...newlyEmerged];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4" /> Emerging &amp; rising skills
        </CardTitle>
        <CardDescription>
          Skills with positive comparable growth, sorted by growth. Newly emerged skills
          (no demand in the previous comparable period) and skills losing demand are
          listed separately so a decline is never hidden behind the growth chart.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !emerging || !trending ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-64" />
            <Skeleton className="h-56 w-full" />
          </div>
        ) : candidates.length === 0 ? (
          currentDemand.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              title="No skills match the current filters"
              description="Try widening the year range or clearing the skill-scope filters."
            />
          ) : (
            <CurrentDemandFallback skills={currentDemand} />
          )
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                {formatCount(growthCandidates.length)} skill
                {growthCandidates.length === 1 ? "" : "s"} with comparable growth
                {newlyEmerged.length > 0
                  ? ` · ${formatCount(newlyEmerged.length)} newly emerged`
                  : ""}
                {summary.strongestGrowthPct != null
                  ? ` · strongest ${formatSignedGrowth(summary.strongestGrowthPct)}${
                      summary.strongestGrowthName
                        ? ` (${summary.strongestGrowthName})`
                        : ""
                    }`
                  : ""}
              </p>
              <div className="w-full sm:w-56">
                <Select
                  value={historySlug ?? "none"}
                  onValueChange={(value) =>
                    setHistorySlug(value === "none" ? null : value)
                  }
                >
                  <SelectTrigger
                    aria-label="View a skill's demand history"
                    className="h-9"
                  >
                    <SelectValue placeholder="View skill history…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Hide history</SelectItem>
                    {historyOptions.map((candidate) => (
                      <SelectItem key={candidate.slug} value={candidate.slug}>
                        {candidate.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {growthCandidates.length > 0 ? (
              <div className="overflow-x-auto">
                <div
                  className="min-w-[480px]"
                  role="img"
                  aria-label="Growth in demand by skill"
                >
                  <ResponsiveContainer
                    width="100%"
                    height={Math.max(200, growthCandidates.length * 34 + 48)}
                  >
                    <ComposedChart
                      data={growthCandidates}
                      layout="vertical"
                      margin={{ top: 4, right: 72, left: 4, bottom: 8 }}
                    >
                      <CartesianGrid
                        stroke={CHART_GRID_STROKE}
                        strokeDasharray="3 3"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        domain={[0, (dataMax: number) => Math.max(10, Math.ceil(dataMax * 1.1))]}
                        tickFormatter={percentTick}
                        tick={CHART_AXIS_STYLE}
                        tickMargin={4}
                        height={34}
                        label={chartAxisLabel(
                          "Growth vs previous comparable period (%)"
                        )}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={140}
                        tick={CHART_AXIS_STYLE}
                        tickMargin={4}
                        tickFormatter={(value: string) =>
                          value.length > 18 ? `${value.slice(0, 17)}…` : value
                        }
                      />
                      <Tooltip
                        content={<LollipopTooltip />}
                        cursor={{ fill: CHART_CURSOR_FILL }}
                      />
                      <Bar
                        dataKey="growthPct"
                        name="Growth"
                        barSize={14}
                        legendType="none"
                        isAnimationActive={false}
                        shape={(props: unknown) => (
                          <LollipopShape {...(props as LollipopShapeProps)} />
                        )}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No skill has a comparable previous period under these filters, so no
                growth lollipop can be drawn.
              </p>
            )}

            {newlyEmerged.length > 0 && (
              <div className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium">Newly emerged</p>
                  <Badge variant="outline" className="text-muted-foreground">
                    No demand in the previous comparable period
                  </Badge>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {newlyEmerged.map((candidate) => (
                    <button
                      key={candidate.slug}
                      type="button"
                      aria-pressed={historySlug === candidate.slug}
                      className="rounded-md border border-border bg-secondary px-2 py-1 text-xs font-normal text-secondary-foreground transition-colors hover:bg-secondary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-pressed:border-primary"
                      onClick={() =>
                        setHistorySlug(
                          historySlug === candidate.slug ? null : candidate.slug
                        )
                      }
                    >
                      {candidate.name} · {formatCount(candidate.currentCount)} posting
                      {candidate.currentCount === 1 ? "" : "s"}
                      {candidate.currentWindowDemandPct != null
                        ? ` (${formatPercent(candidate.currentWindowDemandPct, 1)})`
                        : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {declining.length > 0 && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium">Losing demand</p>
                  <Badge variant="destructive">Declining</Badge>
                  <span className="text-xs text-muted-foreground">
                    Fewer postings than the comparable previous period
                  </span>
                </div>
                <ul className="mt-2 divide-y divide-border">
                  {declining.map((skill) => (
                    <li
                      key={skill.slug}
                      className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1.5 text-sm"
                    >
                      <span className="min-w-0 truncate">{skill.name}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {formatCount(skill.previous_period_count)} →{" "}
                        {formatCount(skill.current_period_count)} postings ·{" "}
                        <span className="font-medium text-destructive">
                          {formatSignedGrowth(skill.yoy_growth_pct)}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {historyCandidate && (
              <div className="rounded-md border border-border p-3">
                <p className="text-sm font-medium">
                  {historyCandidate.name} · year-wise demand
                </p>
                <TrajectoryChart candidate={historyCandidate} meta={meta} />
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
