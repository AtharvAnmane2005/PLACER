"use client";

import { Layers as LayersIcon } from "lucide-react";
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

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTooltipCard } from "@/components/shared/chart-ui";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CHART_AXIS_STYLE,
  CHART_CURSOR_FILL,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
  assignCategoryColors,
  chartAxisLabel,
} from "@/lib/chart-theme";
import { formatCount, formatPercent } from "@/lib/format";
import type { JobFamilyMarketAnalytics } from "@/types/market-analytics";

function ChartTooltip({
  active,
  payload,
  colorByName,
}: {
  active?: boolean;
  payload?: Array<{ payload: JobFamilyMarketAnalytics }>;
  colorByName: Map<string, string>;
}) {
  const entry = payload?.[0];
  if (!active || !entry) return null;
  const family = entry.payload;
  return (
    <ChartTooltipCard
      title={family.job_family}
      rows={[
        {
          label: "Postings",
          value: formatCount(family.posting_count),
          color: colorByName.get(family.job_family),
        },
        {
          label: "Share of filtered postings",
          value: formatPercent(family.posting_share_pct, 1),
        },
      ]}
    />
  );
}

export function JobFamilySection({
  families,
  isLoading,
}: {
  families: JobFamilyMarketAnalytics[] | undefined;
  isLoading: boolean;
}) {
  if (isLoading || !families) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Domain breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-72 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (families.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Domain breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={LayersIcon}
            title="No domains match the current filters"
            description="Try widening the year range or clearing the company filter."
          />
        </CardContent>
      </Card>
    );
  }

  const familyColors = assignCategoryColors(families.map((family) => family.job_family));
  const familyColorByName = new Map<string, string>(
    families.map((family, index) => [family.job_family, familyColors[index]!] as const)
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Domain breakdown</CardTitle>
        <CardDescription>
          Domains ranked by postings in the filtered market. Colours are stable per domain and
          reused in the chart.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div role="img" aria-label="Postings by domain">
          <ResponsiveContainer width="100%" height={Math.max(220, families.length * 32 + 40)}>
            <BarChart data={families} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 0 }}>
              <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                allowDecimals={false}
                tick={CHART_AXIS_STYLE}
                label={chartAxisLabel("Postings")}
              />
              <YAxis
                type="category"
                dataKey="job_family"
                width={170}
                tick={CHART_AXIS_STYLE}
                tickFormatter={(value: string) =>
                  value.length > 22 ? `${value.slice(0, 21)}…` : value
                }
              />
              <Tooltip
                content={<ChartTooltip colorByName={familyColorByName} />}
                contentStyle={CHART_TOOLTIP_STYLE}
                cursor={{ fill: CHART_CURSOR_FILL }}
              />
              <Bar dataKey="posting_count" radius={[0, 4, 4, 0]} barSize={14}>
                {families.map((family) => (
                  <Cell
                    key={family.job_family}
                    fill={familyColorByName.get(family.job_family)}
                  />
                ))}
                <LabelList
                  dataKey="posting_count"
                  position="right"
                  formatter={(value: number | string) => formatCount(Number(value))}
                  style={{ fill: "#475569", fontSize: 11, fontWeight: 600 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {families.map((family) => (
            <div key={family.job_family} className="min-w-0 rounded-md border border-border p-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <p className="flex min-w-0 items-center gap-1.5 font-medium">
                  {family.job_family}
                </p>
                <Badge variant="outline">
                  {formatCount(family.posting_count)} postings ·{" "}
                  {formatPercent(family.posting_share_pct, 1)}
                </Badge>
              </div>
              {family.top_skills.length === 0 ? (
                <p className="text-xs text-muted-foreground">No skill demand recorded.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {family.top_skills.map((skill) => (
                    <span
                      key={skill.slug}
                      className="rounded-md border border-border bg-secondary px-2 py-1 text-xs font-normal text-secondary-foreground"
                    >
                      {skill.name} · {skill.posting_count} ({skill.demand_pct}%)
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Year-wise postings:{" "}
                {Object.entries(family.yearly_counts)
                  .map(([year, count]) => `${year}: ${count}`)
                  .join(" · ")}
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
