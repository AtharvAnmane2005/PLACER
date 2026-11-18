"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
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

export interface TrendSeries {
  key: string;
  label: string;
  /** Defaults to the canonical colour for `label`. */
  color?: string;
}

export type TrendRow = Record<string, string | number>;

function TrendTooltip({
  active,
  label,
  payload,
  series,
  xValueFormatter,
  valueFormatter,
}: {
  active?: boolean;
  label?: string | number;
  payload?: Array<{ value?: number | string; dataKey?: string | number }>;
  series: Array<TrendSeries & { color: string }>;
  xValueFormatter?: (value: string) => string;
  valueFormatter: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const title = xValueFormatter ? xValueFormatter(String(label ?? "")) : String(label ?? "");
  return (
    <ChartTooltipCard
      title={title}
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

export interface TrendLineChartProps {
  data: TrendRow[];
  /** Property used for the time axis. */
  xKey: string;
  series: TrendSeries[];
  ariaLabel: string;
  height?: number;
  /** Fixed y-axis bounds, e.g. [0, 100] for percentages. */
  yDomain?: [number, number];
  valueFormatter?: (value: number) => string;
  xValueFormatter?: (value: string) => string;
  xAxisLabel?: string;
  yAxisLabel?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  /**
   * Print each point's exact value. Useful for a short single-series trend;
   * automatically ignored for multi-series charts where labels would collide.
   */
  showValueLabels?: boolean;
}

/**
 * Shared time-series line chart. Used for the student score trend and the
 * admin monthly activity lines; each series keeps one canonical colour.
 */
export function TrendLineChart({
  data,
  xKey,
  series,
  ariaLabel,
  height = 280,
  yDomain,
  valueFormatter = formatCount,
  xValueFormatter,
  xAxisLabel,
  yAxisLabel,
  emptyTitle = "No trend data yet",
  emptyDescription = "Activity will appear here as records are created.",
  showValueLabels = false,
}: TrendLineChartProps) {
  const resolvedSeries = series.map((entry) => ({
    ...entry,
    color: entry.color ?? categoryColor(entry.label),
  }));

  if (data.length === 0) {
    return <ChartEmptyState title={emptyTitle} description={emptyDescription} height={height} />;
  }

  return (
    <div className="w-full" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 12, right: 18, left: -8, bottom: 24 }}>
          <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={CHART_AXIS_STYLE}
            tickFormatter={xValueFormatter}
            label={xAxisLabel ? chartAxisLabel(xAxisLabel) : undefined}
            minTickGap={12}
          />
          <YAxis
            allowDecimals={false}
            domain={yDomain}
            tick={CHART_AXIS_STYLE}
            tickFormatter={(value: number) => valueFormatter(value)}
            label={yAxisLabel ? chartAxisLabel(yAxisLabel, "insideLeft") : undefined}
            width={yAxisLabel ? 56 : 40}
          />
          <Tooltip
            content={
              <TrendTooltip
                series={resolvedSeries}
                xValueFormatter={xValueFormatter}
                valueFormatter={valueFormatter}
              />
            }
            contentStyle={CHART_TOOLTIP_STYLE}
            cursor={{ stroke: CHART_GRID_STROKE, strokeWidth: 1 }}
          />
          {resolvedSeries.map((entry) => (
            <Line
              key={entry.key}
              type="monotone"
              dataKey={entry.key}
              name={entry.label}
              stroke={entry.color}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0, fill: entry.color }}
              activeDot={{ r: 5, strokeWidth: 0, fill: entry.color }}
              label={
                showValueLabels && resolvedSeries.length === 1
                  ? {
                      position: "top",
                      formatter: (value: number) => valueFormatter(value),
                      fontSize: 10,
                      fontWeight: 600,
                      fill: "#475569",
                    }
                  : undefined
              }
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <ChartLegend
        className="mt-2"
        ariaLabel={`${ariaLabel} legend`}
        items={resolvedSeries.map((entry) => ({ label: entry.label, color: entry.color }))}
      />
    </div>
  );
}
