"use client";

import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { FilterCard } from "@/components/shared/filter-card";
import { DEFAULT_MARKET_FILTERS, type MarketFiltersState } from "@/hooks/use-market-analytics";
import { companyLabel, sourceLabel, yearLabel } from "@/lib/filter-summary";
import { formatCount } from "@/lib/format";
import type { MarketFiltersResponse } from "@/types/market-analytics";

const ALL = "all";
const LIMIT_CHOICES = [10, 15, 20];

/**
 * Draft-based filter panel: selections update local draft state and only the
 * "Apply filters" action issues a new query, so adjusting several filters in
 * a row does not fire a request per change. "Reset filters" restores the
 * defaults and applies immediately.
 *
 * The controls are collapsed by default; the compact header still shows the
 * applied filters and how many are active.
 */
export function MarketFilterPanel({
  active,
  onApply,
  options,
  optionsLoading,
  optionsError,
  onRetryOptions,
}: {
  active: MarketFiltersState;
  onApply: (filters: MarketFiltersState) => void;
  options: MarketFiltersResponse | undefined;
  optionsLoading: boolean;
  optionsError: boolean;
  onRetryOptions: () => void;
}) {
  const [draft, setDraft] = useState<MarketFiltersState>(active);

  // Keep the draft in sync when the applied filters change (e.g. Reset).
  useEffect(() => {
    setDraft(active);
  }, [active]);

  const invalidYearRange =
    draft.year_from != null && draft.year_to != null && draft.year_from > draft.year_to;

  const update = (patch: Partial<MarketFiltersState>) =>
    setDraft((previous) => ({ ...previous, ...patch }));

  // Source changes apply immediately (not on "Apply filters") because the
  // company/location/year option lists belong to the selected source. Those
  // population filters are cleared so a slug from one source can never
  // silently produce an empty result in another.
  const applySource = (value: string) => {
    const next: MarketFiltersState = {
      ...draft,
      source: value,
      company: null,
      location: null,
      year_from: null,
      year_to: null,
    };
    setDraft(next);
    onApply(next);
  };

  const yearValue = (year: number | null) => (year != null ? String(year) : ALL);

  const activeCount = [
    active.year_from != null,
    active.year_to != null,
    active.company != null,
    active.job_family != null,
    active.location != null,
    active.skill_category != null,
    active.technical_only,
  ].filter(Boolean).length;

  const summary = [
    sourceLabel(active.source, options),
    yearLabel(active.year_from, active.year_to),
    active.job_family ?? "All domains",
    companyLabel(active.company, options),
    active.location ?? "All locations",
    active.skill_category,
    active.technical_only ? "Technical only" : null,
  ]
    .filter((part): part is string => Boolean(part))
    .join(" · ");

  const companyCapped =
    options != null && options.company_total > options.companies.length;
  const locationCapped =
    options != null && options.location_total > options.locations.length;

  return (
    <FilterCard activeCount={activeCount} summary={summary}>
      <div className="space-y-1.5 sm:max-w-[240px]">
        <Label htmlFor="data-source">Data source</Label>
        <Select value={draft.source ?? "real"} onValueChange={applySource}>
          <SelectTrigger id="data-source">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="real">All real public postings</SelectItem>
            {(options?.sources ?? [])
              .filter((source) => !source.is_mock)
              .map((source) => (
                <SelectItem key={source.id} value={source.id}>
                  {source.label} ({formatCount(source.posting_count)} postings)
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      {optionsError ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <span>Couldn&apos;t load filter options.</span>
          <Button variant="outline" size="sm" onClick={onRetryOptions}>
            Retry
          </Button>
        </div>
      ) : optionsLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* --- Posting-population filters ----------------------------- */}
          <div className="space-y-1.5">
            <Label htmlFor="year-from">From year</Label>
            <Select
              value={yearValue(draft.year_from)}
              onValueChange={(value) =>
                update({ year_from: value === ALL ? null : Number(value) })
              }
            >
              <SelectTrigger id="year-from">
                <SelectValue placeholder="All years" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All years</SelectItem>
                {(options?.years ?? []).map((year) => (
                  <SelectItem key={year} value={String(year)}>
                    {year}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="year-to">To year</Label>
            <Select
              value={yearValue(draft.year_to)}
              onValueChange={(value) => update({ year_to: value === ALL ? null : Number(value) })}
            >
              <SelectTrigger id="year-to">
                <SelectValue placeholder="All years" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All years</SelectItem>
                {(options?.years ?? []).map((year) => (
                  <SelectItem key={year} value={String(year)}>
                    {year}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="company">Company</Label>
            <Select
              value={draft.company ?? ALL}
              onValueChange={(value) => update({ company: value === ALL ? null : value })}
            >
              <SelectTrigger id="company">
                <SelectValue placeholder="All companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All companies</SelectItem>
                {(options?.companies ?? []).map((company) => (
                  <SelectItem key={company.slug} value={company.slug}>
                    {company.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="job-family">Domain</Label>
            <Select
              value={draft.job_family ?? ALL}
              onValueChange={(value) => update({ job_family: value === ALL ? null : value })}
            >
              <SelectTrigger id="job-family">
                <SelectValue placeholder="All domains" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All domains</SelectItem>
                {(options?.job_families ?? []).map((family) => (
                  <SelectItem key={family} value={family}>
                    {family}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="location">Location</Label>
            <Select
              value={draft.location ?? ALL}
              onValueChange={(value) => update({ location: value === ALL ? null : value })}
            >
              <SelectTrigger id="location">
                <SelectValue placeholder="All locations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All locations</SelectItem>
                {(options?.locations ?? []).map((location) => (
                  <SelectItem key={location} value={location}>
                    {location}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* --- Skill-scope filters ----------------------------------- */}
          <div className="space-y-1.5">
            <Label htmlFor="skill-category">Skill category</Label>
            <Select
              value={draft.skill_category ?? ALL}
              onValueChange={(value) =>
                update({ skill_category: value === ALL ? null : value })
              }
            >
              <SelectTrigger id="skill-category">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All categories</SelectItem>
                {(options?.skill_categories ?? []).map((category) => (
                  <SelectItem key={category} value={category}>
                    {category}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="technical-only">Skill type</Label>
            <Select
              value={draft.technical_only ? "technical" : ALL}
              onValueChange={(value) => update({ technical_only: value === "technical" })}
            >
              <SelectTrigger id="technical-only">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All skills</SelectItem>
                <SelectItem value="technical">Technical skills only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* --- Presentation options ---------------------------------- */}
          <div className="space-y-1.5">
            <Label htmlFor="sort-by">Sort by</Label>
            <Select
              value={draft.sort}
              onValueChange={(value) => update({ sort: value as MarketFiltersState["sort"] })}
            >
              <SelectTrigger id="sort-by">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="trending">Trending</SelectItem>
                <SelectItem value="demand">Most demanded</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="skill-limit">Skill limit</Label>
            <Select
              value={String(draft.limit)}
              onValueChange={(value) => update({ limit: Number(value) })}
            >
              <SelectTrigger id="skill-limit">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LIMIT_CHOICES.map((choice) => (
                  <SelectItem key={choice} value={String(choice)}>
                    {choice}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {(companyCapped || locationCapped) && options != null && (
        <p className="text-xs text-muted-foreground">
          Company and location lists show the most active options
          {companyCapped
            ? ` · ${formatCount(options.companies.length)} of ${formatCount(options.company_total)} companies`
            : ""}
          {locationCapped
            ? ` · ${formatCount(options.locations.length)} of ${formatCount(options.location_total)} locations`
            : ""}
          .
        </p>
      )}

      {invalidYearRange && (
        <p className="text-sm text-destructive">From year must be on or before To year.</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          onClick={() => onApply(draft)}
          disabled={invalidYearRange || optionsLoading || optionsError}
        >
          Apply filters
        </Button>
        <Button
          variant="outline"
          onClick={() => onApply({ ...DEFAULT_MARKET_FILTERS })}
          disabled={optionsLoading}
        >
          <RotateCcw className="mr-2 h-4 w-4" /> Reset filters
        </Button>
      </div>
    </FilterCard>
  );
}
