import type { MarketFiltersResponse } from "@/types/market-analytics";

/**
 * Compact, human-readable labels for the collapsed filter summaries.
 *
 * These only describe the applied filter values; they never derive or alter
 * analytics figures.
 */
export function yearLabel(from: number | null, to: number | null): string {
  if (from != null && to != null) return from === to ? String(from) : `${from}–${to}`;
  if (from != null) return `From ${from}`;
  if (to != null) return `To ${to}`;
  return "All years";
}

export function sourceLabel(
  source: string | null,
  options: MarketFiltersResponse | undefined
): string {
  if (!source || source === "real") return "All real postings";
  return options?.sources.find((entry) => entry.id === source)?.label ?? source;
}

export function companyLabel(
  slug: string | null,
  options: MarketFiltersResponse | undefined
): string {
  if (!slug) return "All companies";
  return options?.companies.find((company) => company.slug === slug)?.name ?? slug;
}
