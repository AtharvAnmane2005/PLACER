"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartEmptyState } from "@/components/shared/chart-card";
import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
  categoryColor,
  chartAxisLabel,
} from "@/lib/chart-theme";
import { formatCount } from "@/lib/format";

export interface GroupedBarSeries {
  /** Property on each datum. */
  key: string;
  label: string;
  /** Defaults to the canonical colour for `label`. */
  color?: string;
}

export type GroupedBarRow = Record<string, string | number>;

/** Long category labels are shortened on crowded axes only. */
function shortLabel(value: string | number, maxLength = 16): string {
  const text = String(value ?? "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function GroupedBarTooltip({
  active,
  label,
  payload,
  series,
  valueFormatter,
}: {
  active?: boolean;
  label?: string | number;
  payload?: Array<{ value?: number | string; dataKey?: string | number }>;
  series: Array<GroupedBarSeries & { color: string }>;
  valueFormatter: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltipCard
      title={String(label ?? "")}
      rows={series.map((entry) => {
        const match = payload.find((row) => String(row.dataKey) === entry.key);
        return {
          label: entry.label,
          value: valueFormatter(Number(match?.value ?? 0)),
          color: entry.color,
        };
      })}
    />
  );
}

export interface GroupedBarChartProps {
  data: GroupedBarRow[];
  /** Property used for the category axis (e.g. department name). */
  categoryKey: string;
  series: GroupedBarSeries[];
  ariaLabel: string;
  height?: number;
  categoryAxisLabel?: string;
  valueAxisLabel?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  /** Angle for long category labels; 0 keeps them horizontal. */
  xTickAngle?: number;
  /** Optional display formatter for category ticks (e.g. "2026-11" -> "Nov 2026"). */
  categoryFormatter?: (value: string) => string;
  /**
   * Print the exact value above each bar. Best for small datasets where the
   * reader should not have to hover; automatically suppressed when crowded.
   */
  showValueLabels?: boolean;
  /** Practical drill-down: called with the category behind the clicked bar. */
  onBarClick?: (category: string) => void;
}

/**
 * Shared grouped/stacked-ready bar chart for one categorical dimension split
 * by status. Series colours are canonical, so Applied/Shortlisted/Rejected
 * mean the same colour here as in every other status chart.
 *
 * The chart adapts to the dataset: a handful of categories keeps every label
 * and can print exact values, while a crowded axis shortens labels and lets
 * Recharts drop overlapping ticks instead of rendering unreadable text.
 */
export function GroupedBarChart({
  data,
  categoryKey,
  series,
  ariaLabel,
  height,
  categoryAxisLabel,
  valueAxisLabel,
  emptyTitle = "No data for this view",
  emptyDescription = "Try widening the date range or clearing a filter.",
  xTickAngle = 0,
  categoryFormatter,
  showValueLabels = false,
  onBarClick,
}: GroupedBarChartProps) {
  const resolvedSeries = series.map((entry) => ({
    ...entry,
    color: entry.color ?? categoryColor(entry.label),
  }));

  const crowded = data.length > (xTickAngle === 0 ? 8 : 5);
  const chartHeight = height ?? (crowded ? 360 : 300);
  const labelsFit = showValueLabels && !crowded && data.length <= 6;
  const angled = xTickAngle !== 0;

  if (data.length === 0) {
    return <ChartEmptyState title={emptyTitle} description={emptyDescription} height={chartHeight} />;
  }

  const handleBarClick = onBarClick
    ? (entry: unknown) => {
        const row = (entry as { payload?: GroupedBarRow })?.payload ?? (entry as GroupedBarRow);
        const category = row?.[categoryKey];
        if (category != null) onBarClick(String(category));
      }
    : undefined;

  return (
    <div className="w-full" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={data}
          margin={{
            top: labelsFit ? 20 : 16,
            right: 20,
            left: 4,
            bottom: angled ? 12 : categoryAxisLabel ? 8 : 4,
          }}
        >
          <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={categoryKey}
            tick={{ ...CHART_AXIS_STYLE, fontSize: 11 }}
            tickMargin={6}
            minTickGap={crowded ? 10 : 0}
            interval={crowded ? "preserveStartEnd" : 0}
            angle={xTickAngle}
            textAnchor={xTickAngle === 0 ? "middle" : "end"}
            height={angled ? 68 : categoryAxisLabel ? 52 : 34}
            tickFormatter={(value: string | number) => {
              const text = categoryFormatter ? categoryFormatter(String(value)) : String(value);
              return crowded ? shortLabel(text, angled ? 20 : 16) : text;
            }}
            label={categoryAxisLabel ? chartAxisLabel(categoryAxisLabel) : undefined}
          />
          <YAxis
            allowDecimals={false}
            width={48}
            tick={CHART_AXIS_STYLE}
            tickMargin={4}
            label={valueAxisLabel ? chartAxisLabel(valueAxisLabel, "insideLeft") : undefined}
          />
          <Tooltip
            content={
              <GroupedBarTooltip series={resolvedSeries} valueFormatter={(value) => formatCount(value)} />
            }
            contentStyle={CHART_TOOLTIP_STYLE}
            cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
          />
          {resolvedSeries.map((entry) => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              fill={entry.color}
              radius={[3, 3, 0, 0]}
              maxBarSize={26}
              onClick={handleBarClick}
              style={onBarClick ? { cursor: "pointer" } : undefined}
            >
              {labelsFit && (
                <LabelList
                  dataKey={entry.key}
                  position="top"
                  formatter={(value: number | string) => formatCount(Number(value))}
                  style={{ fill: "#475569", fontSize: 10, fontWeight: 600 }}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
      <ChartLegend
        className="mt-2"
        ariaLabel={`${ariaLabel} legend`}
        items={resolvedSeries.map((entry) => ({ label: entry.label, color: entry.color }))}
      />
    </div>
  );
}
