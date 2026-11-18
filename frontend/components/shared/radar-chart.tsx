"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RechartsRadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { ChartEmptyState } from "@/components/shared/chart-card";
import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import {
  CHART_AXIS_STYLE,
  CHART_PALETTE,
  CHART_TOOLTIP_STYLE,
  categoryColor,
  percentTick,
} from "@/lib/chart-theme";
import { formatPercent } from "@/lib/format";

export interface RadarDatum {
  subject: string;
  value: number;
}

function DomainTick({
  x = 0,
  y = 0,
  payload,
  textAnchor,
}: {
  x?: number;
  y?: number;
  payload?: { value?: string };
  textAnchor?: "start" | "middle" | "end" | "inherit";
}) {
  const value = payload?.value ?? "";
  return (
    <text
      x={x}
      y={y}
      textAnchor={textAnchor}
      fill={categoryColor(value)}
      fontSize={11}
      fontWeight={600}
    >
      {value}
    </text>
  );
}

function RadarTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: RadarDatum }>;
}) {
  const datum = payload?.[0]?.payload;
  if (!active || !datum) return null;
  return (
    <ChartTooltipCard
      title={datum.subject}
      rows={[
        {
          label: "Score",
          value: formatPercent(datum.value, 1),
          color: categoryColor(datum.subject),
        },
      ]}
    />
  );
}

export interface DomainRadarChartProps {
  data: RadarDatum[];
  ariaLabel: string;
  /** False when the underlying attempts exist but none were graded. */
  hasData: boolean;
  height?: number;
  emptyTitle?: string;
  emptyDescription?: string;
}

/**
 * Five-domain radar. Axis labels and the legend use each domain's canonical
 * colour; the polygon itself is one series, so it keeps one neutral stroke.
 */
export function DomainRadarChart({
  data,
  ariaLabel,
  hasData,
  height = 300,
  emptyTitle = "No graded assessment yet",
  emptyDescription = "Domain scores appear after a submitted assessment has at least one graded answer.",
}: DomainRadarChartProps) {
  if (!hasData || data.length === 0) {
    return <ChartEmptyState title={emptyTitle} description={emptyDescription} height={height} />;
  }

  return (
    <div className="w-full" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsRadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="#E2E8F0" />
          <PolarAngleAxis dataKey="subject" tick={<DomainTick />} tickLine={false} />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={CHART_AXIS_STYLE}
            tickFormatter={percentTick}
            axisLine={false}
          />
          <Tooltip content={<RadarTooltip />} contentStyle={CHART_TOOLTIP_STYLE} />
          <Radar
            name="Score"
            dataKey="value"
            stroke={CHART_PALETTE.indigo}
            fill={CHART_PALETTE.indigo}
            fillOpacity={0.2}
            strokeWidth={2}
            dot={{ r: 3, fill: CHART_PALETTE.indigo, strokeWidth: 0 }}
          />
        </RechartsRadarChart>
      </ResponsiveContainer>
      <ChartLegend
        className="mt-2"
        ariaLabel={`${ariaLabel} legend`}
        items={data.map((datum) => ({
          label: datum.subject,
          color: categoryColor(datum.subject),
          value: formatPercent(datum.value, 1),
        }))}
      />
    </div>
  );
}
