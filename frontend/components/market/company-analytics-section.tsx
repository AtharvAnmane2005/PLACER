"use client";

import { useMemo, useState } from "react";
import { Building2 as BuildingIcon } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import type { CompanyMarketAnalytics } from "@/types/market-analytics";

/** Companies drawn in the chart. More than this makes every bar unreadable. */
const CHART_LIMIT = 12;
/** Company detail cards shown before "Show all". */
const DETAIL_PREVIEW = 12;

function ChartTooltip({
  active,
  payload,
  colorByName,
}: {
  active?: boolean;
  payload?: Array<{ payload: CompanyMarketAnalytics }>;
  colorByName: Map<string, string>;
}) {
  const entry = payload?.[0];
  if (!active || !entry) return null;
  const company = entry.payload;
  return (
    <ChartTooltipCard
      title={company.company_name}
      rows={[
        {
          label: "Postings",
          value: formatCount(company.posting_count),
          color: colorByName.get(company.company_name),
        },
        {
          label: "Share of filtered postings",
          value: formatPercent(company.posting_share_pct, 1),
        },
      ]}
    />
  );
}

function SkillChips({ company }: { company: CompanyMarketAnalytics }) {
  if (company.top_skills.length === 0) {
    return <p className="text-xs text-muted-foreground">No skill demand recorded.</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {company.top_skills.map((skill) => (
        <span
          key={skill.slug}
          className="rounded-md border border-border bg-secondary px-2 py-1 text-xs font-normal text-secondary-foreground"
        >
          {skill.name} · {skill.posting_count} ({skill.demand_pct}%)
        </span>
      ))}
    </div>
  );
}

export function CompanyAnalyticsSection({
  companies,
  companyTotal,
  isLoading,
}: {
  companies: CompanyMarketAnalytics[] | undefined;
  /** True number of companies tracked; the API caps the detailed rows. */
  companyTotal?: number;
  isLoading: boolean;
}) {
  const [showAll, setShowAll] = useState(false);

  const ranked = useMemo(
    () =>
      [...(companies ?? [])].sort(
        (a, b) =>
          b.posting_count - a.posting_count ||
          a.company_name.localeCompare(b.company_name)
      ),
    [companies]
  );

  if (isLoading || !companies) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Company requirements</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-72 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (companies.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Company requirements</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={BuildingIcon}
            title="No companies match the current filters"
            description="Try widening the year range or clearing the domain filter."
          />
        </CardContent>
      </Card>
    );
  }

  const companyColors = assignCategoryColors(ranked.map((company) => company.company_name));
  const companyColorByName = new Map<string, string>(
    ranked.map((company, index) => [company.company_name, companyColors[index]!] as const)
  );

  const chartCompanies = ranked.slice(0, CHART_LIMIT);
  const detailCompanies = showAll ? ranked : ranked.slice(0, DETAIL_PREVIEW);
  // The API returns at most 200 detailed company rows; `companyTotal` is the
  // true number of companies in the filtered population. Never report the
  // capped row count as if it were the whole market.
  const trueTotal =
    companyTotal != null && companyTotal > ranked.length ? companyTotal : ranked.length;
  const detailsCapped = trueTotal > ranked.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Company requirements</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="overflow-hidden" role="img" aria-label="Postings by company">
          <ResponsiveContainer
            width="100%"
            height={Math.max(220, chartCompanies.length * 32 + 40)}
          >
            <BarChart
              data={chartCompanies}
              layout="vertical"
              margin={{ top: 4, right: 24, left: 4, bottom: 0 }}
            >
              <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                allowDecimals={false}
                tick={CHART_AXIS_STYLE}
                label={chartAxisLabel("Postings")}
              />
              <YAxis
                type="category"
                dataKey="company_name"
                width={150}
                tick={CHART_AXIS_STYLE}
                tickFormatter={(value: string) =>
                  value.length > 20 ? `${value.slice(0, 19)}…` : value
                }
              />
              <Tooltip
                content={<ChartTooltip colorByName={companyColorByName} />}
                contentStyle={CHART_TOOLTIP_STYLE}
                cursor={{ fill: CHART_CURSOR_FILL }}
              />
              <Bar dataKey="posting_count" radius={[0, 4, 4, 0]} barSize={14}>
                {chartCompanies.map((company) => (
                  <Cell
                    key={company.company_slug}
                    fill={companyColorByName.get(company.company_name)}
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
          {trueTotal > chartCompanies.length && (
            <p className="mt-1 text-xs text-muted-foreground">
              Showing the top {chartCompanies.length} of {formatCount(trueTotal)} companies by
              postings
              {detailsCapped
                ? `. Detailed rows cover the ${formatCount(ranked.length)} most active companies.`
                : "."}
            </p>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {detailCompanies.map((company) => (
            <div key={company.company_slug} className="min-w-0 rounded-md border border-border p-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {company.company_name}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">{company.industry}</p>
                </div>
                <Badge variant="outline">
                  {formatCount(company.posting_count)} postings ·{" "}
                  {formatPercent(company.posting_share_pct, 1)}
                </Badge>
              </div>
              <SkillChips company={company} />
              <p className="mt-3 text-xs text-muted-foreground">
                Year-wise postings:{" "}
                {Object.entries(company.yearly_counts)
                  .map(([year, count]) => `${year}: ${count}`)
                  .join(" · ")}
              </p>
            </div>
          ))}
        </div>

        {ranked.length > DETAIL_PREVIEW && (
          <div className="flex justify-center">
            <Button variant="outline" size="sm" onClick={() => setShowAll((value) => !value)}>
              {showAll
                ? `Show top ${DETAIL_PREVIEW} companies only`
                : detailsCapped
                  ? `Show all ${formatCount(ranked.length)} detailed companies`
                  : `Show all ${formatCount(ranked.length)} companies`}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
