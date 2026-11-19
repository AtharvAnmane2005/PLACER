import { Building2, Briefcase, CalendarDays, Code2, TrendingUp, Trophy } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/shared/stat-card";
import { formatCount, formatPercent, formatSignedPercent } from "@/lib/format";
import type { MarketMeta, MarketSummary } from "@/types/market-analytics";

function SummarySkeleton() {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-6">
        <div className="w-full space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-16" />
        </div>
        <Skeleton className="h-11 w-11 rounded-full" />
      </CardContent>
    </Card>
  );
}

export function MarketSummaryCards({
  summary,
  meta,
  isLoading,
}: {
  summary: MarketSummary | undefined;
  meta?: MarketMeta;
  isLoading: boolean;
}) {
  if (isLoading || !summary) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, index) => (
          <SummarySkeleton key={index} />
        ))}
      </div>
    );
  }

  // YoY growth is only meaningful when a comparable previous period exists.
  // The backend now reports the exact basis it used (latest complete years
  // when the newest year is still partial), so the card never compares a
  // half-finished year against a full one.
  const hasGrowth = summary.yoy_posting_growth_pct != null;
  const periodLabel = meta?.current_period?.label;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <StatCard label="Total job postings" value={formatCount(summary.total_postings)} icon={Briefcase} />
      <StatCard label="Companies tracked" value={formatCount(summary.company_count)} icon={Building2} />
      <StatCard label="Skills tracked" value={formatCount(summary.distinct_skill_count)} icon={Code2} />
      <StatCard
        label="Most demanded skill"
        value={
          summary.most_demanded_skill ? (
            <span className="text-lg font-semibold">
              {summary.most_demanded_skill.name}
              <span className="ml-1 text-sm font-normal text-muted-foreground">
                ({formatPercent(summary.most_demanded_skill.demand_pct, 1)})
              </span>
            </span>
          ) : (
            "—"
          )
        }
        hint={
          meta?.comparison_comparable && periodLabel
            ? `Share of ${periodLabel} postings`
            : "Share of all filtered postings"
        }
        icon={Trophy}
      />
      {hasGrowth ? (
        <StatCard
          label="YoY posting growth"
          value={formatSignedPercent(summary.yoy_posting_growth_pct, 1)}
          hint={summary.yoy_growth_basis ?? undefined}
          icon={TrendingUp}
        />
      ) : (
        <StatCard
          label="Posting period"
          value={periodLabel ?? "—"}
          valueClassName="text-lg"
          hint="No complete prior period to compare"
          icon={CalendarDays}
        />
      )}
    </div>
  );
}
