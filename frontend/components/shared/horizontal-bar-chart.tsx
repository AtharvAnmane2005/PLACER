"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartEmptyState } from "@/components/shared/chart-card";
import { ChartTooltipCard } from "@/components/shared/chart-ui";
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
  categoryColor,
  chartAxisLabel,
} from "@/lib/chart-theme";
import { formatCount } from "@/lib/format";

export interface HorizontalBarDatum {
  name: string;
  value: number;
  /** Defaults to the canonical colour for `name`. */
  color?: string;
  /** Extra line in the tooltip, e.g. a status split. */
  detail?: string;
}

interface HorizontalBarRow extends HorizontalBarDatum {
  color: string;
}

/** Approximate character budget for the fixed-width category axis. */
function truncateLabel(value: string, width: number): string {
  const budget = Math.max(8, Math.floor((width - 12) / 7));
  return value.length > budget ? `${value.slice(0, budget - 1)}…` : value;
}

function HorizontalBarTooltip({
  active,
  payload,
  valueLabel,
  shareTotal,
}: {
  active?: boolean;
  payload?: Array<{ payload?: HorizontalBarRow }>;
  valueLabel: string;
  shareTotal?: number;
}) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const share = shareTotal && shareTotal > 0 ? (row.value / shareTotal) * 100 : null;
  return (
    <ChartTooltipCard
      title={row.name}
      rows={[
        { label: valueLabel, value: formatCount(row.value), color: row.color },
        ...(share != null ? [{ label: "Share", value: `${share.toFixed(1)}%` }] : []),
        ...(row.detail ? [{ label: "Split", value: row.detail }] : []),
      ]}
    />
  );
}

export interface HorizontalBarChartProps {
  data: HorizontalBarDatum[];
  ariaLabel: string;
  valueLabel?: string;
  /** Width reserved for the category labels on the left. */
  categoryWidth?: number;
  /** Fixed value-axis maximum; omit to auto-scale. */
  valueMax?: number;
  emptyTitle?: string;
  emptyDescription?: string;
  onBarClick?: (name: string) => void;
  height?: number;
  /** When provided, the tooltip also shows each bar's share of this total. */
  shareTotal?: number;
}

/**
 * Shared horizontal bar chart for ranked categories (companies, departments).
 * Bars and tooltip rows share one colour per category, and the value is also
 * printed at the end of each bar so colour is never the only cue.
 */
export function HorizontalBarChart({
  data,
  ariaLabel,
  valueLabel = "Count",
  categoryWidth = 132,
  valueMax,
  emptyTitle = "No data for this view",
  emptyDescription = "Try widening the date range or clearing a filter.",
  onBarClick,
  height,
  shareTotal,
}: HorizontalBarChartProps) {
  const rows: HorizontalBarRow[] = data.map((datum) => ({
    ...datum,
    color: datum.color ?? categoryColor(datum.name),
  }));
  const chartHeight = height ?? Math.max(220, rows.length * 40 + 64);

  if (rows.length === 0) {
    return <ChartEmptyState title={emptyTitle} description={emptyDescription} height={chartHeight} />;
  }

  return (
    <div className="w-full" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 8, right: 48, left: 0, bottom: 24 }}
        >
          <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            allowDecimals={false}
            domain={valueMax ? [0, valueMax] : undefined}
            tick={CHART_AXIS_STYLE}
            tickMargin={6}
            height={30}
            label={chartAxisLabel(valueLabel)}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={categoryWidth}
            tick={CHART_AXIS_STYLE}
            tickLine={false}
            tickMargin={4}
            interval={0}
            tickFormatter={(value: string) => truncateLabel(value, categoryWidth)}
          />
          <Tooltip
            content={<HorizontalBarTooltip valueLabel={valueLabel} shareTotal={shareTotal} />}
            contentStyle={CHART_TOOLTIP_STYLE}
            cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={24}>
            {rows.map((row) => (
              <Cell
                key={row.name}
                fill={row.color}
                cursor={onBarClick ? "pointer" : undefined}
                onClick={onBarClick ? () => onBarClick(row.name) : undefined}
              />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(value: number | string) => formatCount(Number(value))}
              style={{ fill: "#475569", fontSize: 11, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
