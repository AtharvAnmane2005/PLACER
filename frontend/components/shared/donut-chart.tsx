"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { ChartEmptyState } from "@/components/shared/chart-card";
import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import { CHART_TOOLTIP_STYLE, categoryColor } from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface DonutDatum {
  name: string;
  value: number;
  /** Canonical colour for the category. Defaults to `categoryColor(name)`. */
  color?: string;
}

interface DonutSlice extends DonutDatum {
  color: string;
}

function DonutTooltip({
  active,
  payload,
  total,
}: {
  active?: boolean;
  payload?: Array<{ payload?: DonutSlice }>;
  total: number;
}) {
  const slice = payload?.[0]?.payload;
  if (!active || !slice) return null;
  const share = total > 0 ? (slice.value / total) * 100 : 0;
  return (
    <ChartTooltipCard
      title={slice.name}
      rows={[
        { label: "Count", value: formatCount(slice.value), color: slice.color },
        { label: "Share", value: formatPercent(share, 1) },
      ]}
    />
  );
}

export interface DonutChartProps {
  data: DonutDatum[];
  ariaLabel: string;
  /** Large number in the middle of the ring, usually the total. */
  centerValue?: number;
  centerLabel?: string;
  height?: number;
  emptyTitle?: string;
  emptyDescription?: string;
  /** Practical drill-down: called with the slice's category name. */
  onSliceClick?: (name: string) => void;
  className?: string;
}

/**
 * Shared categorical donut. Colours come from the central palette, so the
 * same category is the same colour here, in the legend and in the tooltip.
 */
export function DonutChart({
  data,
  ariaLabel,
  centerValue,
  centerLabel,
  height = 240,
  emptyTitle = "No data yet",
  emptyDescription = "There are no records to summarise for this chart.",
  onSliceClick,
  className,
}: DonutChartProps) {
  const slices: DonutSlice[] = data.map((datum) => ({
    ...datum,
    color: datum.color ?? categoryColor(datum.name),
  }));
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);

  if (slices.length === 0 || total === 0) {
    return <ChartEmptyState title={emptyTitle} description={emptyDescription} height={height} />;
  }

  return (
    <div className={cn("w-full", className)} role="img" aria-label={ariaLabel}>
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius="58%"
              outerRadius="84%"
              paddingAngle={2}
              strokeWidth={1}
              stroke="#FFFFFF"
            >
              {slices.map((slice) => (
                <Cell
                  key={slice.name}
                  fill={slice.color}
                  cursor={onSliceClick ? "pointer" : undefined}
                  onClick={onSliceClick ? () => onSliceClick(slice.name) : undefined}
                />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip total={total} />} contentStyle={CHART_TOOLTIP_STYLE} />
          </PieChart>
        </ResponsiveContainer>
        {(centerValue != null || centerLabel) && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {centerValue != null && (
              <span className="font-display text-2xl font-semibold tabular-nums">
                {formatCount(centerValue)}
              </span>
            )}
            {centerLabel && (
              <span className="mt-0.5 text-xs text-muted-foreground">{centerLabel}</span>
            )}
          </div>
        )}
      </div>
      <ChartLegend
        className="mt-3"
        ariaLabel={`${ariaLabel} legend`}
        items={slices.map((slice) => ({
          label: slice.name,
          color: slice.color,
          value: formatCount(slice.value),
          detail:
            total > 0 ? (
              <span className="tabular-nums">{formatPercent((slice.value / total) * 100, 1)}</span>
            ) : undefined,
        }))}
      />
    </div>
  );
}
