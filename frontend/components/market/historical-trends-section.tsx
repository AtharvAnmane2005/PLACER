"use client";

import { useMemo, useState } from "react";
import { TrendingUp, X } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Combobox } from "@/components/ui/combobox";
import { ChartTooltipCard } from "@/components/shared/chart-ui";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STROKE,
  assignCategoryColors,
  chartAxisLabel,
  percentTick,
} from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";
import { formatSignedGrowth } from "@/lib/market-insights";
import type { HistoricalSkillTrend, MarketMeta } from "@/types/market-analytics";

/** How many skills can be compared at once (bounded chart readability). */
const MAX_COMPARED_SKILLS = 4;
/** Skills selected by default so the chart opens with a real comparison. */
const DEFAULT_COMPARED_SKILLS = 3;

type TrendMetric = "postings" | "share";

interface TrendRow {
  year: number;
  /** Chosen metric keyed by skill slug. */
  [key: string]: number | null;
}

function TrendTooltip({
  active,
  payload,
  colorBySlug,
  nameBySlug,
  metric,
  windowLabel,
}: {
  active?: boolean;
  payload?: Array<{
    dataKey?: string | number;
    name?: string | number;
    value?: number | string;
    payload: TrendRow;
  }>;
  colorBySlug: Map<string, string>;
  nameBySlug: Map<string, string>;
  metric: TrendMetric;
  windowLabel: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const year = payload[0]?.payload.year;
  const rows = payload.flatMap((entry) => {
    if (typeof entry.dataKey !== "string") return [];
    const slug = entry.dataKey;
    const row = entry.payload;
    const postings = row[`${slug}__postings`];
    const share = row[`${slug}__share`];
    const growth = row[`${slug}__growth`];
    const primary =
      metric === "postings"
        ? typeof postings === "number"
          ? `${formatCount(postings)} posting${postings === 1 ? "" : "s"}`
          : "—"
        : typeof share === "number"
          ? formatPercent(share, 1)
          : "—";
    const secondary =
      metric === "postings"
        ? typeof share === "number"
          ? `${formatPercent(share, 1)} of that window's postings`
          : undefined
        : typeof postings === "number"
          ? `${formatCount(postings)} posting${postings === 1 ? "" : "s"}`
          : undefined;
    return [
      {
        label: nameBySlug.get(slug) ?? slug,
        value: primary,
        color: colorBySlug.get(slug),
        detail: (
          <>
            {secondary ? <>{secondary} · </> : null}
            {typeof growth === "number"
              ? `${formatSignedGrowth(growth)} vs previous comparable period`
              : "no comparable prior period"}
          </>
        ),
      },
    ];
  });
  return (
    <ChartTooltipCard
      title={year}
      subtitle={windowLabel}
      rows={rows}
    />
  );
}

/**
 * Compare up to 4 skills' demand over time as a multi-series line chart.
 *
 * The chart plots the SAME comparable-window counts the backend uses for
 * `yoy_growth_pct` (`window_posting_count`), so a line can never move in the
 * opposite direction to its own YoY figure. The demand-share view is available
 * as a secondary metric, and both figures are always shown in the tooltip.
 * Every point is a backend-supplied `historical_trends` value; when the
 * filtered range contains a single year, one real point is drawn per skill and
 * the card states that a trend needs a wider range — no line is invented.
 */
export function HistoricalTrendsSection({
  trends,
  meta,
  isLoading,
}: {
  trends: HistoricalSkillTrend[] | undefined;
  meta: MarketMeta | undefined;
  isLoading: boolean;
}) {
  const [selectedSlugs, setSelectedSlugs] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [metric, setMetric] = useState<TrendMetric>("postings");

  const trendOptions = useMemo(
    () => (trends ?? []).filter((trend) => trend.years.length > 0),
    [trends]
  );

  const defaultSelected = trendOptions.slice(0, DEFAULT_COMPARED_SKILLS);
  const resolvedSelection =
    selectedSlugs.length > 0
      ? selectedSlugs
          .map((slug) => trendOptions.find((trend) => trend.slug === slug))
          .filter((trend): trend is HistoricalSkillTrend => trend != null)
      : defaultSelected;
  const selected =
    resolvedSelection.length > 0 ? resolvedSelection : defaultSelected;

  const selectedColors = assignCategoryColors(selected.map((trend) => trend.name));
  const colorBySlug = new Map<string, string>(
    selected.map((trend, index) => [trend.slug, selectedColors[index]!] as const)
  );
  const nameBySlug = new Map<string, string>(
    selected.map((trend) => [trend.slug, trend.name] as const)
  );

  const years = Array.from(
    new Set(selected.flatMap((trend) => trend.years.map((point) => point.year)))
  ).sort((a, b) => a - b);
  const singleYear = years.length === 1 ? years[0]! : null;

  // Always use the comparable-window figures: they are the exact basis of
  // `yoy_growth_pct`, so the line direction and the growth sign always agree.
  // When the latest year is not partial the window equals the calendar year.
  const windowLabel = meta?.is_partial_year
    ? `${meta.comparison_period} comparable window`
    : "Full calendar year";

  const chartData: TrendRow[] = years.map((year) => {
    const row: TrendRow = { year };
    for (const trend of selected) {
      const point = trend.years.find((entry) => entry.year === year);
      if (point) {
        row[trend.slug] =
          metric === "postings" ? point.window_posting_count : point.window_demand_pct;
        row[`${trend.slug}__postings`] = point.window_posting_count;
        row[`${trend.slug}__share`] = point.window_demand_pct;
        row[`${trend.slug}__growth`] = point.yoy_growth_pct;
      }
    }
    return row;
  });

  const maxValue = chartData.reduce((max, row) => {
    for (const trend of selected) {
      const value = row[trend.slug];
      if (typeof value === "number" && value > max) max = value;
    }
    return max;
  }, 0);
  const yMax = Math.max(1, Math.ceil(maxValue * 1.15));

  const selectedSlugList = selected.map((trend) => trend.slug);
  const addable = trendOptions.filter((trend) => !selectedSlugList.includes(trend.slug));
  const canAddMore = selected.length < MAX_COMPARED_SKILLS;

  const addSkill = (slug: string) => {
    setSelectedSlugs((previous) => {
      const base = previous.length > 0 ? previous : selectedSlugList;
      if (base.includes(slug)) return base;
      return [...base, slug].slice(0, MAX_COMPARED_SKILLS);
    });
  };

  const commitQuery = () => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return;
    const match = addable.find(
      (trend) => trend.name.toLocaleLowerCase() === normalized
    );
    if (match) {
      addSkill(match.slug);
      setQuery("");
    }
  };

  if (isLoading || !trends) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Skill demand over time</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-72 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (trendOptions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Skill demand over time</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={TrendingUp}
            title="No historical data for the current filters"
            description="Try widening the year range or clearing the skill-scope filters."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between sm:space-y-0">
        <div className="min-w-0">
          <CardTitle className="text-base">Skill demand over time</CardTitle>
          <CardDescription>
            {singleYear
              ? `Only ${singleYear} data is available under these filters, so each skill shows one real point. Widen the year range to see a trend.`
              : "Year-wise demand for the selected skills, plotted on the same comparable period as the YoY figure. Hover a point for both postings and demand share."}
          </CardDescription>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          <div className="w-full sm:w-56">
            <Combobox
              listId="historical-trend-skills"
              options={addable.map((trend) => trend.name)}
              value={query}
              onChange={(event) => {
                const value = event.target.value;
                setQuery(value);
                const match = addable.find(
                  (trend) =>
                    trend.name.toLocaleLowerCase() === value.trim().toLocaleLowerCase()
                );
                if (match) {
                  addSkill(match.slug);
                  setQuery("");
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitQuery();
                }
              }}
              placeholder={
                !canAddMore
                  ? "Maximum skills selected"
                  : addable.length === 0
                    ? "All skills selected"
                    : "Search skills to compare…"
              }
              aria-label="Search skills to add to the comparison"
              disabled={!canAddMore || addable.length === 0}
              className="h-9"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-9"
            onClick={commitQuery}
            disabled={!canAddMore || query.trim().length === 0}
          >
            Add
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Selected-skill chips: remove back down to the default selection. */}
        <div className="flex flex-wrap items-center gap-2">
          {selected.map((trend) => (
            <Badge key={trend.slug} variant="secondary" className="gap-1 font-normal">
              <span
                aria-hidden
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: colorBySlug.get(trend.slug) }}
              />
              {trend.name}
              {selected.length > 1 && (
                <button
                  type="button"
                  aria-label={`Remove ${trend.name} from the comparison`}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() =>
                    setSelectedSlugs((previous) => {
                      const base = previous.length > 0 ? previous : selectedSlugList;
                      return base.filter((slug) => slug !== trend.slug);
                    })
                  }
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
          {selectedSlugs.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedSlugs([]);
                setQuery("");
              }}
              className="h-7 px-2 text-xs"
            >
              Reset selection
            </Button>
          )}
        </div>

        {/* Metric switch. Postings is the default because it is the basis of
            the YoY growth, so the line and the growth number agree. */}
        <div
          className="inline-flex rounded-md border border-border p-0.5"
          role="group"
          aria-label="Chart metric"
        >
          <button
            type="button"
            aria-pressed={metric === "postings"}
            onClick={() => setMetric("postings")}
            className="rounded px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors aria-pressed:bg-secondary aria-pressed:text-foreground"
          >
            Postings
          </button>
          <button
            type="button"
            aria-pressed={metric === "share"}
            onClick={() => setMetric("share")}
            className="rounded px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors aria-pressed:bg-secondary aria-pressed:text-foreground"
          >
            Demand share
          </button>
        </div>

        <div
          className="overflow-hidden"
          role="img"
          aria-label={
            metric === "postings"
              ? "Postings requiring each skill by year"
              : "Demand share by year and skill"
          }
        >
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 8 }}>
              <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="year"
                tick={CHART_AXIS_STYLE}
                tickMargin={6}
                height={34}
                allowDecimals={false}
                tickFormatter={(value) => String(value)}
                label={chartAxisLabel("Year")}
              />
              <YAxis
                domain={[0, yMax]}
                tickFormatter={metric === "postings" ? undefined : percentTick}
                allowDecimals={metric === "share"}
                tick={CHART_AXIS_STYLE}
                tickMargin={4}
                width={metric === "postings" ? 64 : 56}
                label={chartAxisLabel(
                  metric === "postings" ? "Postings requiring the skill" : "Demand share (%)",
                  "insideLeft"
                )}
              />
              <Tooltip
                content={
                  <TrendTooltip
                    colorBySlug={colorBySlug}
                    nameBySlug={nameBySlug}
                    metric={metric}
                    windowLabel={windowLabel}
                  />
                }
              />
              {selected.map((trend) => (
                <Line
                  key={trend.slug}
                  type="monotone"
                  dataKey={trend.slug}
                  name={trend.name}
                  stroke={colorBySlug.get(trend.slug)}
                  strokeWidth={2}
                  dot={{ r: 3.5, strokeWidth: 2 }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {singleYear != null && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
            <Badge variant="outline" className="text-muted-foreground">
              Single year
            </Badge>
            <span>
              Only {singleYear} data is available under these filters. A trend needs
              postings from at least two comparable periods.
            </span>
          </div>
        )}

        {meta?.is_partial_year &&
          meta?.current_period != null &&
          selected.some((trend) =>
            trend.years.some((year) => year.year === meta.current_period!.year)
          ) && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="warning">{meta.comparison_period} only</Badge>
              <span>
                Every point uses the same {meta.comparison_period} window so the
                line and the YoY growth are directly comparable.
              </span>
            </div>
          )}
      </CardContent>
    </Card>
  );
}
