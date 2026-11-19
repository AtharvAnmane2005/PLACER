"use client";

import { TrendingUp as TrendingUpIcon } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTooltipCard } from "@/components/shared/chart-ui";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendBadge } from "@/components/market/trend-badge";
import { TrendInsights } from "@/components/market/trend-insights";
import {
  CHART_AXIS_STYLE,
  CHART_CURSOR_FILL,
  CHART_GRID_STROKE,
  CHART_PALETTE,
  CHART_TOOLTIP_STYLE,
  assignCategoryColors,
  chartAxisLabel,
} from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";
import { formatSignedGrowth, trendExplanation } from "@/lib/market-insights";
import type {
  CompanyMarketAnalytics,
  HistoricalSkillTrend,
  JobFamilyMarketAnalytics,
  MarketMeta,
  TrendingSkill,
} from "@/types/market-analytics";

/** Percentage-point change, e.g. +8.1 pts (share momentum, not a % change). */
function formatSignedPoints(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} pts`;
}

function ChartTooltip({
  active,
  payload,
  colorByName,
  showMomentum,
}: {
  active?: boolean;
  payload?: Array<{ payload: TrendingSkill }>;
  colorByName: Map<string, string>;
  showMomentum: boolean;
}) {
  const entry = payload?.[0];
  if (!active || !entry) return null;
  const skill = entry.payload;
  return (
    <ChartTooltipCard
      title={skill.name}
      rows={[
        {
          label: "Postings requiring this skill",
          value: formatCount(skill.posting_count),
          color: colorByName.get(skill.name),
        },
        {
          label: "Demand share",
          value: formatPercent(skill.demand_pct, 1),
        },
        ...(showMomentum
          ? [
              {
                label: "Demand-share momentum",
                value: formatSignedPoints(skill.momentum_pct),
              },
              {
                label: "YoY posting growth",
                value:
                  skill.yoy_growth_pct == null
                    ? "—"
                    : formatSignedGrowth(skill.yoy_growth_pct),
              },
            ]
          : []),
      ]}
    />
  );
}

export function TrendingSkillsSection({
  skills,
  historical,
  families,
  companies,
  meta,
  isLoading,
}: {
  skills: TrendingSkill[] | undefined;
  historical: HistoricalSkillTrend[];
  families: JobFamilyMarketAnalytics[];
  companies: CompanyMarketAnalytics[];
  meta: MarketMeta | undefined;
  isLoading: boolean;
}) {
  const periodLabel = meta?.current_period?.label;
  const previousLabel = meta?.previous_period?.label;
  const comparable = meta?.comparison_comparable ?? false;
  // Momentum is available whenever the backend could compare two windows. It
  // is the ranking signal, so the chart plots it when present; otherwise the
  // card falls back to posting volume (single-year datasets).
  const hasMomentum =
    (skills?.length ?? 0) > 0 &&
    (skills ?? []).every((skill) => skill.momentum_pct != null);
  const chartMetric: "momentum_pct" | "posting_count" = hasMomentum
    ? "momentum_pct"
    : "posting_count";
  const chartLabel = hasMomentum
    ? "Change in demand share (percentage points)"
    : "Postings requiring the skill";
  const chartAriaLabel = hasMomentum
    ? "Demand-share momentum by trending skill"
    : "Postings by trending skill";
  const skillColors = skills ? assignCategoryColors(skills.map((skill) => skill.name)) : [];
  const skillColorByName = new Map<string, string>(
    (skills ?? []).map((skill, index) => [skill.name, skillColors[index]!] as const)
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Top trending skills</CardTitle>
        <CardDescription>
          {hasMomentum
            ? `Skills ranked by momentum — the change in demand share between ${previousLabel ?? "the previous period"} and ${periodLabel ?? "the current period"}. Declining skills are listed last.`
            : `Skills ranked by posting count${periodLabel ? ` in ${periodLabel}` : ""}. Each bar uses the skill's stable colour across the analytics views.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading || !skills ? (
          <Skeleton className="h-72 w-full" />
        ) : skills.length === 0 ? (
          <EmptyState
            icon={TrendingUpIcon}
            title="No skills match the current filters"
            description="Try widening the year range or clearing the skill-scope filters."
          />
        ) : (
          <>
            <div className="overflow-hidden" role="img" aria-label={chartAriaLabel}>
              <ResponsiveContainer width="100%" height={Math.max(220, skills.length * 34 + 40)}>
                <BarChart
                  data={skills}
                  layout="vertical"
                  margin={{ top: 4, right: 24, left: 4, bottom: 0 }}
                >
                  <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" horizontal={false} />
                  <XAxis
                    type="number"
                    allowDecimals={hasMomentum}
                    tick={CHART_AXIS_STYLE}
                    label={chartAxisLabel(chartLabel)}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={CHART_AXIS_STYLE}
                    tickFormatter={(value: string) =>
                      value.length > 18 ? `${value.slice(0, 17)}…` : value
                    }
                  />
                  <Tooltip
                    content={
                      <ChartTooltip
                        colorByName={skillColorByName}
                        showMomentum={hasMomentum}
                      />
                    }
                    cursor={{ fill: CHART_CURSOR_FILL }}
                    contentStyle={CHART_TOOLTIP_STYLE}
                  />
                  {hasMomentum && (
                    <ReferenceLine x={0} stroke={CHART_GRID_STROKE} strokeWidth={1.5} />
                  )}
                  <Bar dataKey={chartMetric} radius={[0, 4, 4, 0]} barSize={16}>
                    {skills.map((skill) => {
                      const declining = hasMomentum && (skill.momentum_pct ?? 0) < 0;
                      return (
                        <Cell
                          key={skill.name}
                          fill={
                            declining
                              ? CHART_PALETTE.red
                              : skillColorByName.get(skill.name)
                          }
                        />
                      );
                    })}
                    <LabelList
                      dataKey={chartMetric}
                      position="right"
                      formatter={(value: number | string) =>
                        hasMomentum
                          ? formatSignedPoints(Number(value))
                          : formatCount(Number(value))
                      }
                      style={{ fill: "#475569", fontSize: 11, fontWeight: 600 }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Supporting table — hidden heading keeps it accessible without
                duplicating the card title visually. Trend badges carry a
                native tooltip explaining the classification. */}
            <div className="overflow-x-auto">
              <table className={`w-full ${comparable ? "min-w-[840px]" : "min-w-[560px]"} text-sm`}>
                <caption className="sr-only">Trending skills detail</caption>
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="py-2 pr-3 font-medium">Skill</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Category</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">Postings</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">Demand</th>
                    <th
                      scope="col"
                      className="py-2 pr-3 text-right font-medium"
                      title={periodLabel ? `Postings in ${periodLabel}` : undefined}
                    >
                      Current
                    </th>
                    {hasMomentum && (
                      <th
                        scope="col"
                        className="py-2 pr-3 text-right font-medium"
                        title="Change in demand share versus the previous comparable period, in percentage points."
                      >
                        Momentum
                      </th>
                    )}
                    {comparable && (
                      <>
                        <th
                          scope="col"
                          className="py-2 pr-3 text-right font-medium"
                          title={previousLabel ? `Postings in ${previousLabel}` : undefined}
                        >
                          Previous
                        </th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">
                          YoY growth
                        </th>
                        <th scope="col" className="py-2 pr-3 font-medium">Trend</th>
                      </>
                    )}
                    <th
                      scope="col"
                      className="py-2 font-medium"
                      title="Backend trend score: weighted mean of the skill's year-wise demand shares."
                    >
                      Score
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {skills.map((skill) => (
                    <tr key={skill.slug} className="align-middle">
                      <td className="py-2.5 pr-3 font-medium">{skill.name}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">
                        {skill.category ?? "—"}
                      </td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{skill.posting_count}</td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{skill.demand_pct}%</td>
                      <td
                        className="py-2.5 pr-3 text-right tabular-nums"
                        title={periodLabel ? `Postings in ${periodLabel}` : undefined}
                      >
                        {skill.current_period_count}
                      </td>
                      {hasMomentum && (
                        <td className="py-2.5 pr-3 text-right tabular-nums">
                          {formatSignedPoints(skill.momentum_pct)}
                        </td>
                      )}
                      {comparable && (
                        <>
                          <td
                            className="py-2.5 pr-3 text-right tabular-nums"
                            title={previousLabel ? `Postings in ${previousLabel}` : undefined}
                          >
                            {skill.previous_period_count}
                          </td>
                          <td className="py-2.5 pr-3 text-right tabular-nums">
                            {skill.yoy_growth_pct == null
                              ? "—"
                              : formatSignedGrowth(skill.yoy_growth_pct)}
                          </td>
                          <td className="py-2.5 pr-3">
                            <span
                              title={trendExplanation(skill)}
                              className="inline-flex cursor-help"
                              aria-label={trendExplanation(skill)}
                            >
                              <TrendBadge trend={skill.trend} />
                            </span>
                          </td>
                        </>
                      )}
                      <td className="py-2.5 tabular-nums text-muted-foreground">
                        {skill.trend_score}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!comparable && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Growth, trend and previous-period columns need postings from two comparable
                  years. The current dataset covers{" "}
                  {meta?.current_period?.label ?? "a single period"} only.
                </p>
              )}
            </div>

            <TrendInsights
              skills={skills}
              historical={historical}
              families={families}
              companies={companies}
              meta={meta}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
