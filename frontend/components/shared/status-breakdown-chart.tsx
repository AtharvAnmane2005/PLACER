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

import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
  assignCategoryColors,
  chartAxisLabel,
} from "@/lib/chart-theme";
import { formatCount } from "@/lib/format";
import type {
  ApplicationStatusBreakdown,
  TpoApplicationStatusBreakdown,
} from "@/types/analytics";

interface StatusDatum {
  name: string;
  count: number;
}

function StatusTooltip({
  active,
  payload,
  colorByName,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | string; payload: StatusDatum }>;
  colorByName: Map<string, string>;
}) {
  const entry = payload?.[0];
  if (!active || !entry) return null;
  const name = entry.payload.name;
  return (
    <ChartTooltipCard
      title={name}
      rows={[
        {
          label: "Applications",
          value: formatCount(Number(entry.value ?? 0)),
          color: colorByName.get(name),
        },
      ]}
    />
  );
}

export function StatusBreakdownChart({
  breakdown,
}: {
  breakdown: ApplicationStatusBreakdown | TpoApplicationStatusBreakdown;
}) {
  // Only the three statuses the current workflow manages are plotted.
  // Legacy `selected` rows are mapped into `shortlisted` by the backend at
  // read time, so plotting `selected` again would double-count them.
  const data: StatusDatum[] = [
    { name: "Applied", count: breakdown.applied },
    { name: "Shortlisted", count: breakdown.shortlisted },
    { name: "Rejected", count: breakdown.rejected },
  ];
  const colors = assignCategoryColors(data.map((entry) => entry.name));
  const colorByName = new Map(data.map((entry, index) => [entry.name, colors[index]!]));

  return (
    <div role="img" aria-label="Application counts by status">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 16, right: 20, left: 4, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={CHART_AXIS_STYLE} tickMargin={6} height={32} />
          <YAxis
            allowDecimals={false}
            width={52}
            tick={CHART_AXIS_STYLE}
            tickMargin={4}
            label={chartAxisLabel("Applications", "insideLeft")}
          />
          <Tooltip
            content={<StatusTooltip colorByName={colorByName} />}
            contentStyle={CHART_TOOLTIP_STYLE}
            cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={colorByName.get(entry.name)} />
            ))}
            <LabelList
              dataKey="count"
              position="top"
              formatter={(value: number | string) => formatCount(Number(value))}
              style={{ fill: "#475569", fontSize: 11, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartLegend
        className="mt-2"
        ariaLabel="Application status legend"
        items={data.map((entry) => ({
          label: entry.name,
          color: colorByName.get(entry.name)!,
          value: formatCount(entry.count),
        }))}
      />
    </div>
  );
}
